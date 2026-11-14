"""Player weapon anim-overlay modules (dc1/player-specific-weapon-overlays/*.bin): read the anim-overlay-sets, and write
the Part I Shorty / El Diablo overlay modules (T2R_P1_GUNS).

anim-overlay-set (re/uc4-own-movement.md): +0 entries ptr, +8 count, +0x10 layer sid, +0x18 set name sid, +0x20 'player',
+0x28 short name sid, +0x30 keys ptr (the from-names in entry order).  Entry 0x40 bytes: {from sid, to sid, 0 x5, +0x38 kind
(u32) / +0x3a u16 flags}; kind 1 = rename.

TLOU2 ships two leftover TLOU1 modules that are LOADED (listed in modules.bin) but used by no weapon:
player-specific-weapon-overlays/pistol-uber.bin   (key 'pistol-uber',    set anim-overlay-player-specific-weapon-pistol-uber)
player-specific-weapon-overlays/pistol-shotgun.bin (key 'pistol-shotgun', set anim-overlay-player-specific-weapon-pistol-shotgun)
A weapon picks its player overlay through art def +0x180 (a string: the key of a *weapon-specific-overlay-<key>* map).  The
Part I build points El Diablo's / the Shorty's +0x180 at these keys and rewrites the two modules: every entry of the HOST gun's
set (so grips / aim / fire stay the host's) with the reload targets renamed to our carrier clips.  The module keeps its own
symbols (same exports in modules.bin), only its set's entry array / keys / count change (appended data), so the module size
changes and dc_modules.set_size must be called.

  python p1_overlay.py dump <overlay.bin> [more files with name strings]   sets and their renames (names from the game's
                                               sidbase; Part I sids resolve with e.g. the Part I anim pak as extra file)"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(TOOLS, "features"), TOOLS]
from dcfile import DcFile, fnv  # noqa: E402

SET = fnv("anim-overlay-set")
ENTRY = 0x40


def find_sets(d):
    """offsets of the anim-overlay-set objects of a module: an object is preceded by its type sid (the DC object header
    {type sid} right before the data, as dcfile objects are) - found by checking the set layout instead: +0 ptr to an
    entry array of +8 count entries whose from-sids equal the +0x30 key array."""
    out = []
    n = len(d.data)
    for o in range(0, n - 0x38, 8):
        if not (d.is_ptr(o) and d.is_ptr(o + 0x30)):
            continue
        cnt = d.q(o + 8)
        if not 0 < cnt < 4096:
            continue
        ents, keys = d.q(o), d.q(o + 0x30)
        if not (0 <= ents < n and 0 <= keys < n and ents + cnt * ENTRY <= n and keys + 8 * cnt <= n):
            continue
        if all(d.q(ents + ENTRY * i) == d.q(keys + 8 * i) for i in range(min(cnt, 4))):
            out.append(o)
    return out


def entries(d, s):
    ents, cnt = d.q(s), d.q(s + 8)
    return [(d.q(ents + ENTRY * i), d.q(ents + ENTRY * i + 8), bytes(d.data[ents + ENTRY * i:ents + ENTRY * (i + 1)]))
            for i in range(cnt)]


def rewrite(target_path, host_path, host_set, renames, out_path):
    """target module (pistol-uber / pistol-shotgun: keeps its own symbols) whose single set gets the entries of the host
    module's set `host_set` (grips / aim / fire of the host gun), then `renames` {from-name: to-name}: an existing kind-1
    entry with that from-name gets the new target, any other from-name is APPENDED as a kind-1 rename (the overlay
    resolver walks the entries for the first key match; the keys array mirrors the entries).
    Returns (entries, changed, added)."""
    t = DcFile(open(target_path, "rb").read())
    h = DcFile(open(host_path, "rb").read())
    ts, hs = find_sets(t), find_sets(h)
    assert len(ts) == 1, f"{target_path}: expected one overlay set, found {len(ts)}"
    hsets = {h.q(s + 0x18): s for s in hs}
    assert fnv(host_set) in hsets, f"{host_path}: set {host_set} not found"
    src = entries(h, hsets[fnv(host_set)])
    want = {fnv(k): v for k, v in renames.items()}
    template = next(raw for frm, to, raw in src if struct.unpack_from("<H", raw, 0x38)[0] == 1 and
                    not struct.unpack_from("<H", raw, 0x3a)[0])
    # Kind-2 entries (anim trees) can carry POINTERS into their own module: +0x18 the blend func, +0x20 the flip func
    # (script lambdas: anim-node-blend-func / anim-node-flip-func). Copied as raw bytes they kept the HOST's file offsets
    # (e.g. the Beretta's stand^craft-intro blend func 0x49f8), unrelocated in the target = a non-pointer in game: TAB
    # with the Shorty / El Diablo crashed in the anim snapshot (exe+166df47 reading 0x49f8+0x20; exe+1355eb0).
    # A lambda can't move between modules, so such an entry takes the TARGET module's own entry for the same from-name
    # when that one has the same pointer slots (its lambda is in the target: relocated as a pointer slot), else it is
    # left out (the base clip plays without that tree). Every slot that is a pointer in the output is marked.
    tsrc = {frm: (raw, entries_off) for frm, raw, entries_off in
            ((t.q(t.q(ts[0]) + ENTRY * i), bytes(t.data[t.q(ts[0]) + ENTRY * i:t.q(ts[0]) + ENTRY * (i + 1)]), t.q(ts[0]) + ENTRY * i)
             for i in range(t.q(ts[0] + 8)))}
    hents = h.q(hsets[fnv(host_set)])
    blob, keys, slots, changed, seen = bytearray(), bytearray(), [], 0, set()
    dropped, reused = [], []
    for i, (frm, to, raw) in enumerate(src):
        raw = bytearray(raw)
        hp = [o for o in range(0, ENTRY, 8) if h.is_ptr(hents + ENTRY * i + o)]
        if hp:
            own = tsrc.get(frm)
            tp = [o for o in range(0, ENTRY, 8) if own and t.is_ptr(own[1] + o)]
            if own and tp == hp:
                raw = bytearray(own[0])
                slots += [len(blob) + o for o in tp]
                reused.append(frm)
            else:
                dropped.append(frm)
                continue
        if frm in want and struct.unpack_from("<H", raw, 0x38)[0] == 1:
            struct.pack_into("<Q", raw, 8, fnv(want[frm]))
            changed += 1
            seen.add(frm)
        blob += raw
        keys += struct.pack("<Q", frm)
    rewrite.dropped, rewrite.reused = dropped, reused
    added = 0
    for frm, to in want.items():
        if frm in seen:
            continue
        raw = bytearray(template)
        struct.pack_into("<QQ", raw, 0, frm, fnv(to))
        blob += raw
        keys += struct.pack("<Q", frm)
        added += 1
    s = ts[0]
    eo = t.append(bytes(blob), ptr_slots=slots)
    ko = t.append(bytes(keys))
    t.set_ptr(s, eo)
    n = len(blob) // ENTRY
    t.set_q(s + 8, n)
    t.set_ptr(s + 0x30, ko)
    for i in range(n):                       # no host offset may survive: every non-zero +0x10..+0x37 qword is a marked pointer
        for o in range(0x10, 0x38, 8):
            v = t.q(eo + ENTRY * i + o)
            # (a value over 32 bits is a data sid - the hunting rifle's set has trees naming one at +0x30 - not a host file offset)
            assert not v or v >= 1 << 32 or (t.is_ptr(eo + ENTRY * i + o) and v < len(t.data)), \
                f"{out_path}: entry {i} +{o:#x} = {v:#x} is not a relocated pointer"
    open(out_path, "wb").write(t.save())
    return n, changed, added


def sid_names():
    """{sid: string} from every printable string in the game's sidbase.bin (tools/win/ext/dcmain/build of the main
    checkout, or T2R_SIDBASE), cached in <main>/re/part1/sidnames.pkl (git-ignored)"""
    import pickle
    import re
    root = os.path.dirname(TOOLS)
    main_root = root.split(os.sep + ".claude" + os.sep)[0]
    cache = os.path.join(main_root, "re", "part1", "sidnames.pkl")
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    sb = os.environ.get("T2R_SIDBASE") or os.path.join(main_root, "tools", "win", "ext", "dcmain", "build", "sidbase.bin")
    tab = {}
    if os.path.exists(sb):
        for m in re.findall(rb"[\x20-\x7e]{2,200}", open(sb, "rb").read()):
            s = m.decode("latin1")
            tab[fnv(s)] = s
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        pickle.dump(tab, open(cache, "wb"))
    return tab


def main(argv):
    if len(argv) < 3 or argv[1] != "dump":
        print(__doc__)
        return 1
    tab = dict(sid_names())
    for extra in argv[3:]:                     # more files whose printable strings name sids (e.g. a Part I anim pak)
        for m in re.findall(rb"[!-~]{3,200}", open(extra, "rb").read()):
            tab.setdefault(fnv(m.decode("latin1")), m.decode("latin1"))

    def nm(h):
        return tab.get(h, "%#x" % h)
    d = DcFile(open(argv[2], "rb").read())
    for s in find_sets(d):
        print(f"set @{s:#x}: {nm(d.q(s + 0x18))} layer {nm(d.q(s + 0x10))} short {nm(d.q(s + 0x28))}, {d.q(s + 8)} entries")
        for frm, to, raw in entries(d, s):
            print(f"   {nm(frm)} -> {nm(to)}  kind {struct.unpack_from('<H', raw, 0x38)[0]} flags {struct.unpack_from('<H', raw, 0x3a)[0]:#x}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


def rebuild_map(target_path, host_path, host_sym, target_sym, renames, template_key="ellie-fire-fw-fb-hr-walk-into-fire-loop"):
    """The weapon-anim-overlay of a gun (`*weapon-specific-overlay-<key>*`) holds, besides its anim-overlay-set, a compiled MAP
    {n, sorted from-sids*, ptr* to 72-byte weapon-anim-overlay-info {to sid, blend params ...}}: the host gun's has every locomotion /
    carry / cover / crouch grip entry (the hunting rifle's: 1145 keys onto 166 infos), the leftover lever module's only 94.  A rewritten
    set alone left the Frontier with the lever's 94 (idle / sprint / crouch carry poses were wrong).  The target's map
    becomes the host's (info structs copied: they hold no pointers) plus one rename-info per `renames` {from: to} (a copy of the
    template key's info with the to-sid replaced; an existing key is retargeted).  Returns (n keys, n added)."""
    from weapon_clone import find_symbol
    t = DcFile(open(target_path, "rb").read())
    h = DcFile(open(host_path, "rb").read())
    hw, tw = find_symbol(h, host_sym), find_symbol(t, target_sym)
    hm = h.q(hw)
    n, kp, vp = h.q(hm), h.q(hm + 8), h.q(hm + 16)
    keys = [h.q(kp + 8 * i) for i in range(n)]
    assert keys == sorted(keys), "host overlay map is not sorted"
    infos = {}
    blobs = bytearray()
    order = []
    def intern(src_addr, patch_to=None):
        key = (src_addr, patch_to)
        if key not in infos:
            # (the host's LAST info sits 64 bytes before its data end: the copy is zero padded to 72 - unpadded, the next appended array's first
            # qword became its trailing sid; the host itself reads whatever follows the module there)
            raw = bytearray(h.data[src_addr:src_addr + 72].ljust(72, b"\0"))
            for o in range(0, 72, 8):
                assert not h.is_ptr(src_addr + o), "an overlay info holds a pointer"
            if patch_to is not None:
                struct.pack_into("<Q", raw, 0, patch_to)
            infos[key] = len(blobs)
            blobs.extend(raw)
        return infos[key]
    ents = [(k, intern(h.q(vp + 8 * i))) for i, k in enumerate(keys)]        # duplicates kept as they are (30 keys repeat, 16 with other infos)
    tmpl = h.q(vp + 8 * keys.index(fnv(template_key)))
    have = {k for k, _ in ents}
    added = sum(1 for frm in renames if fnv(frm) not in have)
    for frm, to in renames.items():
        k = fnv(frm)
        ents = [e for e in ents if e[0] != k]
        ents.append((k, intern(tmpl, fnv(to))))
    ents.sort(key=lambda e: e[0])                                               # stable: duplicate keys keep their order
    ks = [k for k, _ in ents]
    pairs = [o for _, o in ents]
    bo = t.append(bytes(blobs))
    ko = t.append(b"".join(struct.pack("<Q", k) for k in ks))
    vo = t.append(b"".join(struct.pack("<Q", bo + o) for o in pairs), ptr_slots=[8 * i for i in range(len(ks))])
    mo = t.append(struct.pack("<QQQ", len(ks), ko, vo), ptr_slots=[8, 16], tag="map")
    t.set_ptr(tw, mo)
    open(target_path, "wb").write(t.save())
    return len(ks), added
