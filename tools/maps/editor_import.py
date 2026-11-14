"""Bring a SceneEditor-saved map pak back into the json the build regenerates the pak from (so `sp_maps.py pak <key>` keeps hand edits).

  python editor_import.py <key> <saved pak>                 # diff only: what the editor changed vs our json
  python editor_import.py <key> <saved pak> --apply         # write it: data/<key>-spawns.json, sp_maps.json props, data/<key>-medkits.json + tools/ext/medkits.h
  python editor_import.py <key> --export-kits <pak>         # put our kits (data/<key>-medkits.json) into an editor pak as to1-healthkit-N (backup .bak)
  python editor_import.py <key> --export-spots <pak> [--out <pak2>]   # put our item spots (data/<key>-itemspots.json) into an editor pak as random-spot-N / loot-spot-N
                                                            # masters + random-spot-N-i-<item> markers (in place with .bak, or into --out; refuses a pak that has spots)

Names / art groups the editor must keep (everything else is a prop or reported as unrecognised):
  player + camera                       start pose (json "player"; both move together)
  to1-t0-intro-spawn-point-1..4         team 0 intro spawns   (json intro0)      to1-t1-intro-spawn-point-1..4  team 1 (intro1)
  to1-spawn-point-N                     respawns, art `ellie`, N = list position (json respawns; delete / add / renumber freely)
  to1-supplybox-N                       supply boxes, SimpleObject art `pickup-chest`, N <= 12 (json boxes). The 12 item positions
                                        to1-supplybox-N-itempos-M are derived from the box and ignored.
  art group `medkit` (ItemPickup)       health kits, any name (recommended to1-healthkit-N) -> data/<key>-medkits.json, flagged hand_placed
  any other spawner with an art group   prop (name to1-prop-N or anything: invis-collision, window boards, crates, cars ...) -> sp_maps.json props
  random-<family>-N-<what> (any art)    RANDOM ITEM SPOT: spawners named `random-` (random-util-1-molotov, random-util-2-pipebomb, random-ammo-1-...) of
                                        the same family that sit within 0.5 m of each other (or are parented into each other) are ONE spot;
                                        its candidates = their art groups (molotov, pipe-bomb, knife-shiv, stun-bomb, medkit, + item ids), the
                                        family = the name after `random-` up to the next `-<digit>`. Duplicate the whole stack around the map
                                        (select all 4, duplicate, move). -> data/<key>-itemspots.json + tools/ext/itemspots.h. The ext fills a
                                        spot ~70 % of the time with one candidate, re-rolls 60 s after a pickup. Not written into the pak.
                                        A pak without any random- spawner leaves the spots alone; with some, the pak is the truth for ALL spots.
Props are matched to the old ones (same art + pose, then the same name to1-prop-N, then the nearest of the same art within 3 m), so moves,
art swaps, scale changes, deletions and additions show up as such. Props keep their metadata (auto / fp / note ...) when matched; new ones get none.
Health kits: a pak without any medkit spawner leaves the kits alone (the generated pak carries none; the ext spawns them from medkits.h). As soon
as the pak has at least one, the pak is the truth for ALL kits of the map (use --export-kits first to get ours into the editor).
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "data")
SPEC = os.path.join(HERE, "sp_maps.json")
DUMP = os.path.join(HERE, "editor_dump.ps1")
EDIT = os.path.join(HERE, "editor_edit.ps1")

POS_TOL = 0.005            # m: json rounds to 3 decimals
ANG_TOL = 0.1              # degrees
SCALE_TOL = 1e-3
MATCH_MOVE = 3.0           # m: nearest same-art prop that counts as the same one moved
KIT_MATCH = 10.0           # m: nearest kit that counts as the same one moved

RX_INTRO = re.compile(r"^to1-t([01])-intro-spawn-point-(\d+)$")
RX_RESP = re.compile(r"^to1-spawn-point-(\d+)$")
RX_BOX = re.compile(r"^to1-supplybox-(\d+)$")
RX_ITEM = re.compile(r"^to1-supplybox-\d+-itempos-\d+$")
RX_PROP = re.compile(r"^to1-prop-(\d+)$")
RX_SPOT_M = re.compile(r"^(?:random|loot)-spot-(\d+)(?:-shared)?$")   # item spawner; loot-spot-N[-shared] = the loot group (SceneEditor build-next25)
RX_LOOT = re.compile(r"^loot-spot-(\d+)(-shared)?$")
RX_SPOT_I = re.compile(r"^random-spot-(\d+)-i-(.+?)(?:-w(\d+))?$")   # its item markers: random-spot-3-i-machete[-w2] (world pose = spot * offset)
RX_CAR = re.compile(r"^t2r-car-(\d+)-(.+)$")                 # vehicle cover preset instance (sp_maps.json "prefabs", tools/maps/vehicle_presets.py)
RX_LOCKBOX = re.compile(r"^to1-lockbox-t([01])-(\d+)$")           # interrogation safe candidates (data/<key>-lockboxes.json)
RX_RANDOM = re.compile(r"^random-(.+?)(?:-\d.*)?$")      # random-util-1-molotov -> family `util`
SPOT_JOIN = 0.5            # m: random- spawners of one family this close (or parented into each other) are ONE item spot
SPOT_MATCH = 3.0           # m: nearest old item spot that counts as the same one moved
DATA_KEY = {"hospital-ellie": "hospital"}   # map key -> key of its medkits / itemspots / satchels data files (medkits.INDEX, satchels.py)
MAP_INDEX = {"chase": 22, "jackson-market": 23, "p1-bookstore": 17}   # maps outside medkits.INDEX that have satchel spots


# ------------------------------------------------------------------ reading
def read_pak(path):
    """[{name, type, art, pos, quat, scale}] of every spawner (SceneEditor Core DLL via editor_dump.ps1)"""
    fd, out = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        subprocess.run(["pwsh", "-NoProfile", "-File", DUMP, "-Pak", os.path.abspath(path), "-Out", out], check=True)
        return json.load(open(out, encoding="utf-8-sig"))
    finally:
        os.remove(out)


def classify(sp):
    c = {"player": None, "camera": None, "intro": {0: {}, 1: {}}, "resp": {}, "box": {}, "items": [], "props": [], "kits": [], "random": [], "spot_m": {}, "spot_i": [], "cars": [], "lockbox": [], "unknown": []}
    for s in sp:
        n, art = s["name"], (s.get("art") or "")
        m = None
        if n == "player":
            c["player"] = s
        elif n == "camera":
            c["camera"] = s
        elif RX_INTRO.match(n):
            m = RX_INTRO.match(n)
            c["intro"][int(m.group(1))][int(m.group(2))] = s
        elif RX_RESP.match(n):
            c["resp"][int(RX_RESP.match(n).group(1))] = s
        elif RX_BOX.match(n):
            c["box"][int(RX_BOX.match(n).group(1))] = s
        elif RX_ITEM.match(n):
            c["items"].append(s)
        elif RX_LOCKBOX.match(n):
            c["lockbox"].append(s)
        elif RX_CAR.match(n):
            c["cars"].append(s)
        elif RX_SPOT_M.match(n):
            c["spot_m"][int(RX_SPOT_M.match(n).group(1))] = s
        elif RX_SPOT_I.match(n):
            m2 = RX_SPOT_I.match(n)
            c["spot_i"].append((int(m2.group(1)), m2.group(2), int(m2.group(3) or 1), s))
        elif RX_RANDOM.match(n):
            c["random"].append(s)
        elif art.lower() == "medkit":
            c["kits"].append(s)
        elif art and art not in ("pickup-chest",) and not art.startswith("ellie") and (s.get("type") in ("SimpleObject", None, "", "None") or RX_PROP.match(n)):   # type "None" = an art group placed from the Project panel without a spawner type (crate + gate walls)
            c["props"].append(s)
        else:
            c["unknown"].append(s)
    return c


# ------------------------------------------------------------------ geometry
def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def ang(a, b):
    """degrees between two rotations"""
    na = math.sqrt(sum(v * v for v in a)) or 1.0
    nb = math.sqrt(sum(v * v for v in b)) or 1.0
    a = [v / na for v in a]
    b = [v / nb for v in b]
    d = qmul(a, (-b[0], -b[1], -b[2], b[3]))
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2))))


def moved(old, new):
    """(distance m, rotation deg) between two {pos, quat}"""
    return math.dist(old["pos"], new["pos"]), (ang(old["quat"], new["quat"]) if "quat" in old and "quat" in new else 0.0)


def same(old, new):
    d, a = moved(old, new)
    return d <= POS_TOL and a <= ANG_TOL


def r3(v):
    return [round(float(x), 3) for x in v]


def r6(v):
    return [round(float(x), 6) for x in v]


def pose(s):
    return {"pos": r3(s["pos"]), "quat": r6(s["quat"])}


# ------------------------------------------------------------------ diff
class Diff:
    def __init__(self):
        self.lines = {}          # category -> [str]
        self.n = 0
        self.info = []

    def add(self, cat, text):
        self.lines.setdefault(cat, []).append(text)
        self.n += 1

    def note(self, text):
        self.info.append(text)

    def show(self):
        for cat, ls in self.lines.items():
            print(f"{cat}: {len(ls)} change(s)")
            for l in ls:
                print("   " + l)
        for t in self.info:
            print("note: " + t)
        print("no differences" if not self.n else f"{self.n} change(s) in total")


def fmt(p):
    return "({:.2f} {:.2f} {:.2f})".format(*p["pos"])


def diff_slots(df, cat, label, old, new):
    """old: list of {pos, quat} (index i = number i+1), new: {number: spawner}; -> the resulting list"""
    out = []
    for i, o in enumerate(old):
        s = new.get(i + 1)
        if s is None:
            df.add(cat, f"- removed {label}{i + 1} at {fmt(o)}")
            continue
        d, a = moved(o, s)
        if d > POS_TOL or a > ANG_TOL:
            bits = []
            if d > POS_TOL:
                bits.append(f"moved {d:.2f} m")
            if a > ANG_TOL:
                bits.append(f"turned {a:.1f} deg")
            df.add(cat, f"~ {label}{i + 1} {', '.join(bits)}: {fmt(o)} -> {fmt(s)}")
            out.append(dict(o, **pose(s)))
        else:
            out.append(o)
    extra = []
    for n in sorted(k for k in new if k > len(old)):
        df.add(cat, f"+ added {label}{n} at {fmt(new[n])}")
        extra.append(pose(new[n]))
    return out + extra


GEN_MOVE = 1.5            # m: a saved respawn this close to a generated point that is gone from its place = that generated point, moved by the user


def split_generated(df, cl, gen, n_user):
    """data/<key>-respawns-gen.json (tools/maps/respawn_fill.py): the pak build appends those points as to1-spawn-point-<n_user+1..>. Takes them
    out of cl["resp"] (by pose, any number) so diff_slots sees only the user's respawns -> the new generated list, or None (unchanged).
    Untouched = still generated; moved (<= GEN_MOVE) = the user's now (diff_slots adds it), dropped from the generated list; missing = deleted
    by the user, dropped. A pak that holds none of them (saved from a pak built before they existed) leaves the list alone."""
    if not gen or not gen.get("respawns"):
        return None
    pts = gen["respawns"]
    hit = {}
    for n, s in list(cl["resp"].items()):
        for k, g in enumerate(pts):
            if k not in hit.values() and same(g, s):
                hit[n] = k
                break
    if not hit:
        df.note(f"the pak holds none of the {len(pts)} generated respawns (saved from an older pak?): data/<key>-respawns-gen.json kept as it is")
        return None
    for n in hit:
        del cl["resp"][n]
    gone = [k for k in range(len(pts)) if k not in hit.values()]
    keep = set(hit.values())
    for k in gone:
        g = pts[k]
        near = [(math.dist(g["pos"], s["pos"]), n) for n, s in cl["resp"].items() if n > n_user]
        near = min(near) if near else None
        if near and near[0] <= GEN_MOVE:
            df.add("respawns", f"~ generated respawn {fmt(g)} moved {near[0]:.2f} m by you -> it is a user respawn now (to1-spawn-point-{near[1]} in the save)")
        else:
            df.add("respawns", f"- removed generated respawn at {fmt(g)}")
    if not gone:
        return None
    out = dict(gen)
    out["respawns"] = [g for k, g in enumerate(pts) if k in keep]
    return out


def diff_spawns(df, cl, spawns):
    """-> the new spawns json (a copy)"""
    new = json.loads(json.dumps(spawns))
    if "player" in spawns:
        if cl["player"] is None:
            df.note("pak has no `player` spawner: player pose kept")
        else:
            o, s = spawns["player"], cl["player"]
            d, a = moved(o, s)
            if d > POS_TOL or a > ANG_TOL:
                df.add("player", f"~ player moved {d:.2f} m, turned {a:.1f} deg: {fmt(o)} -> {fmt(s)}")
                new["player"] = dict(o, **pose(s))
            if cl["camera"] is not None and not same(o, cl["camera"]) and not same(s, cl["camera"]):
                df.note(f"`camera` differs from `player` ({math.dist(cl['camera']['pos'], s['pos']):.2f} m): ignored, the pak build puts both on the player pose")
    for t in (0, 1):
        key = f"intro{t}"
        if key not in spawns:
            continue
        have = cl["intro"][t]
        old = spawns[key]
        out = []
        for i, o in enumerate(old):
            s = have.get(i + 1)
            if s is None:
                df.note(f"pak has no to1-t{t}-intro-spawn-point-{i + 1}: {key}[{i}] kept")
                out.append(o)
                continue
            d, a = moved(o, s)
            if d > POS_TOL or a > ANG_TOL:
                bits = ([f"moved {d:.2f} m"] if d > POS_TOL else []) + ([f"turned {a:.1f} deg"] if a > ANG_TOL else [])
                df.add(key, f"~ team {t} intro {i + 1} {', '.join(bits)}: {fmt(o)} -> {fmt(s)}")
                out.append(dict(o, **pose(s)))
            else:
                out.append(o)
        for n in sorted(k for k in have if k > len(old)):
            df.note(f"to1-t{t}-intro-spawn-point-{n}: only 4 intro slots exist - ignored")
        new[key] = out
    if "respawns" in spawns:
        new["respawns"] = diff_slots(df, "respawns", "respawn ", spawns["respawns"], cl["resp"])
    if "boxes" in spawns:
        new["boxes"] = diff_slots(df, "boxes", "supply box ", spawns["boxes"], cl["box"])
        if len(new["boxes"]) > 12:
            df.note(f"{len(new['boxes'])} supply boxes: winmm holds 12 at most, the pak build will refuse")
    return new


def prop_changes(o, s):
    """list of change phrases between an old spec prop and a saved prop spawner"""
    bits = []
    if o["art"] != s["art"]:
        bits.append(f"art {o['art']} -> {s['art']}")
    d, a = moved(o, s)
    if d > POS_TOL:
        bits.append(f"moved {d:.2f} m")
    if a > ANG_TOL:
        bits.append(f"turned {a:.1f} deg")
    sc = s.get("scale") or [1, 1, 1]
    osc = o.get("scale") or [1, 1, 1]
    if max(abs(x - y) for x, y in zip(sc, osc)) > SCALE_TOL:
        bits.append("scale {} -> {}".format([round(x, 3) for x in osc], [round(x, 3) for x in sc]))
    return bits


def diff_props(df, cl, props):
    """-> (new props list, unmatched count). Matching: identical, same name index, nearest same art within 3 m."""
    saved = list(cl["props"])
    pair = {}                                   # old index -> saved spawner
    used = set()
    for i, o in enumerate(props):               # 1: untouched (same art, pose, scale)
        for j, s in enumerate(saved):
            if j not in used and not prop_changes(o, s):
                pair[i] = j
                used.add(j)
                break
    for j, s in enumerate(saved):               # 2: same name to1-prop-N
        m = RX_PROP.match(s["name"])
        if j in used or not m:
            continue
        i = int(m.group(1)) - 1
        if 0 <= i < len(props) and i not in pair:
            pair[i] = j
            used.add(j)
    for j, s in enumerate(saved):               # 3: nearest of the same art
        if j in used:
            continue
        best = None
        for i, o in enumerate(props):
            if i not in pair and o["art"] == s["art"]:
                d = math.dist(o["pos"], s["pos"])
                if d <= MATCH_MOVE and (best is None or d < best[0]):
                    best = (d, i)
        if best:
            pair[best[1]] = j
            used.add(j)
    out = []
    for i, o in enumerate(props):
        if i not in pair:
            df.add("props", f"- removed {o['art']} at {fmt(o)}" + (f" ({o['note']})" if o.get("note") else ""))
            continue
        s = saved[pair[i]]
        bits = prop_changes(o, s)
        if not bits:
            out.append(o)
            continue
        df.add("props", f"~ {o['art']} {fmt(o)}: " + ", ".join(bits) + (f"  [{s['name']}]" if s["name"] != f"to1-prop-{i + 1}" else ""))
        n = dict(o, art=s["art"], **pose(s))
        sc = s.get("scale") or [1, 1, 1]
        if max(abs(x - 1) for x in sc) > SCALE_TOL:
            n["scale"] = [round(x, 4) for x in sc]
        else:
            n.pop("scale", None)
        out.append(n)
    for j, s in enumerate(saved):
        if j in used:
            continue
        df.add("props", f"+ added {s['art']} at {fmt(s)}  [{s['name']}]")
        n = {"art": s["art"], **pose(s)}
        sc = s.get("scale") or [1, 1, 1]
        if max(abs(x - 1) for x in sc) > SCALE_TOL:
            n["scale"] = [round(x, 4) for x in sc]
        out.append(n)
    return out


def diff_kits(df, cl, key, mk_json, mk_path):
    """-> the new kit list [{pos}] or None (leave the kits alone)"""
    saved = cl["kits"]
    old = (mk_json or {}).get("kits", [])
    if not saved:
        if old:
            df.note(f"no medkit spawners in the pak: the {len(old)} kit(s) of data/{key}-medkits.json stay as they are "
                    f"({'hand placed' if mk_json.get('hand_placed') else 'generated'}; the pak build writes none, the ext spawns them from medkits.h)")
        return None
    pairs = sorted(((math.dist(o["pos"], s["pos"]), i, j) for i, o in enumerate(old) for j, s in enumerate(saved)))
    pi, pj, link = set(), set(), []
    for d, i, j in pairs:
        if i in pi or j in pj or d > KIT_MATCH:
            continue
        pi.add(i)
        pj.add(j)
        link.append((i, j, d))
    out = []
    for i, o in enumerate(old):
        m = [(j, d) for (a, j, d) in link if a == i]
        if not m:
            df.add("medkits", f"- removed kit at {fmt(o)}")
            continue
        j, d = m[0]
        if d > POS_TOL:
            df.add("medkits", f"~ kit moved {d:.2f} m: {fmt(o)} -> {fmt(saved[j])}  [{saved[j]['name']}]")
            out.append({"pos": r3(saved[j]["pos"])})
        else:
            out.append({"pos": o["pos"]})
    for j, s in enumerate(saved):
        if j not in pj:
            df.add("medkits", f"+ added kit at {fmt(s)}  [{s['name']}]")
            out.append({"pos": r3(s["pos"])})
    if not df.lines.get("medkits"):
        return None            # same kits as the json: nothing to take over
    if not (mk_json or {}).get("hand_placed"):
        df.note(f"data/{key}-medkits.json becomes hand_placed (`medkits.py gen` keeps it from now on)")
    return out


def cluster_spots(random_sp):
    """random- spawners -> [{pos, quat, family, arts, names}]: one spot per family-cluster (members within SPOT_JOIN m or parented chain)"""
    fam = lambda s: RX_RANDOM.match(s["name"]).group(1)
    n = len(random_sp)
    up = list(range(n))

    def find(i):
        while up[i] != i:
            up[i] = up[up[i]]
            i = up[i]
        return i
    by_name = {s["name"]: i for i, s in enumerate(random_sp)}
    for i, a in enumerate(random_sp):
        p = a.get("parent")
        if p in by_name and fam(random_sp[by_name[p]]) == fam(a):
            up[find(i)] = find(by_name[p])
        for j in range(i):
            if fam(random_sp[j]) == fam(a) and math.dist(random_sp[j]["pos"], a["pos"]) <= SPOT_JOIN:
                up[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(random_sp[i])
    out = []
    for g in groups.values():
        names = {s["name"] for s in g}
        roots = [s for s in g if s.get("parent") not in names] or g
        arts = []
        for s in g:
            a = (s.get("art") or "").lower()
            if a and a not in arts:
                arts.append(a)
        c = [sum(s["pos"][k] for s in g) / len(g) for k in range(3)]
        out.append({"pos": r3(c), "quat": r6(roots[0]["quat"]), "family": fam(g[0]), "arts": arts, "names": sorted(names)})
    out.sort(key=lambda s: (s["family"], s["pos"]))
    return out


def qinv(q):
    n = sum(v * v for v in q) or 1.0
    return (-q[0] / n, -q[1] / n, -q[2] / n, q[3] / n)


def qrot(q, v):
    ux, uy, uz, w = q
    cx, cy, cz = uy * v[2] - uz * v[1], uz * v[0] - ux * v[2], ux * v[1] - uy * v[0]
    return [v[0] + 2 * (w * cx + uy * cz - uz * cy), v[1] + 2 * (w * cy + uz * cx - ux * cz), v[2] + 2 * (w * cz + ux * cy - uy * cx)]


def spots_from_pak(cl):
    """item spawners of the pak -> [{pos, quat, items:[norm_item], names}]: random-spot-N masters + their item markers (offset/rotation = marker pose relative to the master),
    plus legacy random-<family>-N-<art> stacks (every family but satchel) converted to spots at offset 0"""
    import itemspots as IS
    out = []
    for num, m in sorted(cl["spot_m"].items()):
        mq = tuple(m["quat"])
        items, names = [], [m["name"]]
        for (n2, item, w, s) in cl["spot_i"]:
            if n2 != num:
                continue
            off = qrot(qinv(mq), [s["pos"][k] - m["pos"][k] for k in range(3)])
            iq = qmul(qinv(mq), tuple(s["quat"]))
            ln = math.sqrt(sum(v * v for v in iq)) or 1.0
            iq = [v / ln for v in iq]
            if iq[3] < 0:
                iq = [-v for v in iq]
            items.append(IS.norm_item({"item": item, "art": (s.get("art") or "").lower() or None, "offset": off, "quat": iq, "weight": w}))
            names.append(s["name"])
        sp = {"pos": r3(m["pos"]), "quat": r6(mq), "items": items, "names": names}
        lm = RX_LOOT.match(m["name"])
        if lm:                                   # the group and shared / unique come from the master's name (the editor's Loot group check boxes)
            sp["group"], sp["shared"] = "loot", bool(lm.group(2))
        out.append(sp)
    for s in cluster_spots(cl["random"]):
        if s["family"] != "satchel":
            out.append({"pos": s["pos"], "quat": s["quat"], "items": [IS.norm_item({"art": a}) for a in s["arts"]], "names": s["names"], "legacy": True})
    return out


def diff_item_spots(df, cl, key, is_json):
    """-> the new spot list [{pos, quat, items}] or None (unchanged / no item spawners in the pak)"""
    import itemspots as IS
    new = spots_from_pak(cl)
    old = [IS.norm_spot(s) for s in (is_json or {}).get("spots", [])]
    if not new:
        if old:
            df.note(f"no item spawners in the pak: the {len(old)} spot(s) of data/{key}-itemspots.json stay as they are")
        return None
    for s in new:
        for i in s["items"]:
            if not i["item"] or (i["item"] not in IS.ITEM_IDS):
                df.note(f"item spawner at {fmt(s)}: '{i['item'] or i['art']}' is no known item (itemspots.py ITEMS) - ignored by the ext")
        if len(s["items"]) < 2:
            df.note(f"item spawner at {fmt(s)} has {len(s['items'])} item(s): it will only ever give that (or nothing)")
    pairs = sorted(((math.dist(o["pos"], s["pos"]), i, j) for i, o in enumerate(old) for j, s in enumerate(new)))
    pi, pj, link = set(), set(), []
    for d, i, j in pairs:
        if i in pi or j in pj or d > SPOT_MATCH:
            continue
        pi.add(i)
        pj.add(j)
        link.append((i, j, d))
    out = []
    lab = lambda s: "/".join(i["item"] or i["art"] for i in s["items"])
    # a pak prepared before the loot group existed (no loot-spot-N names) does not hold the loot scatter at all: keep it, never read it as removed
    stale_pak = any(o.get("group") == "loot" for o in old) and not any(s.get("group") == "loot" for s in new)
    if stale_pak:
        df.note(f"the editor pak predates the loot group (no loot-spot-N spawners): the {sum(o.get('group') == 'loot' for o in old)} loot spot(s) are kept as they are; "
                f"run python tools/maps/editor_prepare.py {key} to edit them in the SceneEditor")
    for i, o in enumerate(old):
        m = [(j, d) for (a, j, d) in link if a == i]
        if not m:
            if stale_pak and o.get("group") == "loot":
                out.append(o)
                continue
            df.add("itemspots", f"- removed item spawner at {fmt(o)} ({lab(o)})")
            continue
        j, d = m[0]
        s = new[j]
        bits = []
        if d > POS_TOL:
            bits.append(f"moved {d:.2f} m")
        if ang(o["quat"], s["quat"]) > ANG_TOL:
            bits.append(f"turned {ang(o['quat'], s['quat']):.1f} deg")
        oi = {x["item"]: x for x in o["items"]}
        ni = {x["item"]: x for x in s["items"]}
        add, rem = sorted(set(ni) - set(oi)), sorted(set(oi) - set(ni))
        if add:
            bits.append("+" + ",+".join(add))
        if rem:
            bits.append("-" + ",-".join(rem))
        for k in sorted(set(oi) & set(ni)):
            a, b = oi[k], ni[k]
            if math.dist(a["offset"], b["offset"]) > POS_TOL:
                bits.append(f"{k} offset {a['offset']} -> {b['offset']}")
            if ang(a["quat"], b["quat"]) > ANG_TOL:
                bits.append(f"{k} turned {ang(a['quat'], b['quat']):.1f} deg")
            if a["weight"] != b["weight"]:
                bits.append(f"{k} weight {a['weight']} -> {b['weight']}")
        if s.get("legacy"):
            bits.append("converted from a random-* stack")
        if not stale_pak:
            if (o.get("group") == "loot") != (s.get("group") == "loot"):
                bits.append("joined the loot group" if s.get("group") == "loot" else "left the loot group")
            elif s.get("group") == "loot" and bool(o.get("shared")) != bool(s.get("shared")):
                bits.append("now shared (per-player copy)" if s.get("shared") else "now unique")
        if bits:
            df.add("itemspots", f"~ item spawner {fmt(o)}: {', '.join(bits)}")
            for k in IS.SPOT_ATTRS:          # room / fill / respawn / dy survive the editor (the pak has no field for them); group / shared = the name
                if k in o and (stale_pak or k not in ("group", "shared")):
                    s[k] = o[k]
            if not stale_pak and s.get("group") != "loot":
                for k in ("group", "shared", "fill", "resp", "room"):
                    s.pop(k, None)
            if d > POS_TOL and "dy" in s:    # the contact correction belongs to the old place
                s.pop("dy")
                df.note(f"loot spot moved {d:.2f} m: re-measure its contact with python tools/maps/loot_place.py check {key} --fix")
            out.append(s)
        else:
            out.append(o)
    loot = [o for o in old if o.get("group") == "loot"]
    for j, s in enumerate(new):
        if j not in pj:
            if s.get("group") == "loot":                        # a loot spot placed in the editor takes room / fill / respawn of the nearest loot spot
                near = min(loot, key=lambda o: math.dist(o["pos"], s["pos"])) if loot else None
                if near is not None and math.dist(near["pos"], s["pos"]) <= 12.0:
                    for k in ("room", "fill", "resp"):
                        if k in near:
                            s[k] = near[k]
                df.note(f"new loot spot at {fmt(s)} ({'shared' if s.get('shared') else 'unique'}, room {s.get('room', '?')}): "
                        f"measure its contact with python tools/maps/loot_place.py check {key} --fix")
            df.add("itemspots", f"+ added item spawner at {fmt(s)} ({lab(s)}; from {', '.join(s['names'][:3])}{'...' if len(s['names']) > 3 else ''})")
            out.append(s)
    return out if df.lines.get("itemspots") else None


def diff_prefabs(df, cl, old):
    """vehicle cover presets (spawners t2r-car-N-<preset>, the names sp_maps.py pak gives them) -> [{preset, pos, quat, name}] or None (unchanged / none in the pak)"""
    new = []
    for s in sorted(cl["cars"], key=lambda x: int(RX_CAR.match(x["name"]).group(1))):
        m = RX_CAR.match(s["name"])
        new.append({"preset": m.group(2), "pos": r3(s["pos"]), "quat": r6(s["quat"]), "name": s["name"]})
    if not new and not old:
        return None
    pair = {}
    for j, s in enumerate(new):                 # same name first, then nearest of the same preset within 3 m
        for i, o in enumerate(old):
            if i not in pair.values() and (o.get("name") or "t2r-car-%d-%s" % (i + 1, o["preset"])) == s["name"]:
                pair[j] = i
                break
    for j, s in enumerate(new):
        if j in pair:
            continue
        c = sorted((math.dist(o["pos"], s["pos"]), i) for i, o in enumerate(old) if i not in pair.values() and o["preset"] == s["preset"])
        if c and c[0][0] <= 3.0:
            pair[j] = c[0][1]
    for i, o in enumerate(old):
        if i not in pair.values():
            df.add("prefabs", f"- removed vehicle {o['preset']} at {fmt(o)}")
    for j, s in enumerate(new):
        if j not in pair:
            df.add("prefabs", f"+ added vehicle {s['preset']} at {fmt(s)}")
            continue
        o = old[pair[j]]
        oq = o.get("quat") or [0.0, math.sin(math.radians(o.get("yaw", 0.0)) / 2), 0.0, math.cos(math.radians(o.get("yaw", 0.0)) / 2)]
        d = math.dist(o["pos"], s["pos"])
        a = ang(oq, s["quat"])
        if d > POS_TOL or a > ANG_TOL:
            df.add("prefabs", f"~ vehicle {s['preset']} {fmt(o)}: " + ", ".join(b for b in (f"moved {d:.2f} m" if d > POS_TOL else "", f"turned {a:.1f} deg" if a > ANG_TOL else "") if b))
    return new if df.lines.get("prefabs") else None


def diff_lockboxes(df, cl, key, lb_json):
    """interrogation safes (to1-lockbox-t<team>-N markers) -> new teams [[{name, pos, yaw_deg, ...}], [...]] or None (unchanged / none in the pak)"""
    if not cl["lockbox"]:                     # pak saved by an editor build without safe markers (that wiped 3 maps' safes): keep the data, never read it as "all removed"
        return None
    teams_old = (lb_json or {}).get("teams") or [[], []]
    new = [[], []]
    for s in sorted(cl["lockbox"], key=lambda x: (RX_LOCKBOX.match(x["name"]).group(1), int(RX_LOCKBOX.match(x["name"]).group(2)))):
        t = int(RX_LOCKBOX.match(s["name"]).group(1))
        yaw = round(math.degrees(2 * math.atan2(s["quat"][1], s["quat"][3])) % 360.0, 1)
        new[t].append({"pos": r3(s["pos"]), "yaw_deg": yaw})
    if not any(new) and not any(teams_old):
        return None
    out = [[], []]
    for t in (0, 1):
        old = list(teams_old[t]) if t < len(teams_old) else []
        used = set()
        for j, n in enumerate(new[t]):
            best = min(((math.dist(o["pos"], n["pos"]), i) for i, o in enumerate(old) if i not in used), default=None)
            if best and best[0] <= 3.0:
                o = old[best[1]]
                used.add(best[1])
                dy = abs(((o.get("yaw_deg", 0.0) - n["yaw_deg"] + 180.0) % 360.0) - 180.0)
                if best[0] > POS_TOL or dy > 0.2:
                    df.add("lockboxes", f"~ lockbox team {t} {fmt(o)}: " + ", ".join(b for b in (f"moved {best[0]:.2f} m" if best[0] > POS_TOL else "", f"turned {dy:.1f} deg" if dy > 0.2 else "") if b))
                    out[t].append(dict(o, pos=n["pos"], yaw_deg=n["yaw_deg"]))
                else:
                    out[t].append(o)
            else:
                df.add("lockboxes", f"+ added lockbox team {t} at {fmt(n)}")
                out[t].append(dict(n, name=f"lockbox-{t}-{len(out[t])}"))
        for i, o in enumerate(old):
            if i not in used:
                df.add("lockboxes", f"- removed lockbox team {t} {fmt(o)}")
    for t in (0, 1):
        for k, e in enumerate(out[t]):
            e["name"] = f"lockbox-{t}-{k}"
    if not out[0] or not out[1]:
        df.note("a team has no lockbox candidate: the game falls back to its intro spawn point 1")
    return out if df.lines.get("lockboxes") else None


def diff_spots(df, cl, key, is_json, sat=False):
    """-> the new spot list [{pos, quat, family, arts}] or None (leave the item spots alone).
    sat=False: the random- sets of every family but `satchel` (data/<key>-itemspots.json); sat=True: family `satchel` (data/<key>-satchels.json)"""
    cat = "satchels" if sat else "itemspots"
    new = [s for s in cluster_spots(cl["random"]) if (s["family"] == "satchel") == sat]
    old = (is_json or {}).get("spots", [])
    import itemspots as IS
    if not new:
        if old:
            df.note(f"no random- spawners in the pak: the {len(old)} spot(s) of data/{key}-{cat}.json stay as they are "
                    f"(the pak build writes none, the ext spawns them from itemspots.h)")
        return None
    for s in new:
        bad = [a for a in s["arts"] if not IS.item_of(a)]
        if bad:
            df.note(f"item spot {s['family']} at {fmt(s)}: art(s) {', '.join(bad)} are no known item - ignored by the ext (itemspots.py ART_ITEM)")
        if len(s["arts"]) < 2 and not sat:
            df.note(f"item spot {s['family']} at {fmt(s)} has only {len(s['arts'])} candidate: it will only ever give that item (or nothing)")
    pairs = sorted(((math.dist(o["pos"], s["pos"]), i, j) for i, o in enumerate(old) for j, s in enumerate(new)))
    pi, pj, link = set(), set(), []
    for d, i, j in pairs:
        if i in pi or j in pj or d > SPOT_MATCH:
            continue
        pi.add(i)
        pj.add(j)
        link.append((i, j, d))
    out = []
    for i, o in enumerate(old):
        m = [(j, d) for (a, j, d) in link if a == i]
        if not m:
            df.add(cat, f"- removed item spot {o.get('family', '')} at {fmt(o)} ({'/'.join(o['arts'])})")
            continue
        j, d = m[0]
        s = new[j]
        bits = []
        if d > POS_TOL:
            bits.append(f"moved {d:.2f} m")
        if ang(o["quat"], s["quat"]) > ANG_TOL:
            bits.append(f"turned {ang(o['quat'], s['quat']):.1f} deg")
        if sorted(o["arts"]) != sorted(s["arts"]):
            bits.append(f"candidates {'/'.join(o['arts'])} -> {'/'.join(s['arts'])}")
        if bits:
            df.add(cat, f"~ item spot {s['family']} {fmt(o)}: {', '.join(bits)}")
        out.append({k: s[k] for k in ("pos", "quat", "family", "arts")})
    for j, s in enumerate(new):
        if j not in pj:
            df.add(cat, f"+ added item spot {s['family']} at {fmt(s)} ({'/'.join(s['arts'])}; from {', '.join(s['names'])})")
            out.append({k: s[k] for k in ("pos", "quat", "family", "arts")})
    return out if df.lines.get(cat) else None


def run(key, pak_path, spec_path=None, data_dir=None):
    """-> (Diff, plan) where plan has the new spawns / props / kits (None = unchanged)"""
    spec_path, data_dir = spec_path or SPEC, data_dir or DATA
    d = json.load(open(spec_path, encoding="utf-8"))
    m = next((x for x in d["maps"] if x["key"] == key), None)
    if m is None:
        sys.exit(f"no map '{key}' in {spec_path}")
    sp_path = os.path.join(data_dir, f"{key}-spawns.json")
    if not os.path.exists(sp_path) and not m.get("props"):
        sys.exit(f"{key}: pak-driven map (no spawns file, no props): sp_maps.py keeps its pak, nothing to import")
    spawns = json.load(open(sp_path)) if os.path.exists(sp_path) else {}
    dk = DATA_KEY.get(key, key)
    mk_path = os.path.join(data_dir, f"{dk}-medkits.json")
    mk = json.load(open(mk_path)) if os.path.exists(mk_path) else None
    cl = classify(read_pak(pak_path))
    df = Diff()
    gp = os.path.join(data_dir, f"{key}-respawns-gen.json")
    gen = json.load(open(gp)) if os.path.exists(gp) else None
    new_gen = split_generated(df, cl, gen, len(spawns.get("respawns", []))) if spawns else None    # before diff_spawns: the generated points are not the user's
    plan = {"spawns": diff_spawns(df, cl, spawns) if spawns else None, "props": None, "kits": None, "gen": new_gen}
    if not spawns:
        df.note(f"no data/{key}-spawns.json: spawn spots of the pak are not imported")
    plan["props"] = diff_props(df, cl, m.get("props", []))
    plan["prefabs"] = diff_prefabs(df, cl, m.get("prefabs", []))
    lb_path = os.path.join(data_dir, f"{key}-lockboxes.json")
    plan["lockboxes"] = diff_lockboxes(df, cl, key, json.load(open(lb_path)) if os.path.exists(lb_path) else None)
    plan["kits"] = diff_kits(df, cl, dk, mk, mk_path)
    is_path = os.path.join(data_dir, f"{dk}-itemspots.json")
    plan["spots"] = diff_item_spots(df, cl, dk, json.load(open(is_path)) if os.path.exists(is_path) else None)
    st_path = os.path.join(data_dir, f"{dk}-satchels.json")
    plan["satchels"] = diff_spots(df, cl, dk, json.load(open(st_path)) if os.path.exists(st_path) else None, sat=True)
    for s in cl["unknown"]:
        df.note(f"UNRECOGNISED (kept in the pak you saved, not imported): {s['name']} type {s['type']} art '{s['art']}' at {fmt(s)}")
    if len(cl["items"]) != 12 * len(cl["box"]) and cl["box"]:
        df.note(f"{len(cl['items'])} supply box item positions for {len(cl['box'])} boxes (12 each expected): the build rebuilds them from the box pose")
    return df, plan, spawns, m


def apply(key, df, plan, spawns, spec_path=None, data_dir=None):
    spec_path, data_dir = spec_path or SPEC, data_dir or DATA
    if plan["spawns"] is not None and any(df.lines.get(k) for k in ("player", "intro0", "intro1", "respawns", "boxes")):
        with open(os.path.join(data_dir, f"{key}-spawns.json"), "w", newline="\n") as f:
            json.dump(plan["spawns"], f, indent=1)
        print(f"wrote data/{key}-spawns.json")
    if plan.get("gen") is not None:
        with open(os.path.join(data_dir, f"{key}-respawns-gen.json"), "w", newline="\n") as f:
            json.dump(plan["gen"], f, indent=1)
        print(f"wrote data/{key}-respawns-gen.json ({len(plan['gen']['respawns'])} generated respawns left)")
    if df.lines.get("props"):
        d = json.load(open(spec_path, encoding="utf-8"))
        for m in d["maps"]:
            if m["key"] == key:
                m["props"] = plan["props"]
        with open(spec_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(d, f, indent=1)
            f.write("\n")
        print(f"wrote {os.path.basename(spec_path)} props ({len(plan['props'])})")
    if plan.get("lockboxes") is not None:
        dk = key                                  # lockboxes are per MAP key (interrogation_lockboxes SP_ROWS: hospital-ellie), not DATA_KEY
        lp = os.path.join(data_dir, f"{dk}-lockboxes.json")
        d = json.load(open(lp)) if os.path.exists(lp) else {"key": dk, "method": "SceneEditor (hand placed)"}
        d["teams"] = plan["lockboxes"]
        d["hand_placed"] = True
        with open(lp, "w", newline="\n") as f:
            json.dump(d, f, indent=1)
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "interrogation_lockboxes.py")], cwd=os.path.dirname(os.path.dirname(HERE)), check=False)
        print(f"wrote data/{dk}-lockboxes.json ({len(plan['lockboxes'][0])} + {len(plan['lockboxes'][1])} candidates) + tools/interrogation_lockboxes.json + tools/ext/lockboxes.h")
    if plan.get("prefabs") is not None:
        d = json.load(open(spec_path, encoding="utf-8"))
        for m in d["maps"]:
            if m["key"] == key:
                m["prefabs"] = plan["prefabs"]
        with open(spec_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(d, f, indent=1)
            f.write("\n")
        print(f"wrote {os.path.basename(spec_path)} prefabs ({len(plan['prefabs'])})")
    if plan["kits"] is not None:
        import medkits as MK
        dk = DATA_KEY.get(key, key)
        if dk not in MK.INDEX:
            print(f"medkits: {key} is not in medkits.INDEX - kits not written")
        else:
            MK.save_hand(dk, plan["kits"])
            print(f"wrote data/{dk}-medkits.json ({len(plan['kits'])} kits, hand_placed) + tools/ext/medkits.h")


    if plan.get("spots") is not None:
        import itemspots as IS
        dk = DATA_KEY.get(key, key)
        try:
            IS.index_of(dk)
        except KeyError:
            print(f"item spots: {key} is not in medkits.INDEX - spots not written")
        else:
            IS.save(dk, plan["spots"])
            print(f"wrote data/{dk}-itemspots.json ({len(plan['spots'])} spots) + tools/ext/itemspots.h")
    if plan.get("satchels") is not None:
        import itemspots as IS
        dk = DATA_KEY.get(key, key)
        sp = os.path.join(data_dir, f"{dk}-satchels.json")
        d = json.load(open(sp)) if os.path.exists(sp) else {"key": dk, "map_index": MAP_INDEX.get(dk, IS.index_of(dk) if dk in __import__("medkits").INDEX else -1)}
        d["spots"] = plan["satchels"]
        d["hand_placed"] = True
        d.pop("from", None)
        with open(sp, "w", newline="\n") as f:
            json.dump(d, f, indent=1)
        IS.write_header()
        print(f"wrote data/{dk}-satchels.json ({len(plan['satchels'])} spots) + tools/ext/itemspots.h")


def export_kits(key, pak_path, data_dir=None):
    """our kits -> to1-healthkit-N spawners in an editor pak (in place, .bak kept)"""
    data_dir = data_dir or DATA
    kits = json.load(open(os.path.join(data_dir, f"{key}-medkits.json")))["kits"]
    cl = classify(read_pak(pak_path))
    if cl["kits"]:
        sys.exit(f"{pak_path} already has {len(cl['kits'])} medkit spawner(s)")
    ops = {"add_medkits": [{"name": f"to1-healthkit-{i + 1}", "pos": k["pos"], "quat": [0.0, 0.0, 0.0, 1.0]} for i, k in enumerate(kits)]}
    with tempfile.TemporaryDirectory() as td:
        o = os.path.join(td, "ops.json")
        json.dump(ops, open(o, "w"))
        out = os.path.join(td, "out.pak")
        subprocess.run(["pwsh", "-NoProfile", "-File", EDIT, "-In", os.path.abspath(pak_path), "-Out", out, "-Ops", o], check=True)
        import shutil
        shutil.copyfile(pak_path, pak_path + ".bak")
        shutil.copyfile(out, pak_path)
    print(f"{len(kits)} kit(s) added to {pak_path} (backup .bak)")


def export_spots(key, pak_path, out_path=None):
    """our item spots (data/<key>-itemspots.json) -> editor pak: master + item markers per spot, the exact layout editor_prepare writes and spots_from_pak reads back.
    In place with a .bak, or into out_path (the pak stays untouched)."""
    cl = classify(read_pak(pak_path))
    if cl["spot_m"] or cl["spot_i"]:
        sys.exit(f"{pak_path} already has {len(cl['spot_m'])} item spot(s)")
    import editor_prepare
    ops, _ns, _nr, _nk = editor_prepare.ops_for(key)
    ops = {"add_random": [r for r in ops["add_random"] if r["name"].startswith(("random-spot-", "loot-spot-"))]}
    n = sum(1 for r in ops["add_random"] if RX_SPOT_M.match(r["name"]))
    with tempfile.TemporaryDirectory() as td:
        o = os.path.join(td, "ops.json")
        json.dump(ops, open(o, "w"))
        out = os.path.join(td, "out.pak")
        subprocess.run(["pwsh", "-NoProfile", "-File", EDIT, "-In", os.path.abspath(pak_path), "-Out", out, "-Ops", o], check=True)
        import shutil
        if out_path:
            shutil.copyfile(out, out_path)
        else:
            shutil.copyfile(pak_path, pak_path + ".bak")
            shutil.copyfile(out, pak_path)
    print(f"{n} item spot(s) ({len(ops['add_random'])} spawners) written to {out_path or pak_path}" + ("" if out_path else " (backup .bak)"))


def main(a):
    if len(a) >= 3 and a[1] == "--export-kits":
        return export_kits(a[0], a[2])
    if len(a) >= 3 and a[1] == "--export-spots":
        return export_spots(a[0], a[2], a[a.index("--out") + 1] if "--out" in a else None)
    if len(a) < 2:
        print(__doc__)
        return
    df, plan, spawns, _ = run(a[0], a[1])
    df.show()
    if "--apply" in a:
        apply(a[0], df, plan, spawns)
        if df.n:
            print(f"now: python tools/maps/sp_maps.py pak {a[0]}")
    elif df.n:
        print("(dry run: --apply writes it)")


if __name__ == "__main__":
    main(sys.argv[1:])
