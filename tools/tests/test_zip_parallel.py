"""release/build_release.write_zip (big members deflated in parallel) must write exactly the bytes a plain ZipFile.write loop writes
(same members, same order, same headers, same deflate streams), and the zip must test clean.

  python tools/tests/test_zip_parallel.py
"""
import importlib.util
import os
import random
import shutil
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
spec = importlib.util.spec_from_file_location("build_release", os.path.join(ROOT, "release", "build_release.py"))
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)

td = tempfile.mkdtemp(prefix="t2r-zip-test-")
try:
    out = os.path.join(td, "out")
    client = os.path.join(out, "client")
    os.makedirs(os.path.join(client, "sub", "deep"))
    rnd = random.Random(7)
    files = {
        "a.txt": b"hello\n" * 10,
        "zeros.bin": bytes(3 << 20),                                   # mostly zeros (the slim DLL)
        "random.dat": rnd.randbytes(2 << 20),                          # incompressible (the .dat)
        "mixed.dll": (rnd.randbytes(1 << 16) + bytes(1 << 16)) * 20,
        "sub/small.bin": rnd.randbytes(1000),
        "sub/deep/empty.txt": b"",
        "sub/deep/big2.bin": b"abc" * (1 << 20),
    }
    for rel, data in files.items():
        with open(os.path.join(client, *rel.split("/")), "wb") as f:
            f.write(data)
    plain = os.path.join(td, "plain.zip")
    with zipfile.ZipFile(plain, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _, fs in os.walk(client):
            for f in sorted(fs):
                p = os.path.join(base, f)
                z.write(p, os.path.relpath(p, out).replace(os.sep, "/"))
    fast = os.path.join(td, "fast.zip")
    br.write_zip(fast, client, out, big=1 << 20)             # (1 MB threshold: several members go the parallel way)
    a, b = open(plain, "rb").read(), open(fast, "rb").read()
    assert a == b, "parallel zip differs from the plain zip (%d vs %d bytes)" % (len(a), len(b))
    with zipfile.ZipFile(fast) as z:
        assert z.testzip() is None
        for rel, data in files.items():
            assert z.read("client/" + rel) == data, rel
    print("OK: parallel zip == plain zip byte for byte (%d bytes, %d members)" % (len(a), len(files)))
finally:
    shutil.rmtree(td, ignore_errors=True)
