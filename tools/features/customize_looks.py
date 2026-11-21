"""Composable look records for CUSTOMIZE (re/customize-1117.md "Wearing it in a match").

One look2 record per (faction, sex, body): "t2r-cz-<f><s>-<b>" (f = w / s, s = m / f, b = 0..8: the 8 peer
slots + our own body). Each record is a copy of that (faction, sex)'s default pool look's armoured twin
("<look>-t2r-arm"), with a mesh array and a prop array that hold the SUPERSET of parts:

  - every part of every armoured twin of that (faction, sex)'s pool looks (helmet, vest, pushed copies,
    holsters, back holster, second holsters), in order, the default look's first;
  - every part / prop of every tier-1 item of that (faction, sex) (customize_items.table()), taken from
    the first look2 record in characters.bin that wears it.

The count fields hold the full superset size. t2r-ext (customize.c cz_compose) snapshots the arrays the
first time, then before every spawn writes the chosen subset to the front of the arrays and sets the
counts, and spawns that body with its record's name. Nothing else spawns these names.

Seraphite records also get their own skin tint palette entry (scar-skin-palette); the ext copies the
chosen face's colour into it before the spawn.

Run AFTER patch_armour_looks + patch_look_tints (build_dll.py). T2R_CUSTOMIZE_LOOKS=0 = without.
"""
import os
import struct

import customize_items as ci
import dc_data_patches as dp

ON = os.environ.get("T2R_CUSTOMIZE_LOOKS", "1") != "0"
BODIES = 9                     # = t2r-ext T2R_MAX_PEERS + 1 (T2R_US = 8)
FAC_KEY = {"wlf": "w", "scar": "s"}
POOL = {("wlf", "m"): "wlf", ("scar", "m"): "seraphite"}


def look_name(fac, sex, body):
    """= customize.c cz_look_name()"""
    return "t2r-cz-%s%s-%d" % (FAC_KEY[fac], sex, body)


def pool_looks(fac, sex):
    """the pool looks of one (faction, sex), default first (= customize_items.DEFAULTS comments)"""
    side = "wlf" if fac == "wlf" else "seraphite"
    src = dp.FACTION_LOOKS if sex == "m" else dp.FEMALE_LOOKS
    return list(src[side])


def combos():
    out = [("wlf", "m"), ("scar", "m")]
    if dp.FEMALE_ON and dp.ARMOUR_RIG_FEMALE_ON:
        out += [("wlf", "f"), ("scar", "f")]
    return out


def item_parts(fac, sex):
    """(parts, props) of every tier-1 item of one (faction, sex), first-seen order"""
    T = ci.table()[(fac, sex)]
    parts, props, hide = [], [], []
    for cat in ci.CATS:
        for it in T[cat]:
            if it.get("tier") != 1:
                continue
            for p in it["parts"]:
                if p not in parts:
                    parts.append(p)
            for p in it["props"]:
                if p not in props:
                    props.append(p)
            for p in it.get("hide", ()):
                if p not in hide:
                    hide.append(p)
    return parts, props, hide


