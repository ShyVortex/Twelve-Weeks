"""offline checks of the render-settings value encoding + the auto-exposure fix (python tools/part1/test_p1_rsenv.py)"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p1_rsenv as p  # noqa: E402

GAME_RS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "re", "gamebin", "dc1", "render-settings")
T1X = os.path.join(GAME_RS, "t1x.bin")


def test_pack_value():
    assert p.pack_value(1) == bytes.fromhex("0000000001000000")      # stock exposure-method auto
    assert p.pack_value(0) == bytes.fromhex("0000000000000000")      # stock manual
    assert p.pack_value(4.0) == bytes.fromhex("00008040ffffffff")    # stock float cell (light-range-max 4.0)


def test_with_auto_exposure():
    recs = [(p.fnv("lighting:x"), p.pack_value(1.0), bytes(8))]
    out = p.with_auto_exposure(recs)
    k = p.fnv(p.KEY_EXPOSURE_METHOD)
    assert dict((a, b) for a, b, _ in out)[k] == p.pack_value(1)
    assert [r[0] for r in out] == sorted(r[0] for r in out)
    assert p.with_auto_exposure(out) == out                          # already set: untouched
    manual = [(k, p.pack_value(0), bytes(8))]
    assert p.with_auto_exposure(manual) == manual                    # an explicit setting is respected


def test_symbols_in_module():
    if not os.path.exists(T1X):
        print("skip: no extracted t1x.bin"); return
    data = open(T1X, "rb").read()
    k = p.fnv(p.KEY_EXPOSURE_METHOD)
    new, _ = p.add_symbols(data, {"*test-a*": p.with_auto_exposure([(p.fnv("lighting:x"), p.pack_value(2.0), bytes(8))])}, lambda _k: True)
    new, n = p.add_fill_symbol(new, "*test-fill*")
    r = p.DcRs(new)
    for nm in ("*test-a*", "*test-fill*"):
        recs = r.syms[p.fnv(nm)]
        assert [a for a, _, _ in recs] == sorted(a for a, _, _ in recs)
        assert dict((a, b) for a, b, _ in recs)[k] == p.pack_value(1), nm
    assert n == len(p.FILL_SETTINGS)


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
