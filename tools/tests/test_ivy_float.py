"""tools/maps/ivy_float.py: geometry helpers, pick parsing, edit entries (synthetic; no game files needed)"""
import os
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "maps"))
import ivy_float as F  # noqa: E402


def main():
    T = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], float)
    P = np.array([[0.2, 0.2, 1], [2, 0, 0], [-1, -1, 0], [0.5, 0.5, 0], [0.5, -1, 0], [2, 2, 0]], float)
    want = [1, 1, 2 ** 0.5, 0, 1, (2 * 1.5 ** 2) ** 0.5]
    assert np.allclose(F.pt_tri_dist(P, T), want), F.pt_tri_dist(P, T)
    assert np.allclose(F.ray_tris(np.array([0.2, 0.2, 5.0]), np.array([0, 0, -1.0]), T), [5.0])
    assert np.isinf(F.ray_tris(np.array([2.0, 2.0, 5.0]), np.array([0, 0, -1.0]), T)).all()
    I = np.array([[0, 1, 2], [2, 1, 3], [4, 5, 6]])
    comps = sorted(sorted(c.tolist()) for c in F.components(I))
    assert comps == [[0, 1], [2]], comps
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("cam 1 2 3 dir 0 0 2 t 0.1 hit 1 2 18 map wilds-houses @10:00:00\n"
                "cam 1 2 3 dir 0 1 0 t -1 map wilds-houses @10:00:01\n"
                "garbage line\n")
    pk = F.parse_picks(f.name)
    os.unlink(f.name)
    assert len(pk) == 2 and pk[0]["dist"] == 15.0 and np.allclose(pk[0]["d"], [0, 0, 1]) and pk[1]["dist"] == 200.0
    assert pk[0]["map"] == "wilds-houses"
    print("ivy_float OK")


if __name__ == "__main__":
    main()