def patch_customize_looks(chars_path, modules_path):
    """characters.bin (mod) + modules.bin: the t2r-cz-* records. Returns {name: (n meshes, n props)}."""
    from dcfile import DcFile
    if not ON:
        print("customize looks: off (T2R_CUSTOMIZE_LOOKS=0)")
        return {}
    f = DcFile(open(chars_path, "rb").read())
    D = f.data
    n_ent, ent = struct.unpack_from("<IQ", D, 20)
    assert ent == 40, "characters.bin header layout"
    rows = [struct.unpack_from("<QQQ", D, ent + 24 * k) for k in range(n_ent)]
    T_LOOK, T_ARRAY = dp._fnv("look2"), dp._fnv("array")
    T_MESH, T_PROP = dp._fnv("look2-mesh"), dp._fnv("look2-prop")
    looks = {r[0]: r[2] for r in rows if r[1] == T_LOOK}

    def cstr(p):
        return bytes(f.data[p:f.data.index(b"\0", p)]).decode("latin1")

    def arr(lo, off):
        if not f.is_ptr(lo + off):
            return []
        a, c = f.q(lo + off), struct.unpack_from("<I", f.data, lo + off + 8)[0]
        return [f.q(a + 8 * k) for k in range(c)]

    # every mesh / prop record by name (the first look that wears it)
    mesh_any, prop_any = {}, {}
    for sid, lo in sorted(looks.items(), key=lambda kv: kv[1]):
        for m in arr(lo, 0xa0):
            mesh_any.setdefault(cstr(f.q(m + 0x10)), m)
        for m in arr(lo, 0xb0):
            prop_any.setdefault(cstr(f.q(m + 0x10)), m)

    strings = {}

    def add_str(s):
        strings[s] = len(f.data)
        f.data += s.encode() + b"\0"
        return strings[s]

    def app(blob, slots, tag):
        before = f.strings
        o = f.append(blob, slots, tag=None)
        grow = f.strings - before
        for s in strings:
            strings[s] += grow
        struct.pack_into("<Q", f.data, o, tag)
        return o + 8

    new, info = [], {}
    for fac, sex in combos():
        pl = pool_looks(fac, sex)
        twins = [l + dp.ARMOUR_LOOK_SUFFIX for l in pl]
        for t in twins:
            assert dp._fnv(t) in looks, f"{t} missing (run patch_armour_looks first)"
        base = looks[dp._fnv(twins[0])]
        meshes, mnames, props, pnames = [], [], [], []
        nflip = 0
        for t in twins:
            lo = looks[dp._fnv(t)]
            for m in arr(lo, 0xa0):
                n = cstr(f.q(m + 0x10))
                if n not in mnames:
                    mnames.append(n); meshes.append(m)
            for m in arr(lo, 0xb0):
                n = cstr(f.q(m + 0x10))
                if n not in pnames:
                    pnames.append(n); props.append(m)
        iparts, iprops, ihide = item_parts(fac, sex)
        for n in iparts:
            if n not in mesh_any and n in ci.MOD_PARTS:
                # a mod-built part (customize_items.MOD_PARTS: own actor pak, no record in characters.bin): a copy of its
                # template part's look2-mesh record (region / gore group / attach kept) with the part's name + sid
                tpl = ci.MOD_PARTS[n][1]
                assert tpl in mesh_any, f"{fac} {sex}: template {tpl} of mod part {n} has no look2-mesh record"
                if n not in strings:
                    add_str(n)
                blob, slots = f.copy_block(mesh_any[tpl], dp.LOOK2_MESH_SIZE)
                blob = bytearray(b"\0" * 8 + blob)
                slots = [s + 8 for s in slots]
                assert 8 + 0x10 in slots and 8 + 0x18 not in slots      # +0x10 the name (pointer), +0x18 its sid (hash)
                struct.pack_into("<Q", blob, 8 + 0x10, strings[n])
                struct.pack_into("<Q", blob, 8 + 0x18, dp._fnv(n))
                blob[8 + 0x48] = 0
                if n in ci.HANDTINT_PARTS:
                    # a WLF top's hand-tint copy: the skin on it takes the outfit's palette colour only through a tint KEY in the part's
                    # record (+0x30 -> {count, keys}; the engine colours a part with palette-map[key]). The key object of a Seraphite
                    # lower arm of the same sex is borrowed: its sid is in every face palette patch_customize_tints builds.
                    sx = "female" if n.startswith("t2r-wh-f-") else "male"
                    ksrc = mesh_any["scar-%s-a-jacket-torso-loarm-l" % sx]
                    assert f.is_ptr(ksrc + 0x30) and struct.unpack_from("<I", f.data, f.q(ksrc + 0x30))[0] >= 1, "the Seraphite arm record has no tint key"
                    if 8 + 0x30 not in slots:
                        slots.append(8 + 0x30)
                    struct.pack_into("<Q", blob, 8 + 0x30, f.q(ksrc + 0x30))
                if n.startswith("t2r-kl-") and 8 + 0x30 in slots:
                    # a KELLIE part is baked (skin and cloth toned in its own maps): no tint key, whatever its template carries
                    # (look2-mesh +0x30 -> {count, keys}; a Seraphite arm template would hand it the face tint)
                    nokey = next((f.q(m + 0x30) for m in mesh_any.values()
                                  if f.is_ptr(m + 0x30) and struct.unpack_from("<I", f.data, f.q(m + 0x30))[0] == 0), None)
                    assert nokey is not None, "no look2-mesh record without tint keys to borrow from"
                    struct.pack_into("<Q", blob, 8 + 0x30, nokey)
                mesh_any[n] = app(bytes(blob), slots, T_MESH)
            assert n in mesh_any, f"{fac} {sex}: item part {n} has no look2-mesh record"
            if n not in mnames:
                mnames.append(n); meshes.append(mesh_any[n])
        # a worn item part needs a record shown at spawn, a hide-list part (HOOD UP hides the hood-down mesh, and the other way)
        # one hidden at spawn (+0x48): the ext picks the variant; a missing one is a copy with the flag flipped
        for n, want in [(n, 0) for n in iparts] + [(n, 1) for n in ihide if n in mesh_any]:
            if any(nm == n and (f.data[m + 0x48] != 0) == bool(want) for nm, m in zip(mnames, meshes)):
                continue
            src = mesh_any[n]
            blob, slots = f.copy_block(src, dp.LOOK2_MESH_SIZE)
            blob = bytearray(b"\0" * 8 + blob)
            blob[8 + 0x48] = want
            mnames.append(n); meshes.append(app(bytes(blob), [s + 8 for s in slots], T_MESH))
            nflip += 1
        if fac == "wlf" and ci.TINT_PARTS:
            # the tint inside the stock kits (customize_items.TINT_KITS): the kit's torso / arm parts of these records carry the
            # tint key (their own copies of the records: the game's are shared with looks that have no palette)
            keyed = {}
            for i, n in enumerate(mnames):
                if n in ci.TINT_PARTS:
                    if meshes[i] not in keyed:
                        keyed[meshes[i]] = keyed_mesh(f, app, mesh_any, meshes[i], n, T_MESH)
                    meshes[i] = keyed[meshes[i]]
        for n in iprops:
            if n not in prop_any and n in ci.MOD_PROPS:
                # a mod-built cloth prop (customize_items.MOD_PROPS): a copy of its template's look2-prop record with its own name + sid
                # (the copy dc_data_patches.patch_armour_looks makes for the trimmed coats)
                tpl = ci.MOD_PROPS[n][1]
                assert tpl in prop_any, f"{fac} {sex}: template {tpl} of mod prop {n} has no look2-prop record"
                if n not in strings:
                    add_str(n)
                blob, slots = f.copy_block(prop_any[tpl], dp.LOOK2_PROP_SIZE)
                blob = bytearray(b"\0" * 8 + blob)
                slots = [s + 8 for s in slots]
                assert 8 + 0x10 in slots
                struct.pack_into("<Q", blob, 8 + 0x10, strings[n])
                struct.pack_into("<Q", blob, 8 + 0x18, dp._fnv(n))
                prop_any[n] = app(bytes(blob), slots, T_PROP)
            assert n in prop_any, f"{fac} {sex}: item prop {n} has no look2-prop record"
            if n not in pnames:
                pnames.append(n); props.append(prop_any[n])
        for m in meshes:
            assert f.q(m - 8) == T_MESH
        for m in props:
            assert f.q(m - 8) == T_PROP
        for b in range(BODIES):
            name = look_name(fac, sex, b)
            assert dp._fnv(name) not in looks and len(name) < 0x28, name
            add_str(name)
            a_off = app(b"\0" * 8 + b"".join(struct.pack("<Q", m) for m in meshes), [8 + 8 * k for k in range(len(meshes))], T_ARRAY)
            p_off = app(b"\0" * 8 + b"".join(struct.pack("<Q", m) for m in props), [8 + 8 * k for k in range(len(props))], T_ARRAY) if props else None
            base = looks[dp._fnv(twins[0])]          # (no appends move records: they go before the strings, records stay)
            blob, slots = f.copy_block(base, dp.LOOK2_SIZE)
            blob = bytearray(b"\0" * 8 + blob)
            slots = [s + 8 for s in slots]
            assert 8 + 0x08 in slots and 8 + 0xa0 in slots
            struct.pack_into("<Q", blob, 8 + 0x00, dp._fnv(name))
            struct.pack_into("<Q", blob, 8 + 0x08, strings[name])
            struct.pack_into("<Q", blob, 8 + 0xa0, a_off)
            struct.pack_into("<I", blob, 8 + 0xa8, len(meshes))
            if p_off is not None:
                if 8 + 0xb0 not in slots:
                    slots.append(8 + 0xb0)
                struct.pack_into("<Q", blob, 8 + 0xb0, p_off)
                struct.pack_into("<I", blob, 8 + 0xb8, len(props))
            new.append((name, app(bytes(blob), slots, T_LOOK)))
            info[name] = (len(meshes), len(props))
            # Seraphites: one more record per FACE of the list, "<name>-<face index>", on the SAME arrays (one of them spawns at a
            # time). The skin tint is a palette entry by look NAME that the engine reads once: a record per face is the only tint
            # switch that holds (neither an edited entry nor another palette pointer changed the hands). face_name().
            if fac == "scar" or ci.HANDTINT:
                for k in range(face_records(fac, sex)):
                    vn = face_name(name, k)
                    assert dp._fnv(vn) not in looks and len(vn) < 0x28, vn
                    add_str(vn)
                    vb = bytearray(blob)
                    struct.pack_into("<Q", vb, 8 + 0x00, dp._fnv(vn))
                    struct.pack_into("<Q", vb, 8 + 0x08, strings[vn])
                    new.append((vn, app(bytes(vb), slots, T_LOOK)))
                    info[vn] = (len(meshes), len(props))
        print(f"customize looks: {fac} {sex} x{BODIES} from {twins[0]}: {len(meshes)} parts ({nflip} visibility copies), {len(props)} props")
    anchor = dp.ARMOUR_LOOK_BASES[0]
    out, n_exp, sids = dp._insert_look_rows(f, ent, n_ent, rows, new, chars_path, modules_path, anchor)
    print(f"customize looks: {len(new)} records, characters.bin {len(out)} bytes, exports {n_exp} -> {len(sids)}")
    return info


