"""Language text tables (text2/<lang>.common) of the mod.

Table = u32 count, count x (u64 sid, u64 blob offset) sorted by sid, then the string blob (NUL terminated UTF-8).

The mod patches eng.common / uke.common in the stage (re/modfs ships both: text ids the revival added, e.g. the HUD message
placeholder id 0xae4c7f46d2c1da94 that winmm's notify writes into, and the ciphers the widgets use). Every OTHER language the game
can be set to lacks those ids: a lookup of a missing id hands back a pointer into the exe's read-only data and winmm's set-text copy
into it crashed the game (Polish text selected). finish_language_tables() puts a <lang>.common of EVERY language of the
game (core.psarc) into the stage - the game's own file plus every id of the staged English table that it lacks, plus the widget
ciphers (loc_widgets: static labels of our pages) with the language's translation (tools/loc/<code>/*.txt) or the English text -
and gives the Polish table the rewritten recipe / prompt texts in Polish (the English table's rewrites mean our multiplayer rules,
not the single-player text)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "loc"))

# engine language code (text2/<code>.common) -> mod language key (tools/loc/<key>/*.txt); other languages get English text for our ciphers
LANGS = {"pol": "pl"}


def load(path):
    d = open(path, "rb").read()
    import struct
    n = struct.unpack_from("<I", d, 0)[0]
    ent = [struct.unpack_from("<QQ", d, 4 + i * 16) for i in range(n)]
    blob = d[4 + n * 16:]
    out = {}
    for sid, off in ent:
        out[sid] = blob[off:blob.index(b"\0", off)]
    return out


def save(path, table):
    import struct
    blob = bytearray()
    offs = {}
    for sid in sorted(table):
        offs[sid] = len(blob)
        blob += table[sid] + b"\0"
    out = bytearray(struct.pack("<I", len(table)))
    for sid in sorted(table):
        out += struct.pack("<QQ", sid, offs[sid])
    open(path, "wb").write(bytes(out + blob))


def selected_langs(available):
    """T2R_LANGS (space / comma separated engine codes, "none" = no extra tables); default every language of the game"""
    v = os.environ.get("T2R_LANGS")
    if v is None:
        return list(available)
    return [x for x in v.replace(",", " ").split() if x in available]


def _translations(code):
    import locdata
    rows = locdata.load(code)
    return {k: v for _, k, v, _, _ in rows}, {rk: rv for _, _, _, rk, rv in rows}


def apply_game_text(pol, eng_orig, pairs, fallback):
    """The Polish table gets our rewritten texts in Polish: dc_data_patches.RECIPE_TEXTS applied to the ORIGINAL English table
    in order (as the in-place patch does), every sid it rewrites gets the translation of the new English text."""
    import dc_data_patches
    work = {s: t.decode("utf-8") for s, t in eng_orig.items()}
    n = 0
    for old, new in dc_data_patches.RECIPE_TEXTS:
        tr = pairs.get(new) or fallback.get(new.strip())
        if tr is None:
            print(f"loc: no Polish text for the rewritten game string: {new[:60]}")
            continue
        if new.endswith(" ") and not tr.endswith(" "):
            tr += " "
        for sid, t in work.items():
            if t.startswith(old):
                work[sid] = new
                if sid in pol:
                    pol[sid] = tr.encode("utf-8")
                    n += 1
    # the tail of the impaled prompt ("..., by ją wyjąć" refers to a feminine arrow): our bolt is masculine
    tail = 0x7ee65fee446c872d
    if tail in pol and eng_orig.get(tail, b"").strip() == b"to remove it":
        pol[tail] = ", by go wyjąć".encode("utf-8")
        n += 1
    return n


def finish_language_tables(stage, paths, order, game, registry):
    """<stage>/text2/<code>.common for every language of the game + manifest entries. Returns the codes written."""
    done = []
    eng_path = os.path.join(stage, "text2", "eng.common")
    if not os.path.exists(eng_path):
        return done
    eng = load(eng_path)
    import dc_data_patches
    import loc_widgets
    cdir = {name: loc_widgets.fnv64(name) for name in registry}
    sys.path.insert(0, os.path.join(TOOLS, "part1"))
    import p1_archive
    try:
        arch = p1_archive.Psarc(os.path.join(game, "build", "pc", "main", "core.psarc"))
    except Exception as e:
        print(f"loc: language tables not staged ({e})")
        arch = None
    codes = ["eng", "uke"]
    if arch is not None:
        avail = sorted(n[len("text2/"):-len(".common")] for n in arch.names if n.startswith("text2/") and n.endswith(".common"))
        codes += [c for c in selected_langs([a for a in avail if a not in ("eng", "uke")])]
    eng_orig = None
    for code in codes:
        rel = "text2/%s.common" % code
        dst = os.path.join(stage, "text2", "%s.common" % code)
        if code in ("eng", "uke"):
            if not os.path.exists(dst):
                continue
            tab = load(dst)
        else:
            try:
                raw = arch.get(rel)
            except Exception as e:
                print(f"loc: {rel} not staged ({e})")
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(raw)
            tab = load(dst)
            if code == "pol" or eng_orig is None:
                pass
        add = {sid: t for sid, t in eng.items() if sid not in tab}
        tab.update(add)
        key = LANGS.get(code)
        tr, raw_pairs = _translations(key) if key else ({}, {})
        for sid, t in add.items():              # the mod's own text ids (option rows ...) in the language's words
            s = t.decode("utf-8", "replace").strip()
            if s in tr:
                tab[sid] = t.decode("utf-8").replace(s, tr[s]).encode("utf-8")
        for name, text in registry.items():
            s = text.strip()
            out = text
            if key and s in tr:
                out = text.replace(s, tr[s])
            tab[cdir[name]] = out.encode("utf-8")
        if code == "pol":
            if eng_orig is None:
                orig_path = os.path.join(stage, "text2", "_eng.orig.tmp")
                open(orig_path, "wb").write(arch.get("text2/eng.common"))
                eng_orig = load(orig_path)
                os.remove(orig_path)
            n = apply_game_text(tab, eng_orig, raw_pairs, tr)
        else:
            n = 0
        save(dst, tab)
        for lst in (paths, order):
            if rel not in lst:
                anchor = "text2/uke.common"
                lst.insert(lst.index(anchor) + 1 if anchor in lst else len(lst), rel)
        done.append(code)
        print(f"loc: {rel}: {len(tab)} entries ({len(add)} mod ids from the English table, {len(registry)} widget ciphers"
              + (f", {n} game strings rewritten" if n else "") + ")")
    return done
