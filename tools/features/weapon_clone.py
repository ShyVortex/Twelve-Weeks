"""New weapon ids (more weapons will be added, so ids must be real new ones).

A weapon is a set of per-id entries in the DC data files:
  weapon-gameplay.bin  *weapon-gameplay-defs*   map (sorted keys, binary search) -> weapon-gameplay-def
  weapon-art.bin       *weapon-art-defs-hash*   hash-table (n slots, home = sid % n, linear probe)
  weapon-damages.bin   *weapon-damage-settings* map
  weapon-upgrades.bin  *weapon-upgrades*        map (upgrade sets per type)
clone_weapon() adds new_id to each, as a copy of src_id's entry (the def struct copied, its
sub-objects shared unless overridden), using dcfile.DcFile.append so the files grow.

Struct sizes are not stored: an object ends where the next pointed-to object's type tag starts.
"""
import struct
from dcfile import DcFile, fnv


def _targets(d: DcFile):
    """Object boundaries: every type tag qword (the tag values are those found right before
    pointer targets), as sorted offsets of the object start after each tag."""
    import numpy as np
    flags = d.ptr_flags()
    nq = len(d.data) // 8
    if len(d.data) % 8 == 0 or not flags[nq]:        # vectorised (the python loops below are the reference, kept for the odd case)
        qa = np.frombuffer(d.data, dtype="<u8", count=nq)
        t = set(int(x) for x in np.unique(qa[flags[:nq]]))
        tags = {d.q(x - 8) for x in t if 8 <= x < d.strings and not d.is_ptr(x - 8)}
        tags.discard(0)
        starts = set(x for x in t if x < d.strings)
        m = len(range(0, d.strings - 8, 8))
        if m > 0 and tags:
            hit = np.isin(qa[:m], np.array(sorted(tags), dtype=np.uint64)) & ~flags[:m]
            starts.update(int(i) * 8 + 8 for i in np.nonzero(hit)[0])
        del qa
        return sorted(starts)
    t = set()
    for i in range(0, len(d.data), 8):
        if d.is_ptr(i):
            t.add(d.q(i))
    tags = {d.q(x - 8) for x in t if 8 <= x < d.strings and not d.is_ptr(x - 8)}
    tags.discard(0)
    starts = set(x for x in t if x < d.strings)
    for i in range(0, d.strings - 8, 8):
        if not d.is_ptr(i) and d.q(i) in tags:
            starts.add(i + 8)
    return sorted(starts)


def obj_size(d: DcFile, at: int, targets=None) -> int:
    import bisect
    targets = targets or _targets(d)
    k = bisect.bisect_right(targets, at)
    # the next object starts at a pointer target with its type tag (a 64-bit hash) before it;
    # targets inside an object (an inline array, art def +0x1c8) don't end it
    while k < len(targets) and (targets[k] <= at + 8 or d.is_ptr(targets[k] - 8) or
                                d.q(targets[k] - 8) < (1 << 40)):
        k += 1
    return (targets[k] - 8 - at) if k < len(targets) else d.strings - at


def find_symbol(d: DcFile, name: str) -> int:
    """File offset of a top-level symbol's object (entries table at header +0x28: {sid, ?, ptr})."""
    raw = d.data
    n = struct.unpack_from("<I", raw, 0x14)[0]
    base = struct.unpack_from("<Q", raw, 0x18)[0] if struct.unpack_from("<Q", raw, 0x18)[0] else 0x28
    h = fnv(name)
    for i in range(n):
        o = base + i * 24
        if d.q(o) == h:
            return d.q(o + 16)
    raise KeyError(name)


def map_get(d: DcFile, mo: int, key: int):
    n = d.q(mo) & 0xffffffff
    kp, vp = d.q(mo + 8), d.q(mo + 16)
    for i in range(n):
        if d.q(kp + 8 * i) == key:
            return d.q(vp + 8 * i)
    return None