def keyed_mesh(f, app, mesh_any, m, name, tag):
    """a copy of look2-mesh record m with the skin tint key (+0x30 -> {count, keys}): the key object of a Seraphite lower arm of
    the part's sex - its sid is in every palette the tint patches build. -> the copy's offset"""
    sx = "female" if "-female-" in name or name.startswith("t2r-wh-f-") else "male"
    blob, slots = f.copy_block(m, dp.LOOK2_MESH_SIZE)
    blob = bytearray(b"\0" * 8 + blob)
    slots = [s + 8 for s in slots]
    ksrc = mesh_any["scar-%s-a-jacket-torso-loarm-l" % sx]
    assert f.is_ptr(ksrc + 0x30) and struct.unpack_from("<I", f.data, f.q(ksrc + 0x30))[0] >= 1, "the Seraphite arm record has no tint key"
    if 8 + 0x30 not in slots:
        slots.append(8 + 0x30)
    struct.pack_into("<Q", blob, 8 + 0x30, f.q(ksrc + 0x30))
    return app(bytes(blob), slots, tag)


def patch_pool_hand_tints(chars_path, modules_path, names=None):
    """The tint inside the stock kits (customize_items.TINT_KITS), for the looks that are no CUSTOMIZE record: every look of
    `names` - None = EVERY look of characters.bin (the pool looks, their armoured twins, winter looks, and the game's own SP
    looks of those kits, which MP never spawns but which would be white-handed if anything ever did) - that wears a tint
    kit's torso / arm parts gets
      * keyed copies of those look2-mesh records in its part array (keyed_mesh), and
      * when it has no palette (the WLF have none): one palette of the game's 31 sids, all in the colour of the look's own head
        (data/wlf_face_tint.json by the head part's kit number) - built in the shape of the same sex's Seraphite pool look.
    Without both, the kit's arm skin (now on the tinting material) is drawn untinted: white hands. Run after every look patch.
    -> lines for the build log"""
    from dcfile import DcFile
    if not ci.TINT_PARTS:
        return []
    f = DcFile(open(chars_path, "rb").read())
    T_ARRAY, T_PAL, T_MESH = dp._fnv("array"), dp._fnv("look2-tint-palette"), dp._fnv("look2-mesh")

    def app(blob, slots, tag):
        o = f.append(blob, slots, tag=None)
        struct.pack_into("<Q", f.data, o, tag)
        return o + 8

    def cstr(p):
        return bytes(f.data[p:f.data.index(b"\0", p)]).decode("latin1")

    def arr(lo, off):
        if not f.is_ptr(lo + off):
            return 0, []
        a, c = f.q(lo + off), struct.unpack_from("<I", f.data, lo + off + 8)[0]
        return a, [f.q(a + 8 * k) for k in range(c)]

    looks = dp._look_table(f)
    mesh_any = {}
    for _sid, lo in sorted(looks.items(), key=lambda kv: kv[1]):
        for m in arr(lo, 0xa0)[1]:
            mesh_any.setdefault(cstr(f.q(m + 0x10)), m)
    if names is None:
        names = [dp._cstr(f, f.q(lo + 8)) for _sid, lo in sorted(looks.items(), key=lambda kv: kv[1])]
    done, nopal, keyed = [], [], {}
    for name in dict.fromkeys(names):
        if name.startswith("t2r-cz-") or dp._fnv(name) not in looks:
            continue
        lo = dp._look_table(f)[dp._fnv(name)]
        a, ms = arr(lo, 0xa0)
        parts = [cstr(f.q(m + 0x10)) for m in ms]
        hit = [i for i, n in enumerate(parts) if n in ci.TINT_PARTS]
        if not hit:
            continue
        sex = ci.TINT_PARTS[parts[hit[0]]][0]
        for i in hit:
            if ms[i] not in keyed:
                keyed[ms[i]] = keyed_mesh(f, app, mesh_any, ms[i], parts[i], T_MESH)
            lo = dp._look_table(f)[dp._fnv(name)]
            a = f.q(lo + 0xa0)
            f.set_ptr(a + 8 * i, keyed[ms[i]])
        if struct.unpack_from("<I", f.data, lo + 0xe8)[0]:
            done.append(name + " (keys; its own palette kept)")
            continue
        head = next((n for n in parts if "-head-" in n and f.data[ms[parts.index(n)] + 0x48] == 0), None) or next((n for n in parts if "-head-" in n), "")
        kit = head.split("-head-")[1][:2] if "-head-" in head else ""
        col = ci.TINT_COLOURS[sex].get(kit)
        if col is None:
            nopal.append("%s (head %s)" % (name, head or "?"))
            col = ci.TINT_COLOURS[sex].get("10") or [0.85, 0.78, 0.76]
        # the palette: the same sex's Seraphite pool record's, an entry under each of its sids, all in this colour
        tl = dp._look_table(f)[dp._fnv(look_name("scar", sex, 0))]
        assert struct.unpack_from("<I", f.data, tl + 0xe8)[0] == 1, "no Seraphite palette to take the shape from (run patch_customize_tints first)"
        pal = f.q(f.q(tl + 0xe0))
        assert f.q(pal - 8) == T_PAL
        ea, n = f.q(pal), struct.unpack_from("<I", f.data, pal + 8)[0]
        ents = [f.q(ea + 8 * k) for k in range(n)]
        sids = [f.q(e) for e in ents]
        src = ents[0]
        e_tag = f.q(src - 8)
        cp = f.q(src + 0x10)
        cblob, cslots = f.copy_block(cp, 0x18)
        cblob = bytearray(b"\0" * 8 + cblob)
        struct.pack_into("<3f", cblob, 8, *col)
        cnew = app(bytes(cblob), [x + 8 for x in cslots], f.q(cp - 8))
        new_ents = []
        for sid in sids:
            blob, slots = f.copy_block(src, dp.LOOK2_TINT_PALETTE_SIZE)
            blob = bytearray(b"\0" * 8 + blob)
            struct.pack_into("<Q", blob, 8, sid)
            assert 0x10 in slots
            struct.pack_into("<Q", blob, 8 + 0x10, cnew)
            new_ents.append(app(bytes(blob), [x + 8 for x in slots], e_tag))
        a2 = app(b"\0" * 8 + b"".join(struct.pack("<Q", e) for e in new_ents), [8 + 8 * q for q in range(len(new_ents))], T_ARRAY)
        tl = dp._look_table(f)[dp._fnv(look_name("scar", sex, 0))]
        pal = f.q(f.q(tl + 0xe0))
        blob, slots = f.copy_block(pal, dp.LOOK2_TINT_PALETTE_SIZE)
        blob = bytearray(b"\0" * 8 + blob)
        struct.pack_into("<Q", blob, 8, a2)
        struct.pack_into("<I", blob, 16, len(new_ents))
        p2 = app(bytes(blob), [x + 8 for x in slots], T_PAL)
        pa2 = app(b"\0" * 8 + struct.pack("<Q", p2), [8], T_ARRAY)
        lo = dp._look_table(f)[dp._fnv(name)]
        tl = dp._look_table(f)[dp._fnv(look_name("scar", sex, 0))]
        for o_, v_ in ((0xe0, pa2), (0xf0, f.q(tl + 0xf0))):
            f.set_q(lo + o_, v_)
            f._mark(lo + o_)
        struct.pack_into("<I", f.data, lo + 0xe8, 1)
        struct.pack_into("<I", f.data, lo + 0xf8, struct.unpack_from("<I", f.data, tl + 0xf8)[0])
        done.append("%s (%d parts keyed, palette %s for head %s)" % (name, len(hit), [round(x, 3) for x in col], kit or "?"))
    out = f.save()
    open(chars_path, "wb").write(out)
    dp._set_module_size(modules_path, len(out))
    print(f"hand tint in the kits: {len(done)} looks keyed + paletted (" + "; ".join(done[:16]) + (" ..." if len(done) > 16 else "") + ")")
    if nopal:
        print("hand tint in the kits: NO head colour for " + ", ".join(nopal) + " - face 10's used")
    return done


