"""Map packs (DLC maps): which players have which pack, and which maps a match may use.
Spec: re/part1/map-packs.md. Off unless the daemon runs with T2R_MAP_PACKS=1; with an empty registry
(tools/map_packs.json "packs": []) nothing changes either: no map is added, every pool stays as it was.

Registry (server side, tools/map_packs.json or T2R_MAP_PACKS_FILE):
  {"packs": [{"id": "part1-a", "ver": 1, "hash": "1a2b3c4d",          # hash = CRC-32 of the pack archive (hex)
              "maps": [["Bill's Town", "p1-bills-town", "to1-p1-bills-town", 13], ...]}]}
                        display name, image key (streaming/menus/to1/map-pvp-<key>.png), level, respawn count
Pack maps get the map-list indices PACK_BASE.. in registry order (PACK_BASE = t2r-ext MF_NMAPS: the ext knows
indices below it by heart and treats every index at or above it as a pack map).

Client report (t2r-ext short TCP connection, sent only by a client that has at least one valid pack):
  0xC6 [64B token][u8 n][n x u32 LE pack hash]          (n <= MAX_PACKS: the ext's request payload is 48 bytes)
  reply 0xC7 "on=1 acc=<pack ids, comma separated or -> pm<index>=<level> ..." (on=0: packs off on this server)
A client that never reports (old builds, no packs) owns no pack. A report replaces the previous one.
"""
import json
import os
import struct
import threading
import time

OP_REPORT = 0xC6
OP_REPLY = 0xC7
PACK_BASE = 24          # first map-list index of a pack map (= t2r-ext MF_NMAPS)
MAX_PACKS = 11            # 1 + 11 x 4 bytes fit the ext's 48-byte request payload
MAX_PACK_MAPS = 32        # t2r-ext PACK_MAPS_MAX
REPORT_TTL = 6 * 3600.0   # a report older than this no longer counts (the client re-reports every few minutes)
DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_packs.json")


def enabled():
    return os.environ.get("T2R_MAP_PACKS", "") == "1"


def load_registry(path=None):
    """The pack list of the registry file ([] when the file is missing, empty or broken)."""
    path = path or os.environ.get("T2R_MAP_PACKS_FILE") or DEFAULT_FILE
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    out, seen_ids, seen_lvls = [], set(), set()
    for p in data.get("packs", []) if isinstance(data, dict) else []:
        try:
            pid, h = str(p["id"]), int(str(p["hash"]), 16) & 0xffffffff
            maps = [(str(n), str(img), str(lvl), int(resp)) for n, img, lvl, resp in p.get("maps", [])]
        except (KeyError, TypeError, ValueError):
            continue
        if not pid or pid in seen_ids or not maps or any(m[2] in seen_lvls for m in maps):
            continue
        seen_ids.add(pid)
        seen_lvls.update(m[2] for m in maps)
        out.append({"id": pid, "ver": int(p.get("ver", 1)), "hash": h, "maps": maps})
    return out


# ---- single-player-section maps (tools/maps/sp_maps.json, daemon SP_MAPS): which of them a client's DLL contains
# A DLL built without T2R_SP_MAPS has no such to1-levels subnode and hangs at match state 3 when the server picks the map.
# Same rule as the packs: a match's pool / vote only offers an SP map when EVERY player reported it; an old client that
# never reports gets base maps only.
#   0xC8 [64B token][u32 LE mask]        bit k = map-list index SP_BASE + k is in this client's DLL (scan of the to1-levels subnodes)
#   reply 0xC9 "on=1 sp=<mask hex>"      (the mask the server stored; on=0 = gating off on this server)
SP_OP_REPORT = 0xC8
SP_OP_REPLY = 0xC9
SP_BASE = 8               # first map-list index of an SP-section map (daemon SP_MAPS order; t2r-ext MF_MAPS[8..])
SP_MAX = 16               # mask bits