def map_insert(d: DcFile, mo: int, key: int, value: int):
    """Sorted insert: new keys/values arrays appended, the map repointed."""
    n = d.q(mo) & 0xffffffff
    kp, vp = d.q(mo + 8), d.q(mo + 16)
    ks = [d.q(kp + 8 * i) for i in range(n)]
    vs = [d.q(vp + 8 * i) for i in range(n)]
    assert key not in ks, "key exists"
    pairs = sorted(zip(ks + [key], vs + [value]))
    kb = b"".join(struct.pack("<Q", k) for k, _ in pairs)
    vb = b"".join(struct.pack("<Q", v) for _, v in pairs)
    vals_ptr = d.is_ptr(vp)
    nk = d.append(kb, tag="array")
    nv = d.append(vb, ptr_slots=[8 * i for i in range(len(pairs))] if vals_ptr else (), tag="array")
    d.set_q(mo, (d.q(mo) & ~0xffffffff) | (n + 1))
    d.set_ptr(mo + 8, nk)
    d.set_ptr(mo + 16, nv)


def hash_get(d: DcFile, ho: int, key: int):
    n = d.q(ho)
    kp, vp = d.q(ho + 8), d.q(ho + 16)
    for j in range(n):
        i = (key + j) % n
        k = d.q(kp + 8 * i)
        if k == key:
            return d.q(vp + 8 * i)
        if k == 0:
            return None
    return None


def hash_insert(d: DcFile, ho: int, key: int, value: int):
    n = d.q(ho)
    kp, vp = d.q(ho + 8), d.q(ho + 16)
    for j in range(n):
        i = (key + j) % n
        if d.q(kp + 8 * i) == 0:
            d.set_q(kp + 8 * i, key)
            d.set_q(vp + 8 * i, value)
            d._mark(vp + 8 * i)
            return i
        assert d.q(kp + 8 * i) != key, "key exists"
    raise RuntimeError("hash table full")


def copy_obj(d: DcFile, at: int, tag_name: str = None, min_size: int = 0) -> int:
    """Shallow copy of the object at `at` (type tag kept), returns the copy's offset. min_size:
    the type's real size when known - obj_size stops at the next pointer target, and a pointer
    into the object (e.g. +0x1c8 of an art def) cut copies short (garbage past the copy)."""
    size = max(obj_size(d, at), min_size)
    blob, slots = d.copy_block(at, size)
    tag = d.q(at - 8)
    new = d.append(struct.pack("<Q", tag) + blob, ptr_slots=[s + 8 for s in slots])
    return new + 8


def replace_sids_deep(d: DcFile, root: int, repl: dict, depth: int = 6, _seen=None) -> int:
    """Copy-on-write: returns `root` or a copy of it where every qword sid in repl (inside the
    object or any object below it, `depth` levels of pointers) is replaced. Objects that contain
    nothing to replace stay shared."""
    targets = _seen if _seen is not None else {"t": _targets(d)}
    # obj_size can undershoot (art +0x150 > +0x58 has muzzle flash fields at +0xc8..+0xe8 past
    # its guess): scan / copy at least 0x100 - extra bytes only change our own copies
    size = max(obj_size(d, root, targets["t"]), min(0x100, d.strings - root))
    changed = {}
    hit = False
    for o in range(0, size, 8):
        a = root + o
        if d.is_ptr(a):
            p = d.q(a)
            if depth > 0 and 0 < p < d.strings:
                np_ = replace_sids_deep(d, p, repl, depth - 1, targets)
                if np_ != p:
                    changed[o] = np_
        elif d.q(a) in repl:
            hit = True
    if not hit and not changed:
        return root
    new = copy_obj(d, root, min_size=size)
    targets["t"] = _targets(d)
    for o in range(0, size, 8):
        if not d.is_ptr(new + o) and d.q(new + o) in repl:
            d.set_q(new + o, repl[d.q(new + o)])
    for o, p in changed.items():
        d.set_ptr(new + o, p)
    return new


