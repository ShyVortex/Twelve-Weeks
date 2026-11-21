"""Offline proof of the ProcessDynLight light binding mirror and the ANIMATED_LIGHTS naming of the Bookstore fire lights (tools/part1/p1_fires.py,
section "light binding"; static RE of tlou-ii.exe).  No game, no GPU, no SceneEditor.
Needs the converted Part I set (T2R_P1_CONV, default re/part1/x/conv-abi-mix5 of the main checkout) and, for the stock control, the game's
world psarcs (T2R_TLOU2_DIR); each part skips itself without its input.

  1. stock control: every light-skel spawner of t2r-nor-scar-burial-parking-lot-ingame binds to its own level's LIGHT_TABLE_1 through
     ANIMATED_LIGHTS (5 of 5: points 0 1 2, spots 0 1), one entry per record.
  2. our own to1-pvp-p1-bookstore level (the package the night-1102 build grafts rt-ortho-fake-son-Shape-1 into) has no LIGHT_TABLE_1: unbound.
  3. converted hun-checkpoint-bookstore: the fake sun binds (projector 0); after add_point_lights the 2 fire records have no entry (the
     engine walk would read past the item); after name_lights all 3 bind, the fake sun to the same record, names_check / loader / lights /
     trailer mirrors clean, the moved item is the one the login table lists.
  4. p1_stage.stage_lights on a scratch stage (spec light-actors[].level = hun-checkpoint-bookstore): staged pak = step 3's bytes; a spec actor
     that does not bind fails the stage; T2R_P1_LIGHT_NAMES=0 stages the points only.
  python tools/tests/test_p1_dynlight.py
"""
import contextlib
import io
import os
import shutil
import struct
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for sub in ("part1", "maps", "models", "features"):
    sys.path.insert(0, os.path.join(TOOLS, sub))
# the main checkout (converted Part I set, level-edit cache): T2R_MAIN_ROOT, this checkout, or the usual path (a separate checkout has neither)
MAIN = next((c for c in (os.environ.get("T2R_MAIN_ROOT"), os.path.dirname(TOOLS).split(os.sep + ".claude" + os.sep)[0], r".")
             if c and os.path.isdir(os.path.join(c, "re", "part1", "x"))), os.path.dirname(TOOLS))
os.environ["T2R_MAIN_ROOT"] = MAIN
os.environ.setdefault("T2R_P1_FIRE_PARTICLES", "0")       # these steps prove the point-record path (the T2R_P1_FIRE_PARTICLES=0 fallback; p1_particles.py is the default)
CONV = os.environ.get("T2R_P1_CONV") or os.path.join(MAIN, "re", "part1", "x", "conv-abi-mix5")
import p1_fires as F  # noqa: E402

FAKE_SUN = "rt-ortho-fake-son-Shape-1"
FIRES = [{"name": "fire-barrel-main", "pos": [118.88, 5.26, 272.6], "light-level": "hun-checkpoint-bookstore",
          "light": {"radius": 4.5, "intensity": 3.2, "vol": 0.02}},
         {"name": "fire-barrel-rear", "pos": [122.93, 0.15, 257.52], "light-level": "hun-checkpoint-bookstore"}]


def raises(fn, *a, has=""):
    try:
        fn(*a)
    except LookupError as e:
        assert has in str(e), (has, str(e))
        return str(e)
    raise AssertionError(f"{fn.__name__}{a[1:]} did not raise")


