"""Openings and extra collision for a map, kept OUT of sp_maps.json and out of the Scene Editor's own files (jackson-market window).

  tools/maps/data/fixes/openings-<key>.json
    {"openings": [{"seal": "<name of an added collision box of sp_maps.json 'add' edits>", "name": "...",
                   "along": [a0, a1],          # world range of the hole along the seal's long axis (z for a yaw 90 box, x for yaw 0)
                   "y": [y0, y1]}],            # world height range of the hole
     "edits": [ <ordinary level_edit edits (e.g. {"action": "add", "boxes": [...]}) appended after the map's own> ]}

An opening replaces the seal box by up to four boxes around the hole (left / right / below / above).  A seal that the Scene Editor removed
('Remove this seal', data/<key>-sealremove.json) is simply gone and its openings are skipped.  Used by level_edit.spec_edits.
"""
import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MIN = 0.02                      # m: pieces thinner than this are dropped


def path(key):
    return os.path.join(HERE, "data", "fixes", "openings-%s.json" % key)


def load(key):
    p = path(key)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"openings": [], "edits": []}


def split_box(b, along, y):
    """box dict {name, center, size [w, h, t], yaw, like} with a hole -> list of box dicts around it (yaw 0: w along x; yaw 90: w along z)"""
    yaw = int(round(b.get("yaw", 0.0))) % 180
    if yaw not in (0, 90):
        raise SystemExit("openings: seal %r has yaw %s (only 0 / 90)" % (b.get("name"), b.get("yaw")))
    ax = 0 if yaw == 0 else 2
    c = list(b["center"])
    w, h, t = b["size"]
    lo, hi = c[ax] - w / 2, c[ax] + w / 2
    ylo, yhi = c[1] - h / 2, c[1] + h / 2
    a0, a1 = max(along[0], lo), min(along[1], hi)
    y0, y1 = max(y[0], ylo), min(y[1], yhi)
    if a0 >= a1 or y0 >= y1:
        return [b]                                           # the hole misses the box
    out = []

    def piece(tag, p0, p1, q0, q1):                          # along range p0..p1, height range q0..q1
        if p1 - p0 < MIN or q1 - q0 < MIN:
            return
        n = copy.deepcopy(b)
        n["name"] = "%s %s" % (b["name"], tag)
        cc = list(c)
        cc[ax] = (p0 + p1) / 2
        cc[1] = (q0 + q1) / 2
        n["center"] = [round(v, 4) for v in cc]
        n["size"] = [round(p1 - p0, 4), round(q1 - q0, 4), t]
        n["like"] = list(b.get("like") or c)                 # the material of the wall around it
        out.append(n)

    piece("(left of opening)", lo, a0, ylo, yhi)
    piece("(right of opening)", a1, hi, ylo, yhi)
    piece("(below opening)", a0, a1, ylo, y0)
    piece("(above opening)", a0, a1, y1, yhi)
    return out


def apply(key, edits):
    """the map's edits (sealremove already applied) with the openings cut into their seals, plus the file's extra edits"""
    f = load(key)
    if not f.get("openings") and not f.get("edits") and not f.get("colledits"):
        return edits
    edits = copy.deepcopy(edits)
    for op in f.get("openings", []):
        hit = 0
        for e in edits:
            if e.get("action") != "add" or not e.get("boxes"):
                continue
            nb = []
            for b in e["boxes"]:
                if b.get("name") == op["seal"]:
                    nb += split_box(b, op["along"], op["y"])
                    hit += 1
                else:
                    nb.append(b)
            e["boxes"] = nb
        if not hit:
            print("  openings: seal %r of %r not in the map's edits (removed?) - skipped" % (op["seal"], op.get("name")))
    col = [{"name": g.get("name", "collision edit"), "level": g["level"], "action": "colledit", "col": g} for g in f.get("colledits", []) if g.get("active", True)]
    return edits + copy.deepcopy(f.get("edits", [])) + col         # colledit entries: coll_edit.py, the last stage of level_edit.build_edits


def featuredb(key):
    """{"edges": [...], "posts": [], "outlines": []} of the file's "featuredb" (world coordinates; sp_maps.py pak merges it into the map pak's FEATURE_DB_2) or None"""
    fd = load(key).get("featuredb")
    return {"edges": fd.get("edges", []), "posts": fd.get("posts", []), "outlines": fd.get("outlines", [])} if fd else None