# weapon art def: +0x140 -> struct whose +0x18 is the gun's audio set name (which sound banks
# load when the gun is held: "galil" for the Galil, the gun id for most)
ART_AUDIO = (0x140, 0x18)
ART_DEF_SIZE = 0x1d8        # weapon-art-def (next object's tag at +0x1d8; +0x1d0 is read by exe+0x1168fbb)


def _joint_entries(d: DcFile, jo: int):
    n = d.q(jo) & 0xFFFFFFFF
    e = d.q(jo + 8)
    return [(d.q(e + 16 * i), struct.unpack_from("<i", d.data, e + 16 * i + 8)[0]) for i in range(n)]


def _write_joints(d: DcFile, jo: int, entries):
    """Point weapon-mods-joint-array `jo` at a new (sid, i32 visible) entry array."""
    blob = b"".join(struct.pack("<QiI", sid, vis, 0) for sid, vis in entries)
    at = d.append(blob)
    d.set_ptr(jo + 8, at)
    d.set_q(jo, (d.q(jo) & ~0xFFFFFFFF) | len(entries))


def _merge(entries, changes):
    out = list(entries)
    for name, vis in changes.items():
        k = fnv(name)
        for i, (sid, _) in enumerate(out):
            if sid == k:
                out[i] = (sid, vis)
                break
        else:
            out.append((k, vis))
    return out


def joints_copy(d: DcFile, v: int, changes: dict) -> int:
    """Copy of weapon-upgrade-bundles value `v` whose default joint visibility (weapon-visual-mods
    -> weapon-mods-joint-array) has `changes` {joint name: 0/1} applied; v itself is untouched."""
    nv = copy_obj(d, v)
    vm = copy_obj(d, d.q(nv + 8))
    d.set_ptr(nv + 8, vm)
    jo = copy_obj(d, d.q(vm))
    d.set_ptr(vm, jo)
    _write_joints(d, jo, _merge(_joint_entries(d, jo), changes))
    return nv


def set_default_joints(path: str, weapon: str, changes: dict):
    """weapon-upgrades.bin: apply {joint name: 0/1} to `weapon`'s default joint visibility."""
    d = DcFile(open(path, "rb").read())
    mo = find_symbol(d, "*weapon-upgrade-bundles*")
    v = map_get(d, mo, fnv(weapon))
    jo = d.q(d.q(v + 8))
    _write_joints(d, jo, _merge(_joint_entries(d, jo), changes))
    open(path, "wb").write(d.save())


def add_bundles_entry(path: str, weapon: str, template: str, joints: dict):
    """weapon-upgrades.bin: give `weapon` a *weapon-upgrade-bundles* entry (it had none): a copy of
    the template weapon's (pick one without upgrade bundles) whose default joints are `joints`."""
    d = DcFile(open(path, "rb").read())
    mo = find_symbol(d, "*weapon-upgrade-bundles*")
    assert map_get(d, mo, fnv(weapon)) is None, f"{weapon} already has upgrade bundles"
    v = copy_obj(d, map_get(d, mo, fnv(template)))
    d.set_q(v, fnv(weapon))
    vm = copy_obj(d, d.q(v + 8))
    d.set_ptr(v + 8, vm)
    jo = copy_obj(d, d.q(vm))
    d.set_ptr(vm, jo)
    _write_joints(d, jo, [(fnv(k), b) for k, b in joints.items()])
    map_insert(d, mo, fnv(weapon), v)
    open(path, "wb").write(d.save())