# 1 ---------------------------------------------------------------- stock control
def stock():
    import json
    import level_edit
    ing = os.path.join(level_edit.CACHE, "p1-fires", F.DONOR_LEVEL + "-ingame.json")
    if not os.path.isfile(ing):
        print("skip  1 (no donor spawner dump %s)" % ing)
        return
    tmp = tempfile.mkdtemp()
    try:
        try:
            base = level_edit.fetch(F.DONOR_LEVEL, tmp, suffixes=("",))[""]
        except SystemExit as e:
            print("skip  1 (%s)" % e)
            return
        d = open(base, "rb").read()
        tp = F._tpak(d)
        (_pg, _off, art, counts), = F.light_tables(tp)
        (_apg, _aoff, ents), = F.animated_lights(tp)
        assert art == "light-skel" and len(ents) == sum(counts.values()) == 5, (art, counts, len(ents))
        got = {}
        for s in json.load(open(ing, encoding="utf-8-sig")):
            if s.get("art") == "light-skel":
                r = F.bind(tp, s["name"])
                got[s["name"]] = (r["kind_name"], r["index"])
        assert sorted(got.values()) == [("point", 0), ("point", 1), ("point", 2), ("spot", 0), ("spot", 1)], got
        assert got["rt-parking-lot-trash-can-Shape-1"] == ("point", 1)       # = DONOR_LIGHT (the can's record 1)
        r = F.bind(tp, "rt-parking-lot-trash-can-Shape-1")
        assert r["record"] == F.DONOR_LIGHT and r["kind_sid"] == 0x73feab3544c345b1, r["record"].hex()
        raises(F.bind, tp, "rt-no-such-light", has="none of the 5")
        print("ok  1 stock %s: 5 light-skel spawners bind (points 0 1 2, spots 0 1), trash can = DONOR_LIGHT, one entry per record" % F.DONOR_LEVEL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# 2 ---------------------------------------------------------------- our own level
def own_level():
    p = os.path.join(TOOLS, "features", "levels", "to1-pvp-p1-bookstore-ingame.pak")
    raises(F.bind, open(p, "rb").read(), FAKE_SUN, has="no LIGHT_TABLE_1")
    print("ok  2 to1-pvp-p1-bookstore-ingame: no LIGHT_TABLE_1 - a light spawner staged there never binds")


# 3 ---------------------------------------------------------------- converted Bookstore
def converted():
    src = os.path.join(CONV, "hun-checkpoint-bookstore.pak")
    d = open(src, "rb").read()
    r0 = F.bind(d, FAKE_SUN)
    assert (r0["kind_name"], r0["index"], r0["entry"], r0["kind_sid"]) == ("projector", 0, 0, 0x23fc142b178b0e63), r0
    recs = [F.light_record(f["pos"], f.get("light")) for f in FIRES]
    pts = F.add_point_lights(d, recs)
    assert not F.check(d, pts, recs)
    r1 = F.bind(pts, FAKE_SUN)
    assert (r1["kind"], r1["index"], r1["record"]) == (r0["kind"], r0["index"], r0["record"])
    names = [F.fire_light_name(f) for f in FIRES]
    raises(F.bind, pts, names[0], has="past the item")
    named = F.name_lights(pts, names)
    bad = F.names_check(pts, named)
    assert not bad, bad
    tp = F._tpak(named)
    (_pg, _off, ents), = F.animated_lights(tp)
    assert [(n, k, i) for n, k, i, _s in ents] == [(FAKE_SUN, 1, 0), (names[0], 0, 0), (names[1], 0, 1)], ents
    assert all(s == F._fnv("light-skel") for *_x, s in ents)
    for k, n in enumerate(names):
        r = F.bind(tp, n)
        assert (r["kind_name"], r["index"], r["record"]) == ("point", k, recs[k]), (n, r["kind_name"], r["index"])
    r2 = F.bind(tp, FAKE_SUN)
    assert (r2["kind"], r2["index"], r2["record"]) == (r0["kind"], r0["index"], r0["record"])
    # the payload as the stock items lay it out: entries back to back, strings from the last entry's +0x1c, item size = entries + strings
    apg, aoff, _e = F.animated_lights(tp)[0]
    size = struct.unpack_from("<I", tp.pages[apg], aoff - 48 + 16)[0]
    assert size == 3 * 0x20 - 4 + sum(len(n) + 1 for n in [FAKE_SUN] + names), size
    assert tp.ptr(apg, aoff) == (apg, aoff + 3 * 0x20 - 4)
    assert F.name_lights(named, []) == named                        # nothing left to name: unchanged
    import p1_convert
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "hun-checkpoint-bookstore.pak")
        open(p, "wb").write(named)
        bad = p1_convert.loader_check(p) + p1_convert.lights_check(p) + p1_convert.trailer_check(p)
        assert not bad, bad
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ok  3 converted Bookstore: fake sun = projector 0 before / after the fire points / after naming; fire points unnamed -> walk past the item;"
          " named: 3 entries, all bind, mirrors clean (%d -> %d bytes)" % (len(pts), len(named)))
    return d, named


# 4 ---------------------------------------------------------------- p1_stage.stage_lights
def stage(d, named):
    import p1_stage
    m = {"key": "p1-bookstore", "part1": {"fires": FIRES, "light-actors": [
        {"donor": "hun-checkpoint-bookstore-ingame", "level": "hun-checkpoint-bookstore", "name": FAKE_SUN}]}}
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "pak68"))
        dst = os.path.join(tmp, "pak68", "hun-checkpoint-bookstore.pak")
        out = io.StringIO()
        open(dst, "wb").write(d)
        with contextlib.redirect_stdout(out):
            p1_stage.stage_lights(tmp, m, "hun-checkpoint-bookstore")
        assert open(dst, "rb").read() == named, "staged bytes differ from name_lights"
        assert "light actor %s binds to hun-checkpoint-bookstore projector record 0 (ANIMATED_LIGHTS entry 0)" % FAKE_SUN in out.getvalue(), out.getvalue()
        bad_m = dict(m, part1=dict(m["part1"], **{"light-actors": [{"level": "hun-checkpoint-bookstore", "name": "rt-not-in-the-table"}]}))
        open(dst, "wb").write(d)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                p1_stage.stage_lights(tmp, bad_m, "hun-checkpoint-bookstore")
            raise SystemExit("an unbound light actor staged")
        except AssertionError as e:
            assert "does not bind" in str(e), e
        os.environ["T2R_P1_LIGHT_NAMES"] = "0"
        try:
            open(dst, "wb").write(d)
            with contextlib.redirect_stdout(io.StringIO()):
                p1_stage.stage_lights(tmp, m, "hun-checkpoint-bookstore")
            recs = [F.light_record(f["pos"], f.get("light")) for f in FIRES]
            assert open(dst, "rb").read() == F.add_point_lights(d, recs)
        finally:
            del os.environ["T2R_P1_LIGHT_NAMES"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ok  4 p1_stage.stage_lights: named pak staged, the spec light actor's binding printed, an unbound actor fails, T2R_P1_LIGHT_NAMES=0 = points only")


if __name__ == "__main__":
    stock()
    own_level()
    if not os.path.isfile(os.path.join(CONV, "hun-checkpoint-bookstore.pak")):
        print("skip  3 4 (no converted Part I set at %s)" % CONV)
    else:
        stage(*converted())
    print("all ok")