def verify_hand_tints(chars_path):
    """The sweep behind the tint inside the stock kits: EVERY look of characters.bin that wears a tint kit's torso / arm part
    must have the tint key on each such part and a palette that holds the key's sid - a miss is a look with white hands. Stops
    the build on a miss; prints the count per family. -> {family: looks}"""
    from dcfile import DcFile
    if not ci.TINT_PARTS:
        return {}
    f = DcFile(open(chars_path, "rb").read())
    looks = dp._look_table(f)
    pool = [l for side in dp.FACTION_LOOKS.values() for l in side] + [l for side in dp.FEMALE_LOOKS.values() for l in side]

    def meshes(lo):
        if not f.is_ptr(lo + 0xa0):
            return []
        a, c = f.q(lo + 0xa0), struct.unpack_from("<I", f.data, lo + 0xa8)[0]
        return [f.q(a + 8 * k) for k in range(c)]

    def keys(m):
        if not f.is_ptr(m + 0x30):
            return []
        k = f.q(m + 0x30)
        n = struct.unpack_from("<I", f.data, k)[0]
        return [f.q(f.q(k + 8) + 8 * i) for i in range(n)] if n and f.is_ptr(k + 8) else []

    fam, miss = {}, []
    for _sid, lo in sorted(looks.items(), key=lambda kv: kv[1]):
        name = dp._cstr(f, f.q(lo + 8))
        tp = [(dp._cstr(f, f.q(m + 0x10)), m) for m in meshes(lo)]
        tp = [(n, m) for n, m in tp if n in ci.TINT_PARTS]
        if not tp:
            continue
        sids = set()
        if struct.unpack_from("<I", f.data, lo + 0xe8)[0] and f.is_ptr(lo + 0xe0):
            pal = f.q(f.q(lo + 0xe0))
            ea, k = f.q(pal), struct.unpack_from("<I", f.data, pal + 8)[0]
            sids = {f.q(f.q(ea + 8 * i)) for i in range(k)}
        bad = [n for n, m in tp if not [x for x in keys(m) if x] or [x for x in keys(m) if x and x not in sids]]
        base = name[:-len(dp.ARMOUR_LOOK_SUFFIX)] if name.endswith(dp.ARMOUR_LOOK_SUFFIX) else name
        if name.startswith("t2r-cz-"):
            k = "customize tone records" if name.count("-") == 4 else "customize body records"
        elif base in getattr(dp, "WINTER_LOOKS", {}):
            k = "winter looks"
        elif base in pool:
            k = "pool looks" if base == name else "armoured twins"
        else:
            k = "the game's SP looks"
        fam[k] = fam.get(k, 0) + 1
        if bad:
            miss.append("%s (%s)" % (name, bad[0]))
    print("hand tint in the kits: sweep of every look that wears a tint kit's arm: %d looks, %d misses - %s" % (
        sum(fam.values()), len(miss), ", ".join("%s %d" % kv for kv in sorted(fam.items()))))
    if miss:
        raise SystemExit("hand tint in the kits: looks without the tint key / a palette on a tint kit's part (white hands): " + ", ".join(miss[:12]))
    return fam


