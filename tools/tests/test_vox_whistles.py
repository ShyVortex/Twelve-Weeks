"""Offline test of the team voice line tables incl. the Seraphite whistles (tools/features/vox_lines.py).
Run: python tools/tests/test_vox_whistles.py  (data files + generated headers; the archive check needs the game and is skipped without it).
Every index of a (faction, kind) range of the generated header must resolve to a speech key of THAT faction (scr* / mlt*) and gender (m / f),
whistles sit only at the tail of Seraphite ranges (VX_NW / VXF_NW), and every whistle stream must really be in english.psarc."""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "features"))
import vox_lines as v

fails = 0


def ok(c, msg):
    global fails
    print(("ok   " if c else "FAIL ") + msg)
    if not c:
        fails += 1


def parse(path, rng, nw):
    t = open(path).read()
    r = re.search(r"%s\[2\]\[VX_NKINDS\]\[2\] = \{(.*?)\n\};" % rng, t, re.S).group(1)
    rows = [[tuple(map(int, m)) for m in re.findall(r"\{(\d+), (\d+)\}", row)] for row in re.findall(r"\{(.*?)\},", r + ",", re.S) if "{" in row or True]
    rows = [[tuple(map(int, m)) for m in re.findall(r"\{(\d+), (\d+)\}", ln)] for ln in r.strip().split("\n")]
    w = re.search(r"%s\[2\]\[VX_NKINDS\] = \{[^\n]*\n(.*?)\n\};" % nw, t, re.S).group(1)
    ws = [list(map(int, ln.strip().strip("{},").split(","))) for ln in w.strip().split("\n")]
    return rows, ws


male = json.load(open(os.path.join(v.HERE, "data", "vox_lines.json")))
fem = json.load(open(v.FDATA))["lines"]
kinds = [k for k, _ in v.KINDS]
for name, rows, hdr, rng, nw, g in (("male", male, v.HEADER, "VX_RANGE", "VX_NW", "m"), ("female", fem, v.FHEADER, "VXF_RANGE", "VXF_NW", "f")):
    rr, ws = parse(hdr, rng, nw)
    bad = 0
    for f, fac in enumerate(v.FACTIONS):
        for k, kind in enumerate(kinds):
            first, cnt = rr[f][k]
            if not cnt:
                continue
            for i in range(first, first + cnt):
                l = rows[i]
                if l["fac"] != fac or l["kind"] != kind:
                    bad += 1
                    continue
                for sp in l["speech"]:
                    # whistles: the a-voice stream (scrma / scrfa) or the neutral scrm male stream; spoken: <fac><gender><voice>
                    if not (sp.startswith(fac) and (sp[3] in "mf") and (l.get("whistle") or sp[3] == g or sp.startswith("scrm-"))):
                        bad += 1
            nwh = sum(1 for i in range(first, first + cnt) if rows[i].get("whistle"))
            tail = all(rows[i].get("whistle") for i in range(first + cnt - nwh, first + cnt))
            if nwh != ws[f][k] or not tail or (f == 1 and nwh):
                bad += 1
                print("  range", fac, kind, "whistles", nwh, "header", ws[f][k], "tail", tail)
    ok(bad == 0, "%s: every range index resolves to its faction's / gender's streams, whistles only at the tail of Seraphite ranges" % name)
    ids = [i for l in rows for i in l["ids"]]
    ok(len(ids) == len(set(ids)), "%s: line ids unique" % name)

sd = os.path.join(v.GAME, "build", "pc", "main", "speech1")
if os.path.exists(os.path.join(sd, "english.psarc")):
    idx = json.load(open(os.path.join(sd, "english.xvag-index.json")))
    eng = v.psarc_names(os.path.join(sd, "english.psarc"))
    miss = [l["speech"][0] for l in male + fem if l.get("whistle") and (l["speech"][0] not in idx or idx[l["speech"][0]][0] not in eng)]
    ok(not miss, "every whistle stream is in english.psarc (%d missing %s)" % (len(miss), miss[:3]))
print("\n%d failure(s)" % fails)
sys.exit(1 if fails else 0)