def add_scope_entry(path: str, weapon: str, look_from: str, scope_from: str, bundle: str = "scope"):
    """weapon-upgrades.bin: give `weapon` (a clone made with upgrades=False) another gun's scope.
    *weapon-upgrades*: `weapon` -> scope_from's upgrade-type map (shared: the scope bundle's ref
    array names (type, level) entries of it, e.g. the zoom). *weapon-upgrade-bundles*: a copy of
    look_from's entry (its model's default joint visibility) whose bundle array holds only
    scope_from's `bundle` record (0x70 bytes), its joint changes emptied (the scope_from model's
    joints, not ours - our scope is part of the mesh). t2r-ext applies the bundle (El Diablo:
    player-weapon-upgrade-apply-bundle "scope"), then the scope button zooms like the hunting
    pistol's."""
    d = DcFile(open(path, "rb").read())
    mo = find_symbol(d, "*weapon-upgrades*")
    assert map_get(d, mo, fnv(weapon)) is None, f"{weapon} already has upgrade sets"
    map_insert(d, mo, fnv(weapon), map_get(d, mo, fnv(scope_from)))
    bo = find_symbol(d, "*weapon-upgrade-bundles*")
    assert map_get(d, bo, fnv(weapon)) is None, f"{weapon} already has upgrade bundles"
    sv = map_get(d, bo, fnv(scope_from))
    ba = d.q(sv + 0x10)
    arr = d.q(ba + 8)
    rec = next((arr + i * 0x70 for i in range(d.q(ba) & 0xffffffff) if d.q(arr + i * 0x70) == fnv(bundle)), None)
    assert rec is not None, f"{scope_from} has no {bundle} bundle"
    blob, slots = d.copy_block(rec, 0x70)
    nrec = d.append(blob, ptr_slots=slots, tag="array")
    # the record's visual mods (+0x20): an empty joint list (keep its shader blends)
    vm = copy_obj(d, d.q(nrec + 0x20))
    d.set_ptr(nrec + 0x20, vm)
    jo = copy_obj(d, d.q(vm))
    d.set_ptr(vm, jo)
    d.set_q(jo, d.q(jo) & ~0xFFFFFFFF)
    nba = copy_obj(d, ba)
    d.set_ptr(nba + 8, nrec)
    d.set_q(nba, (d.q(nba) & ~0xFFFFFFFF) | 1)
    v = copy_obj(d, map_get(d, bo, fnv(look_from)))
    d.set_q(v, fnv(weapon))
    d.set_ptr(v + 0x10, nba)
    map_insert(d, bo, fnv(weapon), v)
    open(path, "wb").write(d.save())
    print(f"weapon-upgrades: {weapon} + {scope_from}'s {bundle} bundle (look of {look_from})")


def set_art_strings(path: str, changes: dict, only_if_set: bool = False):
    """weapon-art.bin: {(weapon, offset in the art def): new string} (e.g. +0x70 the HUD icon).
    The def is shared by nobody else (clones have their own copies). only_if_set: skip fields that are
    null in the def (a string there would switch a feature on that the gun never had)."""
    d = DcFile(open(path, "rb").read())
    mo = find_symbol(d, "*weapon-art-defs-hash*")
    for (weapon, off), text in changes.items():
        v = hash_get(d, mo, fnv(weapon))
        if v is None or (only_if_set and not d.q(v + off)):
            continue
        at = d.append(text.encode() + bytes(1))
        d.set_ptr(v + off, at)
    open(path, "wb").write(d.save())


def set_art_sfx(path: str, weapon: str, sfx: dict, audio_from: str = None):
    """weapon-art.bin: the sounds of an EXISTING weapon `weapon` (not a clone): its art def gets its own copy with the sound names
    in `sfx` ({old: new}) replaced (copy-on-write: clones made earlier keep theirs) and, with audio_from "=<set>", that audio set
    (same literal-name route as clone_weapon)."""
    d = DcFile(open(path, "rb").read())
    mo = find_symbol(d, "*weapon-art-defs-hash*")
    key = fnv(weapon)
    v = hash_get(d, mo, key)
    nv = copy_obj(d, v, min_size=ART_DEF_SIZE)
    nv = replace_sids_deep(d, nv, {fnv(a): fnv(b) for a, b in sfx.items()})
    if audio_from:
        assert audio_from.startswith("=")
        sub = d.q(nv + ART_AUDIO[0])
        nsub = copy_obj(d, sub)
        at = d.data.find(bytes(1) + audio_from[1:].encode() + bytes(1), d.strings) + 1
        assert at > 0, f"string {audio_from[1:]} not in weapon-art"
        d.set_ptr(nsub + ART_AUDIO[1], at)
        d.set_ptr(nv + ART_AUDIO[0], nsub)
    n = d.q(mo)
    kp, vp = d.q(mo + 8), d.q(mo + 16)
    for j in range(n):
        i = (key + j) % n
        if d.q(kp + 8 * i) == key:
            d.set_ptr(vp + 8 * i, nv)
            break
    else:
        raise RuntimeError("weapon not in the art hash")
    open(path, "wb").write(d.save())
    print(f"weapon-art: {weapon} sounds {sorted(sfx.values())}" + (f", audio set {audio_from[1:]}" if audio_from else ""))