def face_name(name, k):
    """the record of body record `name` with face k of its list - Seraphites - or with skin tone group k - WLF
    (customize_compose.c cz_compose builds the same)"""
    return "%s-%d" % (name, k)


def face_records(fac, sex):
    """how many "<body record>-<k>" records a (faction, sex) has: one per face (Seraphites: the game's own palette colour per look),
    one per skin tone group (WLF, customize_items.wlf_tones: the level def holds 512 symbols at most)"""
    if fac == "wlf":
        return len(ci.wlf_tones(sex)[1]) if ci.HANDTINT else 0
    return len(ci.table()[(fac, sex)]["face"])


def patch_customize_tints(chars_path, modules_path):
    """Seraphite t2r-cz-* records: skin tint by the chosen face. One palette per FACE (the game's 30 sids, all in that face's
    colour); the (body, face) records "<body record>-<face index>" point at their face's. Nothing is written at run time:
    the ext spawns the record of the chosen face.
    (an entry's colour rewritten before the spawn, then a palette pointer switched before the spawn - neither
    changed the hands. What does work, shown by the armoured twins since October: a static entry under the look's own name.)"""
    from dcfile import DcFile
    if not ON:
        return []
    f = DcFile(open(chars_path, "rb").read())
    T_ARRAY, T_PAL = dp._fnv("array"), dp._fnv("look2-tint-palette")
    done = []

    def app(blob, slots, tag):
        o = f.append(blob, slots, tag=None)
        struct.pack_into("<Q", f.data, o, tag)
        return o + 8

    for fac, sex in combos():
        looks = dp._look_table(f)
        lo = looks[dp._fnv(look_name(fac, sex, 0))]
        # WLF (the hand-tint copies of the tops): the WLF records have no palette at all - theirs are built in the shape of the
        # same sex's Seraphite record (its palette object, entry blocks, name array), one per face, in the colour of that WLF face
        # (tools/models/wlf_face_tint.py). pfac = the faction the shapes come from.
        wlf = fac == "wlf"
        if wlf and not ci.HANDTINT:
            continue
        pfac = "scar" if wlf else fac
        plo = looks[dp._fnv(look_name(pfac, sex, 0))]
        if not struct.unpack_from("<I", f.data, plo + 0xe8)[0]:
            continue                                    # (no palette to take the shape from)
        base = pool_looks(pfac, sex)[0]
        lo = plo
        assert struct.unpack_from("<I", f.data, lo + 0xe8)[0] == 1
        pal = f.q(f.q(lo + 0xe0))
        assert f.q(pal - 8) == T_PAL
        ea, n = f.q(pal), struct.unpack_from("<I", f.data, pal + 8)[0]
        ents = [f.q(ea + 8 * k) for k in range(n)]
        by_sid = {f.q(e): e for e in ents}
        tint_of = dp.HEAD_SWAP[base][2] if base in dp.HEAD_SWAP else base
        assert dp._fnv(tint_of) in by_sid, f"{base}: no palette entry"
        src = by_sid[dp._fnv(tint_of)]
        e_tag = f.q(src - 8)
        # the tint source of every face of the list, in list order (= the ext's face index): the look its head comes from
        # ("scar-male-head-13" -> "scar-male-13"); a head without a palette entry takes the default's
        fsrc, miss, fcol = [], [], []
        if wlf:                                         # one palette per skin TONE GROUP (customize_items.wlf_tones), in the group's colour
            _of, fcol, miss = ci.wlf_tones(sex)
            fsrc = [src] * len(fcol)
        for it in ([] if wlf else ci.table()[(fac, sex)]["face"]):
            hd = it["parts"][0] if it["parts"] else ""
            fl = hd.replace("-head-", "-") if "-head-" in hd else ""
            if dp._fnv(fl) not in by_sid:
                miss.append(it["label"])
            fsrc.append(by_sid.get(dp._fnv(fl), src))
        # THE RULE (exe+0xb0fa40 / 0x1532a10 / 0x1531dc0): at every spawn the engine
        # turns the look's palettes into a map sid -> colour (at most 128 entries) and tints each part with the colour of the KEY in
        # that part's look2-mesh record (+0x30 -> {count, keys}): the Seraphite lower-arm records hold the sid of the STOCK look
        # they came from, [0, 0, 0, sid]. A key the map lacks = white. The record's own name is never looked up.
        # So: one palette per FACE, with an entry under EVERY stock sid of the game's palette, all in that face's colour - whatever
        # arm record the outfit wears, its key finds the face's colour. A (body, face) record points at its face's palette; a body
        # record keeps the stock palette. (entries under the record's own name, three ways, changed nothing; a single
        # 156-entry palette overran the 128-entry map and ended the game at the first Seraphite spawn.)
        stock_sids = [f.q(e) for e in ents]
        npal = 0
        for k in range(len(fsrc)):
            new_ents = []
            cnew = None
            if wlf:                                     # the face's own colour block: a copy of the source entry's (rgba + int) with new rgb
                cp = f.q(fsrc[k] + 0x10)
                cblob, cslots = f.copy_block(cp, 0x18)
                cblob = bytearray(b"\0" * 8 + cblob)
                struct.pack_into("<3f", cblob, 8, *fcol[k])
                cnew = app(bytes(cblob), [x + 8 for x in cslots], f.q(cp - 8))
            for sid in stock_sids:
                blob, slots = f.copy_block(fsrc[k], dp.LOOK2_TINT_PALETTE_SIZE)
                blob = bytearray(b"\0" * 8 + blob)
                struct.pack_into("<Q", blob, 8, sid)
                if cnew is not None:
                    assert 0x10 in slots
                    struct.pack_into("<Q", blob, 8 + 0x10, cnew)
                new_ents.append(app(bytes(blob), [x + 8 for x in slots], e_tag))
            a2 = app(b"\0" * 8 + b"".join(struct.pack("<Q", e) for e in new_ents), [8 + 8 * q for q in range(len(new_ents))], T_ARRAY)
            lo = dp._look_table(f)[dp._fnv(look_name(pfac, sex, 0))]
            pal = f.q(f.q(lo + 0xe0))
            blob, slots = f.copy_block(pal, dp.LOOK2_TINT_PALETTE_SIZE)
            blob = bytearray(b"\0" * 8 + blob)
            struct.pack_into("<Q", blob, 8, a2)
            struct.pack_into("<I", blob, 16, len(new_ents))
            p2 = app(bytes(blob), [x + 8 for x in slots], T_PAL)
            pa2 = app(b"\0" * 8 + struct.pack("<Q", p2), [8], T_ARRAY)
            lk = dp._look_table(f)
            for b in range(BODIES):
                rec = lk[dp._fnv(face_name(look_name(fac, sex, b), k))]
                if wlf:                                 # (no palette fields in a WLF record yet: array, count, name array, count)
                    for o_, v_ in ((0xe0, pa2), (0xf0, f.q(lo + 0xf0))):
                        f.set_q(rec + o_, v_)
                        f._mark(rec + o_)
                    struct.pack_into("<I", f.data, rec + 0xe8, 1)
                    struct.pack_into("<I", f.data, rec + 0xf8, struct.unpack_from("<I", f.data, lo + 0xf8)[0])
                else:
                    f.set_ptr(rec + 0xe0, pa2)
            if wlf and k == ci.wlf_tones(sex)[0][ci.DEFAULTS[("wlf", sex)].get("face", 0)]:
                # the WLF BODY records (no tone suffix: what cz_compose falls back to when a tone record is missing) take the
                # default face's tone - their kit parts are keyed, and a keyed part without a palette is drawn white
                for b in range(BODIES):
                    rec = lk[dp._fnv(look_name(fac, sex, b))]
                    for o_, v_ in ((0xe0, pa2), (0xf0, f.q(lo + 0xf0))):
                        f.set_q(rec + o_, v_)
                        f._mark(rec + o_)
                    struct.pack_into("<I", f.data, rec + 0xe8, 1)
                    struct.pack_into("<I", f.data, rec + 0xf8, struct.unpack_from("<I", f.data, lo + 0xf8)[0])
            npal += 1
        nrec = BODIES * len(fsrc)
        done.append(f"{fac} {sex} (default tint {tint_of}, {npal} face palettes of {len(stock_sids)} entries, {nrec} face records" + (f", no entry for {miss}" if miss else "") + ")")
    out = f.save()
    open(chars_path, "wb").write(out)
    dp._set_module_size(modules_path, len(out))
    print(f"customize looks: skin tint palettes for {', '.join(done) or 'none'}")
    return done


