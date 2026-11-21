"""offline: lightmap_fix undo records are per pak (sidecar), so parallel map builds cannot lose each other's records (build-165b rerun failure:
'already carries an injected lightmap and no undo record matches it').  Fake paks; no game data."""
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "maps"))
import lightmap_fix as lf  # noqa: E402

d = tempfile.mkdtemp()
donef = os.path.join(d, "done.json")
a, b = os.path.join(d, "a.pak"), os.path.join(d, "b.pak")
for f in (a, b):
    open(f, "wb").write(b"stage:" + f.encode())


def inject(f, load):
    """what apply() does for one pak after `load` (its done dict read at the start), persisted the way apply() persists"""
    before = lf._sha(f)
    buf = open(f, "rb").read() + b"+inject"
    rec = {"before": before, "after": hashlib.sha1(buf).hexdigest(), "sig": "s", "undo": {}}
    lf._drop_rec(f)
    open(f, "wb").write(buf)
    lf._save_rec(f, rec)
    load[os.path.abspath(f)] = rec


# two map processes load at the same time (empty), each injects its own pak
da, db = lf._load_done([a], donef), lf._load_done([b], donef)
inject(a, da)
inject(b, db)

# rerun: each pak is recognised as ours with its record, whatever the other process did
lf._injected_layers = lambda p: ["basis1_lightColor"]
lf.ndpak = type("N", (), {"Pak": staticmethod(lambda f: f)})
for f in (a, b):
    done = lf._load_done([f], donef)
    lf._clean_input(f, done, donef, lambda *x: None)          # must not raise
    assert done[os.path.abspath(f)]["after"] == lf._sha(f)

# an injected pak with no record at all still stops (never inject twice)
os.remove(lf._rec_path(a))
try:
    lf._clean_input(a, lf._load_done([a], donef), donef, lambda *x: None)
    raise AssertionError("expected SystemExit")
except SystemExit:
    pass
print("ok")
