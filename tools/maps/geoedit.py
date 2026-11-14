"""Geometry removals made in the SceneEditor ("Geometry edit" mode) -> level_edit.py edits.

  tools/maps/data/<key>-geoedits.json  {"key", "edits": [{"name", "level", "kind": "tris"|"instance", "asset", "mesh", "tris": [...], "record": "0x...",
                                                           "box": [x0 y0 z0 x1 y1 z1], "collision": "inside"|"centroid"|"overlap"|"none", "active": true}]}
  python geoedit.py show <key>        # the level_edit edits the spec turns into
  python geoedit.py apply <key>       # level_edit.py apply <key> (sp_maps.json edits + these) -> re/maps/level-edit-cache/out/<key>

kind "tris"     render: the listed triangles of ONE submesh of a merged / single-use mesh become degenerate (level_edit render.world cut, cut_tris);
                collision: Havok triangles of the level's -phys.pak inside `box` (mode inside = wholly inside, centroid, overlap = whole primitives that touch it).
kind "instance" render: the placement record is hidden (offsets); collision: the triangles inside the record's oriented box (obb_of, margin 0.05).
kind "morph"    vertices of baked geometry moved (flatten to a height / translate), render + shadow proxies + collision; kind "detach": triangles
                separated and moved/rotated as a piece (render + collision).  Format and limits: level_morph.py docstring.
kind "restore"  (data/<key>-geoedits-restore.json, hand-written, never touched by the editor or snow_fill; applied LAST of everything): the vertices of one wall
                plane of an asset (render streams + collision vertices) are reset to the stock SP paks.  Format: level_morph.py restore_selection.
The spec is applied on top of the ORIGINAL SP level paks every build (sp_maps_build.stage_edits), so it survives re-extraction of the geometry.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def spec_path(key):
    return os.path.join(DATA, f"{key}-geoedits.json")


def load(key):
    p = spec_path(key)
    edits = json.load(open(p, encoding="utf-8")).get("edits", []) if os.path.exists(p) else []
    # snow_fill.py auto entries (seam overlap, door snow tongues): their own file, never written by the editor, applied after the user's edits
    pa = os.path.join(DATA, f"{key}-geoedits-auto.json")
    if os.path.exists(pa):
        edits = edits + json.load(open(pa, encoding="utf-8")).get("edits", [])
    # restore.json: hand-written "put this wall back to the original" entries, read last so they win over every other edit (level_morph applies them last)
    pr = os.path.join(DATA, f"{key}-geoedits-restore.json")
    if os.path.exists(pr):
        edits = edits + json.load(open(pr, encoding="utf-8")).get("edits", [])
    # The editor appends a NEW entry every time the same placement is removed again, so one record can have several entries (jackson-market: up to 4).
    # Its Restore button flips only ONE of them: the viewport shows the prop back while the others stay active and the build kept removing it
    # (restored window pieces were still deleted in game).  Editor = truth: one restored entry restores the record, in every copy.
    off = {(g["level"], g["record"]) for g in edits if g.get("kind") == "instance" and not g.get("active", True)}
    for g in edits:
        if g.get("kind") == "instance" and g.get("active", True) and (g["level"], g["record"]) in off:
            g["active"] = False
    return edits


THIN_COLLISION = re.compile(r"fence|gate|door|railing|barrier", re.I)
THIN_MARGIN = 0.3          # m


def instance_margin(g):
    """How far (m) a removed instance's collision triangles may stick out of its render box and still go with it.  Fences / gates / doors have
    collision posts and hulls that are wider than the drawn mesh (Supermarket hall: the removed security fence kept a 0.2 m x 2.9 m post of
    collision, tags 1793 / 833, 0.23 m outside the render box = a removed gate that still had collision).  Triangles must lie WHOLLY inside the
    grown box (floor kept), so a wall beside the gate is not cut; other props keep the 0.05 m rule."""
    return THIN_MARGIN if THIN_COLLISION.search((g.get("asset") or "") + " " + (g.get("name") or "")) else 0.05


def to_level_edit(g):
    if g.get("kind") in ("morph", "detach", "restore"):     # level_morph.py: vertex flatten / translate and detach-and-transform (applied after the level's ordinary edits)
        return {"name": g["name"], "level": g["level"], "action": "detach" if g["kind"] == "detach" else "morph", "box": g["box"], "geo": g}
    mode = g.get("collision", "inside")
    if g.get("kind") == "instance":
        e = {"name": g["name"], "level": g["level"], "box": g["box"], "action": "remove",
             "render": {"offsets": [g["record"]]},
             "collision": False if mode == "none" else {"obb_of": [g["record"]], "margin": instance_margin(g), "orphans": True}}
    else:
        e = {"name": g["name"], "level": g["level"], "box": g["box"], "action": "remove",
             "render": {"world": True, "instances": False, "cut_name": g.get("asset") or None, "cut_sub": "(^|\|)" + re.escape(g["mesh"]) + "$", "cut_tris": g["tris"]},
             "collision": False if mode == "none" else {"mode": mode, "orphans": True}}
        if not e["render"]["cut_name"]:
            del e["render"]["cut_name"]
    return e


SHADOW_MAX = 8.0           # m: a removed instance with a bigger box (a whole building / wall group) would take neighbours' shadow proxies with it


def shadow_edit(g):
    """The baked shadow proxy (the level's world-space "...tfrag-merge-shadows" submeshes, separate from the drawn mesh) of a removed
    INSTANCE stays behind and keeps casting its shadow (ghost shadow of a removed crate / pallet / shelf).  Companion edit: cut the
    tfrag-merge-shadows triangles (never another prop's own shadow proxy) that lie wholly inside the removed record's box.  Tolerant: most boxes hold none."""
    b = g["box"]
    if g.get("kind") == "tris":                       # a hole cut into a merged wall mesh: the same asset's own shadowProxy submesh keeps the wall's shadow
        if not g.get("asset"):
            return None
        return {"name": g["name"] + " shadow proxy", "level": g["level"], "box": b, "action": "remove", "tolerant": True, "collision": False,
                "render": {"world": True, "instances": False, "skip_shared": True, "cut_name": g["asset"], "cut_sub": "(?i)shadow", "mode": "inside"}}
    if g.get("kind") != "instance" or g.get("collision") == "keep_shadow":
        return None
    if max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) > SHADOW_MAX:
        return None
    return {"name": g["name"] + " shadow proxy", "level": g["level"], "box": b, "action": "remove", "tolerant": True,
            "render": {"world": True, "instances": False, "skip_shared": True, "cut_sub": "tfrag-merge-shadows", "mode": "inside"}, "collision": False}


DECAL_PAD = (0.3, 0.5, 0.3)   # m: a decal placement whose centre lies in a removed prop's box grown by this goes with it
DECAL_MAX = 8.0


def decal_edits(act, log=print):
    """Decal partners (dark leftovers where props were removed).  Decals (`dcl-*` / `*decal*` placements: blood drips, pools,
    smears, projected onto the prop or the floor under it) are separate placement records of the level; a removed prop keeps its decals, which then
    hang in the air / stain the floor where the prop stood.  Every decal placement whose centre lies inside a removed small INSTANCE's box
    (+DECAL_PAD) is hidden with it (one edit per level, explicit offsets).  Measured on jackson-market: no AO / contact-shadow decal or blob mesh exists
    near any removed prop (names dcl-*, *ao*, *contact*, *blob*, *occlusion* checked in supermarket / int / alley); only the blood decals
    dcl-blood-drip / smear / splatter qualify.  Offline only; any failure leaves the edits as they are."""
    try:
        import numpy as np
        sys.path.insert(0, HERE)
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
        import level_edit as le
        import ndpak
        out = {}
        for lv in sorted({g["level"] for g in act if g.get("kind") == "instance"}):
            boxes = [g for g in act if g.get("kind") == "instance" and g["level"] == lv and max(g["box"][3] - g["box"][0], g["box"][4] - g["box"][1], g["box"][5] - g["box"][2]) < DECAL_MAX]
            if not boxes:
                continue
            src = le.fetch(lv, os.path.join(le.CACHE, "src"), None, ("",))[""]
            p = ndpak.Pak(src)
            have = {int(g["record"], 16) for g in act if g.get("kind") == "instance" and g["level"] == lv and g.get("record")}
            for it in le.find_instances(p):
                if it.pak_off in have or it.wlo is None or not any(("dcl-" in n or "decal" in n) for n, _ in it.names):
                    continue
                c = (np.array(it.wlo) + np.array(it.whi)) / 2
                for g in boxes:
                    b = np.array(g["box"], float)
                    if (c >= b[:3] - DECAL_PAD).all() and (c <= b[3:] + DECAL_PAD).all():
                        out.setdefault(lv, {})[it.pak_off] = (it.names[0][0], g["name"], c)
                        break
        edits = []
        for lv, d in out.items():
            for off, (nm, prop, c) in sorted(d.items()):
                log("  decal partner %s @%#x (%.1f %.1f %.1f) goes with %s" % (nm, off, c[0], c[1], c[2], prop))
            edits.append({"name": "decal partners of removed props", "level": lv, "action": "remove", "tolerant": True, "collision": False,
                          "box": [float(x) for x in list(np.min([v[2] for v in d.values()], 0) - 0.5) + list(np.max([v[2] for v in d.values()], 0) + 0.5)],
                          "render": {"offsets": ["%#x" % o for o in sorted(d)]}})
        return edits
    except Exception as e:                                 # never break a build over a cosmetic partner
        log("  decal partners skipped: %r" % (e,))
        return []


def _map_levels(key):
    """the map's level list (sp_maps.json "levels")"""
    try:
        with open(os.path.join(HERE, "sp_maps.json"), encoding="utf-8") as f:
            d = json.load(f)
        m = d.get(key) if isinstance(d.get(key), dict) else next((x for x in d.get("maps", []) if x.get("key") == key), {})
        return list(m.get("levels", []))
    except Exception:
        return []


def edits_for(key):
    """level_edit edits of a map's active geometry removals (appended to its sp_maps.json edits)"""
    import coll_edit                                # Scene Editor Collision edit (data/<key>-colledits.json): its own module, run as the last stage
    act = [g for g in load(key) if g.get("active", True)]
    sh = [e for e in (shadow_edit(g) for g in act) if e]
    # Removed objects still had baked shadows: a removed instance's shadow proxy can sit in a NEIGHBOUR level's
    # tfrag-merge-shadows (the supermarket's wood boards cast from pat-jackson-alley) - the same box cut, tolerant, in the map's other mesh levels
    # (only the mesh levels the map's edits already touch: the near-field ones; the far LODs / snow-only levels carry no prop proxies, checked)
    touched = {g["level"] for g in act}
    others = [lv for lv in _map_levels(key) if lv in touched]
    sh += [dict(e, name=e["name"] + " (" + lv + ")", level=lv) for e in sh if e["render"].get("cut_sub") == "tfrag-merge-shadows"
           for lv in others if lv != e["level"]]
    return [to_level_edit(g) for g in act] + sh + decal_edits(act) + coll_edit.edits_for(key)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "show":
        print(json.dumps({"edits": edits_for(a[1])}, indent=1))
    elif len(a) == 2 and a[0] == "apply":
        sys.path.insert(0, HERE)
        import subprocess
        sys.exit(subprocess.call([sys.executable, os.path.join(HERE, "level_edit.py"), "apply", a[1]]))
    else:
        print(__doc__)