def set_art_model(path: str, weapon: str, actor: str, muzzle=None):
    """weapon-art.bin: `weapon` is drawn with the actor `actor` (art def +0x0 / +0x38 = the model name, like
    clone_weapon's `model`), and muzzle = (x, y, z) moves its muzzle point (firearm-art-def +0x108, effects start there).
    The firearm-art def / vector are copied first (a clone made earlier shares them)."""
    d = DcFile(open(path, "rb").read())
    mo = find_symbol(d, "*weapon-art-defs-hash*")
    v = hash_get(d, mo, fnv(weapon))
    at = d.append(actor.encode() + bytes(1))
    d.set_ptr(v + 0x0, at)
    d.set_ptr(v + 0x38, at)
    if muzzle is not None:
        fa = copy_obj(d, d.q(v + 0x128))
        d.set_ptr(v + 0x128, fa)
        vec = copy_obj(d, d.q(fa + 0x108))
        d.set_ptr(fa + 0x108, vec)
        struct.pack_into("<3f", d.data, vec, *muzzle)
    open(path, "wb").write(d.save())
    print(f"weapon-art: {weapon} model = {actor}" + (f", muzzle {muzzle}" if muzzle else ""))


def add_ammo_users(path: str, src: str, new: str) -> int:
    """weapon-gameplay.bin *ammo-to-weapon-array* ({u32 count, pad, array*} of {ammo sid, weapon
    sid}): which guns an ammo pickup / inventory ammo feeds. `new` gets every ammo of `src` -
    without it a cloned gun never takes ammo pickups (no ammo from boxes)."""
    d = DcFile(open(path, "rb").read())
    ao = find_symbol(d, "*ammo-to-weapon-array*")
    n, arr = d.q(ao) & 0xffffffff, d.q(ao + 8)
    pairs = [(d.q(arr + 16 * i), d.q(arr + 16 * i + 8)) for i in range(n)]
    add = [(a, fnv(new)) for a, w in pairs if w == fnv(src) and (a, fnv(new)) not in pairs]
    if not add:
        return 0
    blob = b"".join(struct.pack("<QQ", a, w) for a, w in pairs + add)
    na = d.append(blob, tag="array")
    d.set_q(ao, (d.q(ao) & ~0xffffffff) | (n + len(add)))
    d.set_ptr(ao + 8, na)
    open(path, "wb").write(d.save())
    return len(add)


CLONES = {}        # new weapon id -> source id (clone_weapon with upgrades), for patch_upgrade_icons


UPGRADE_ICONS_TOP = 0x26631b6c0175ed76     # weapon-upgrade-icons.bin top symbol: map weapon sid -> (map upgrade-combo bits -> icon path slot)


def find_symbol_sid(d: DcFile, sid: int) -> int:
    n = struct.unpack_from("<I", d.data, 0x14)[0]
    for i in range(n):
        o = 0x28 + i * 24
        if d.q(o) == sid:
            return d.q(o + 16)
    raise KeyError(hex(sid))