def verify_customize_looks(chars_path, info):
    """Re-read: every record resolves, its name / sid match, its arrays hold the expected counts and every
    entry is a look2-mesh / look2-prop record; Seraphite records find their own sid in their palette."""
    from dcfile import DcFile
    if not info:
        return
    f = DcFile(open(chars_path, "rb").read())
    looks = dp._look_table(f)
    T_MESH, T_PROP = dp._fnv("look2-mesh"), dp._fnv("look2-prop")
    for name, (nm, npr) in info.items():
        lo = looks.get(dp._fnv(name))
        assert lo is not None, f"{name} not in the entry table"
        assert f.q(lo) == dp._fnv(name) and dp._cstr(f, f.q(lo + 8)) == name, name
        assert struct.unpack_from("<I", f.data, lo + 0xa8)[0] == nm, f"{name}: mesh count"
        a = f.q(lo + 0xa0)
        assert all(f.q(f.q(a + 8 * k) - 8) == T_MESH for k in range(nm)), f"{name}: mesh array"
        if npr:
            assert struct.unpack_from("<I", f.data, lo + 0xb8)[0] == npr, f"{name}: prop count"
            a = f.q(lo + 0xb0)
            assert all(f.q(f.q(a + 8 * k) - 8) == T_PROP for k in range(npr)), f"{name}: prop array"
        if name.startswith("t2r-cz-s") and struct.unpack_from("<I", f.data, lo + 0xe8)[0]:
            # the tint keys of the record's parts (look2-mesh +0x30 -> {count, keys}) must all be in its palette (else: white skin)
            pal = f.q(f.q(lo + 0xe0))
            ea, n = f.q(pal), struct.unpack_from("<I", f.data, pal + 8)[0]
            assert 0 < n <= 128, f"{name}: palette of {n} entries (the engine's map holds 128)"
            have = {f.q(f.q(ea + 8 * k)) for k in range(n)}
            a = f.q(lo + 0xa0)
            for k in range(nm):
                m = f.q(a + 8 * k)
                if f.is_ptr(m + 0x30):
                    ko = f.q(m + 0x30)
                    kc = struct.unpack_from("<I", f.data, ko)[0]
                    if kc and f.is_ptr(ko + 8):
                        for q in range(min(kc, 4)):
                            key = f.q(f.q(ko + 8) + 8 * q)
                            assert not key or key in have or key in dp.TINT_DEFAULT_KEYS, f"{name}: part {dp._cstr(f, f.q(m + 0x10))} tint key {key:x} not in its palette"
    print(f"customize looks: verified {len(info)} records")
