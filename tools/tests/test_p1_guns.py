"""Offline checks of the Part I gun transplant helpers (no Part I install needed)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import p1_guns  # noqa: E402
import p1_pak  # noqa: E402

# Part I item type ids are FNV-1a-64 of the TLOU2 type names
assert p1_pak.fnv("GEOMETRY_1") == 0x349D779A792F45C1
# material layer slots
t = {"g_tNdFetchBaseColor01Map": 1, "g_tNdFetchNormal01Map": 2, "g_tNdFetchPack_RO_AO_ME_01Map": 3,
     "g_tNdFetchBaseColor02Map": 4, "g_tNdFetchNormal02Map": 5, "g_tNdFetchPack_RO_AO_ME_02Map": 6,
     "g_tNdFetchBaseColor05Map": 7}
assert p1_guns.layer_keys(t, 1) == (1, 2, 3)
assert p1_guns.layer_keys(t, 2) == (4, 5, 6)
assert p1_guns.layer_keys(t, 5) == (7, None, None)
assert p1_guns.layer_keys(t, 3) == (None, None, None)
# the stub mesh_replace gets for emptied host submeshes is one degenerate triangle
s = p1_guns.stub()
assert s["I"].shape == (1, 3) and not s["I"].any()
# the build hook is off by default
import factions_guns  # noqa: E402
assert not factions_guns.p1_guns_enabled()
print("ok  p1_guns helpers")