def patch_upgrade_icons(src_path: str, dst_path: str, icons: dict, clones: dict = None):
    """weapon-upgrade-icons.bin (base game): the HUD icon a weapon shows once upgraded (per upgrade combination: mag, brl, scp, ...).
    Layout: header table {sid, type, ptr}; top symbol 0x26631b6c0175ed76 = map weapon sid -> sub-map (count, u32 combo keys, ptr values);
    each value points at a slot [tag 'string'][ptr to the path string].  Every weapon of `icons` {id: path} that has an entry, and every
    clone of such a weapon (clones {new: src}, chains followed), gets all its slots re-pointed at its own icon (fresh slots / sub-map,
    nothing shared with the stock weapons).  Returns [(weapon, source entry, [(combo bits, old path, new path)])]."""
    d = DcFile(open(src_path, "rb").read())
    top = find_symbol_sid(d, UPGRADE_ICONS_TOP)
    root = lambda w: root(clones[w]) if clones and w in clones else w
    n0 = d.q(top) & 0xffffffff
    have = {d.q(d.q(top + 8) + 8 * i) for i in range(n0)}
    log = []
    for w in sorted(icons):
        src = root(w)
        if fnv(src) not in have:
            continue
        icon = icons[w]
        sub = map_get(d, top, fnv(src))
        n = d.q(sub) & 0xffffffff
        kp, vp = d.q(sub + 8), d.q(sub + 16)
        ent, slots = [], []
        iat = d.append(icon.encode() + bytes(1))
        for i in range(n):
            slot = d.q(vp + 8 * i)
            old = d.q(slot)
            ent.append((struct.unpack_from("<I", d.data, kp + 4 * i)[0], bytes(d.data[old:d.data.index(bytes(1), old)]).decode(), icon))
            slots.append(d.append(struct.pack("<QQ", d.q(slot - 8), iat), ptr_slots=[8]) + 8)
        nvp = d.append(b"".join(struct.pack("<Q", s) for s in slots), ptr_slots=[8 * i for i in range(n)], tag="array")
        nsub = d.append(struct.pack("<QQQQ", d.q(sub - 8), d.q(sub), kp, nvp), ptr_slots=[16, 24]) + 8
        if fnv(w) in have:
            tk, tv = d.q(top + 8), d.q(top + 16)
            for i in range(n0):
                if d.q(tk + 8 * i) == fnv(w):
                    d.set_ptr(tv + 8 * i, nsub)
        else:
            map_insert(d, top, fnv(w), nsub)
        log.append((w, src, ent))
    open(dst_path, "wb").write(d.save())
    return log


