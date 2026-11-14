"""Offline check of havok_convert.remap_proxy_records: the Part I stair-proxy material record (kind 0x103 / 3 items) becomes the stock TLOU2 stair-proxy
record bit for bit ('0112002401024000', flo-mall item 1), other proxy-layer records only gain the stock bytes 4..5 (01 / 02), kind 256 items and T2R_P1_MAT_REMAP=0
are untouched.  Run: python tools/tests/test_p1_proxy_records.py"""
import os
import sys
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import havok_convert as hc  # noqa: E402

P1_STAIR = bytes.fromhex("0112012400004000")       # Part I stair proxy (bookstore / rear / courtyard)
STOCK_STAIR = bytes.fromhex("0112002401024000")    # stock TLOU2 stair proxy (flo-mall, 1188 triangles)
PLAIN = bytes.fromhex("0100000000000000")
WALL = bytes.fromhex("0023013500004000")           # Part I invisible plane -> stock 0023013501024000 (22 triangles in the stock sample)
FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


os.environ.pop("T2R_P1_MAT_REMAP", None)
for kind in (259, 3):
    r = hc.remap_proxy_records(P1_STAIR + WALL, kind)
    check(r[:8] == STOCK_STAIR, "kind %d: Part I stair proxy record == stock stair proxy record" % kind)
    check(r[8:] == bytes.fromhex("0023013501024000"), "kind %d: invisible plane record gains bytes 4..5 = 01 02 only" % kind)
check(hc.remap_proxy_records(P1_STAIR + PLAIN, 256) == P1_STAIR + PLAIN, "kind 256 (static world) records untouched")
check(hc.remap_proxy_records(bytes.fromhex("0126013580004480"), 259) == bytes.fromhex("0126013581024480"), "byte 4 bit 0 is OR-ed (80 -> 81, as in stock)")
os.environ["T2R_P1_MAT_REMAP"] = "0"
check(hc.remap_proxy_records(P1_STAIR, 259) == P1_STAIR, "T2R_P1_MAT_REMAP=0 leaves the records")
print("ALL OK" if not FAILS else "FAILED: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