def sp_gating():
    """On by default; T2R_SP_GATE=0 turns it off (testing an old DLL against a server that lists the maps)."""
    return os.environ.get("T2R_SP_GATE", "1") != "0"


def parse_sp_report(pl):
    """0xC8 payload -> (token, mask) or None."""
    if len(pl) < 68:
        return None
    token = pl[:64].decode("latin1", "ignore")
    if not all(ch in "0123456789abcdefABCDEF" for ch in token):
        return None
    return token, struct.unpack_from("<I", pl, 64)[0] & ((1 << SP_MAX) - 1)


class SpSupport:
    def __init__(self, sp_levels=(), clock=time.time):
        self.levels = {lvl: k for k, lvl in enumerate(sp_levels)}      # level -> bit (map-list order from SP_BASE)
        self.have = {}                                                  # token -> (mask, time of the report)
        self.clock = clock
        self.lock = threading.Lock()

    def is_sp(self, level):
        return level in self.levels

    def report(self, token, mask):
        with self.lock:
            self.have[token] = (mask & ((1 << SP_MAX) - 1), self.clock())
        return mask

    def mask_of(self, token):
        with self.lock:
            mask, at = self.have.get(token, (0, 0.0))
        return mask if self.clock() - at < REPORT_TTL else 0

    def allowed(self, level, players):
        """A non-SP map: always. An SP map: only with players, every one of whom reported it (gating off: always)."""
        k = self.levels.get(level)
        if k is None or not sp_gating():
            return True
        return bool(players) and all((self.mask_of(t) >> k) & 1 for t in players)

    def reply_text(self, token):
        return "on=1 sp=%x" % self.mask_of(token)


class Packs:
    def __init__(self, registry=(), clock=time.time):
        self.registry = list(registry)
        self.by_hash = {p["hash"]: p for p in self.registry}
        self.level_pack = {m[2]: p["id"] for p in self.registry for m in p["maps"]}
        self.have = {}                     # token -> (set of pack ids, time of the report)
        self.clock = clock
        self.lock = threading.Lock()

    def maps(self):
        """(name, image key, level, respawns) of every pack map, in index order (PACK_BASE..)."""
        return [m for p in self.registry for m in p["maps"]][:MAX_PACK_MAPS]

    def is_pack_map(self, level):
        return level in self.level_pack

    def report(self, token, hashes):
        """A client's installed packs (archive hashes). Unknown hashes (other versions) don't count."""
        ids = {self.by_hash[h]["id"] for h in hashes if h in self.by_hash}
        with self.lock:
            self.have[token] = (ids, self.clock())
        return ids

    def ids_of(self, token):
        with self.lock:
            ids, at = self.have.get(token, (set(), 0.0))
        return set(ids) if self.clock() - at < REPORT_TTL else set()

    def allowed(self, level, players):
        """A base map: always. A pack map: only when there are players and every one of them has its pack."""
        pid = self.level_pack.get(level)
        if pid is None:
            return True
        return bool(players) and all(pid in self.ids_of(t) for t in players)

    def reply_text(self, token, maps_list):
        """The 0xC7 text: accepted packs and the map-list index of every pack map on this server."""
        acc = sorted(self.ids_of(token))
        t = ["on=1", "acc=" + (",".join(acc) or "-")]
        t += ["pm%d=%s" % (i, m[2]) for i, m in enumerate(maps_list) if m[2] in self.level_pack]
        return " ".join(t)


def parse_report(pl):
    """0xC6 payload -> (token, [hashes]) or None."""
    if len(pl) < 65:
        return None
    token = pl[:64].decode("latin1", "ignore")
    if not all(ch in "0123456789abcdefABCDEF" for ch in token):
        return None
    n = min(pl[64], MAX_PACKS)
    if len(pl) < 65 + 4 * n:
        return None
    return token, [struct.unpack_from("<I", pl, 65 + 4 * i)[0] for i in range(n)]