def clone_weapon(dc1: str, src: str, new: str, sfx: dict = None, audio_from: str = None,
                 sound_mode: int = None, model: str = None, joints: dict = None, muzzle_dz: float = None,
                 upgrades: bool = True):
    """Add weapon id `new` as a copy of `src` to the weapon files in `dc1` (paths are the staged
    files; caller updates modules.bin sizes). sfx: {old sound name: new sound name} replaced
    inside the new weapon's art def; audio_from: a gun whose audio set the new one loads (needed
    when sfx names another gun's sounds)."""
    import os
    sk, nk = fnv(src), fnv(new)
    out = {}
    if upgrades:
        CLONES[new] = src
    for fname, sym, kind in (("weapon-gameplay", "*weapon-gameplay-defs*", "map"),
                             ("weapon-art", "*weapon-art-defs-hash*", "hash"),
                             ("weapon-damages", "*weapon-damage-settings*", "map"),
                             ("weapon-upgrades", "*weapon-upgrades*", "map"),
                             ("weapon-upgrades", "*weapon-upgrade-bundles*", "map")):
        if fname == "weapon-upgrades" and not upgrades:
            continue                               # another model: the source's joints don't exist on it
        path = os.path.join(dc1, fname + ".bin")
        d = DcFile(open(path, "rb").read())
        mo = find_symbol(d, sym)
        get = map_get if kind == "map" else hash_get
        v = get(d, mo, sk)
        if v is None:
            print(f"clone {new}: {src} has no {sym} entry, skipped")
            continue
        if fname == "weapon-upgrades":
            nv = v                                 # upgrade sets / visual bundles: shared
            if sym == "*weapon-upgrade-bundles*" and joints:
                nv = joints_copy(d, v, joints)     # own default joint visibility (e.g. the can)
        else:
            nv = copy_obj(d, v, min_size=ART_DEF_SIZE if fname == "weapon-art" else 0)
            if fname == "weapon-art" and sfx:
                nv = replace_sids_deep(d, nv, {fnv(a): fnv(b) for a, b in sfx.items()})
            if fname == "weapon-art" and audio_from:
                sub = d.q(nv + ART_AUDIO[0])
                nsub = copy_obj(d, sub)
                if audio_from.startswith("="):     # a literal audio set name (= an actor name)
                    name = audio_from[1:].encode() + bytes(1)
                    at = d.data.find(bytes(1) + name, d.strings) + 1
                    assert at > 0, f"string {audio_from[1:]} not in {fname}"
                    d.set_ptr(nsub + ART_AUDIO[1], at)
                else:
                    other = hash_get(d, mo, fnv(audio_from))
                    d.set_ptr(nsub + ART_AUDIO[1], d.q(d.q(other + ART_AUDIO[0]) + ART_AUDIO[1]))
                d.set_ptr(nv + ART_AUDIO[0], nsub)
            if fname == "weapon-art" and sound_mode is not None:
                # weapon-sound-def +0x0: 1 single-shot events, 2 automatic (looping) shot events
                # (the Galil's / MPX5's); an automatic event under 1 never plays
                sub = d.q(nv + ART_AUDIO[0])
                if sub == d.q(v + ART_AUDIO[0]):
                    sub = copy_obj(d, sub)
                    d.set_ptr(nv + ART_AUDIO[0], sub)
                d.set_q(sub, sound_mode)
            if fname == "weapon-art" and muzzle_dz:
                # firearm-art-def (art +0x128) +0x108: muzzle point (vector x, y, z, 1); effects
                # (flash, smoke) start there - moved forward to the end of a suppressor can
                fa = d.q(nv + 0x128)
                if fa == d.q(v + 0x128):
                    fa = copy_obj(d, fa)
                    d.set_ptr(nv + 0x128, fa)
                vec = copy_obj(d, d.q(fa + 0x108))
                d.set_ptr(fa + 0x108, vec)
                z = struct.unpack_from("<f", d.data, vec + 8)[0]
                struct.pack_into("<f", d.data, vec + 8, z + muzzle_dz)
            if fname == "weapon-art" and model:
                # art def +0x0 / +0x38: the gun's model (actor) name
                at = d.append(model.encode() + bytes(1))
                d.set_ptr(nv + 0x0, at)
                d.set_ptr(nv + 0x38, at)
        (map_insert if kind == "map" else hash_insert)(d, mo, nk, nv)
        open(path, "wb").write(d.save())
        out[fname] = os.path.getsize(path)
    k = add_ammo_users(os.path.join(dc1, "weapon-gameplay.bin"), src, new)
    print(f"weapon {new}: cloned from {src} ({', '.join(out)}), {k} ammo type(s)")
    return out


def copy_art_fields(path: str, dst: str, src: str, offsets):
    """weapon-art.bin: copy the raw 8-byte fields at `offsets` of weapon src's art def into dst's
    (e.g. +0x180 / +0x188: the player overlay set names - which gun's grip / aim animations)."""
    d = DcFile(open(path, "rb").read())
    mo = find_symbol(d, "*weapon-art-defs-hash*")
    a, b = hash_get(d, mo, fnv(dst)), hash_get(d, mo, fnv(src))
    for off in offsets:
        q = d.q(b + off)
        if q:
            d.set_ptr(a + off, q)
        else:
            d.set_q(a + off, 0)
    open(path, "wb").write(d.save())


def set_art_ints(path: str, changes: dict):
    """weapon-art.bin: {(weapon, offset in the art def): new u32} (e.g. +0x1c0 the reticle type:
    4 shotgun brackets, 2 circle)."""
    d = DcFile(open(path, "rb").read())
    mo = find_symbol(d, "*weapon-art-defs-hash*")
    for (weapon, off), v in changes.items():
        struct.pack_into("<I", d.data, hash_get(d, mo, fnv(weapon)) + off, v)
    open(path, "wb").write(d.save())
