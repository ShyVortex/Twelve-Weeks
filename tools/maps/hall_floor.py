"""Walkable ground for the new Supermarket hall (jackson-market: the passage opened by removing the stone wall pat-walls @0x959390 and its
gate, x -509.2..-506.0, z 282.5..289.5, floor y ~18.2), as collision that follows the RENDER snow like the stock snow collision does.

Why (players got stuck in that collision / fell through it): the wall removals took the Havok ground triangles under them,
the old surface patches (pocket_surface.py) follow an older snow state, and stray triangles of the removed props / snow
mounds (up to 0.5 m over the render snow, down to ledges at x -506.3) are left standing.  Stock snow collision = the render snow mesh decimated ~12x
and lifted 5 cm (measured on the courtyard: collision vertex 5 cm over a render vertex, median area 0.49 m2 vs 0.04 m2, collision 6 cm over the render).

  data/jackson-market-colledits-auto.json (read by coll_edit.edits_for, applied after the Scene Editor's colledits, never written by the editor):
    clear  x2 levels  the collision stray in the hall volume (centroid in the wall footprint, inside the ground rect, ground-0.8 .. ground+2.2 m, not a tall wall)
    ground            a grid of the render snow height (+5 cm, quadtree 0.65 -> 0.3 m cells (tol 4 cm: the host item's tagfile page is capped at 1 MB)) over the footprint + overlap under the neighbouring ground, stock snow material
  The ground reads the render paks of the pipeline stage (coll_edit.apply_all), so it follows later Scene Editor snow edits; only the entries here change
  when the hall changes.

  python hall_floor.py write      # (re)write the auto file
  python hall_floor.py check <out-dir>   # ray grid / holes / ledges of a finished build (<out-dir>/colledit, /morph) vs the render snow; CPU only
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
KEY = "jackson-market"
FOOT = (-509.2, 282.5, -506.0, 289.5)                    # x0, z0, x1, z1: the removed wall's box (data: geoedits "pat-walls", cinderblocks, gate props)
BOX = [-509.25, 282.45, -506.25, 290.7]                 # clear: triangle centroids (the east building wall, x -506.33..-505.94, stays)
WBOX = [-511.2, 282.1, -505.78, 291.9]                  # the whole ground area: up-facing triangles (and tiny slivers) up to 0.8 m over the render snow are replaced by the new ground; walls stay (not up-facing / tall)
RECT = [-515.0, 282.1, -505.92, 291.9]                   # ground: hall footprint + ~1.2 m overlap W / N (S edge stays at z 282.1: south of it, x < -509.1, there is no stock ground - a void edge, no new lip) under the neighbouring snow ground (a stock triangle that straddles the edge stays: the overlap is at most the stock's own lift), ends under the east wall (faces x -506.14 / -505.91)
JUNK = [([-506.6, 281.0, -506.25, 282.6], "floating mound fragments at the east wall's south pier"), ([-506.12, 285.5, -505.75, 287.0], "stray slivers in the east wall at the old trash pile")]   # x0, z0, x1, z1: every triangle of area < 0.1 m2 inside (the walls' own faces are far bigger and stay)
WEDGE = [[-506.09899, 17.854, 285.13, -506.02789, 18.2146, 285.8509, -506.09899, 18.85333, 283.76145], [-506.09899, 17.854, 285.13, -505.9904, 18.23121, 285.74398, -506.02789, 18.2146, 285.8509], [-506.09899, 17.854, 285.13, -505.799, 17.854, 285.13, -505.9904, 18.23121, 285.74398], [-506.18999, 18.83, 283.61, -506.02789, 18.2146, 285.8509, -506.18999, 18.92, 283.61], [-506.18999, 18.83, 283.61, -506.18999, 18.83, 285.26, -506.02789, 18.2146, 285.8509], [-506.18999, 18.83, 285.26, -506.09, 18.83, 285.26, -506.02789, 18.2146, 285.8509], [-506.09, 18.83, 283.61, -506.09, 18.92, 283.61, -506.02789, 18.2146, 285.8509], [-506.09, 18.83, 283.61, -506.02789, 18.2146, 285.8509, -506.09, 18.83, 285.26]]                                       # the fan of a slanted wedge along the east wall (z 283.6 .. 285.85, protrudes 5 cm from the wall face), exact triangles
SLIV = [-511.5, 282.7, -508.8, 285.8]                   # a vertex edit collapsed alley ground triangles onto y 17.0 (under the floor, useless)
PLAT = [-514.5, 288.4, -510.4, 294.0]                   # an invisible 0.7 m high collision slab (flat top y 18.63) where the render snow is flat (y 17.9 .. 18.1)
PLAT_TRIS = [[-512.73583, 18.63268, 292.99579, -511.97754, 18.63268, 293.76583, -510.56991, 18.63268, 292.3797], [-512.73583, 18.63268, 292.99579, -510.56991, 18.63268, 292.3797, -511.32821, 18.63268, 291.60964], [-511.32821, 18.63268, 291.60964, -512.83177, 18.63268, 290.08283, -512.73583, 18.63268, 292.99579], [-511.32821, 18.63268, 291.60964, -511.32821, 17.69218, 291.60964, -512.83177, 17.69218, 290.08283], [-511.32821, 18.63268, 291.60964, -512.83177, 17.69218, 290.08283, -512.83177, 18.63268, 290.08283], [-510.56991, 18.63268, 292.3797, -510.56991, 17.69218, 292.3797, -511.32821, 17.69218, 291.60964], [-510.56991, 18.63268, 292.3797, -511.32821, 17.69218, 291.60964, -511.32821, 18.63268, 291.60964], [-512.83177, 18.63268, 290.08283, -514.27415, 18.63268, 288.61804, -514.23936, 18.63268, 291.46894], [-512.83177, 18.63268, 290.08283, -514.23936, 18.63268, 291.46894, -512.73583, 18.63268, 292.99579], [-512.73583, 18.63268, 292.99579, -514.23936, 18.63268, 291.46894, -514.23936, 17.69218, 291.46894], [-512.73583, 18.63268, 292.99579, -514.23936, 17.69218, 291.46894, -512.73583, 17.69218, 292.99579], [-511.97754, 17.69218, 293.76583, -510.56991, 17.69218, 292.3797, -510.56991, 18.63268, 292.3797], [-511.97754, 17.69218, 293.76583, -510.56991, 18.63268, 292.3797, -511.97754, 18.63268, 293.76583], [-512.73583, 17.69218, 292.99579, -511.97754, 17.69218, 293.76583, -511.97754, 18.63268, 293.76583], [-512.73583, 17.69218, 292.99579, -511.97754, 18.63268, 293.76583, -512.73583, 18.63268, 292.99579], [-514.27415, 17.69218, 288.61804, -514.27415, 18.63268, 288.61804, -512.83177, 18.63268, 290.08283], [-514.27415, 17.69218, 288.61804, -512.83177, 18.63268, 290.08283, -512.83177, 17.69218, 290.08283]]
HILL = [-496.0, 271.0, -490.2, 275.8]                    # the courtyard-side snow hill (render snow_chunk_render): collision rebuilt from the render snow like the stock does (decimated, +5 cm)
CRECT = [-511.2, 282.1, -505.78, 291.9]                  # clear: triangles wholly inside this are removable (the stale 0.5 m pocket strip along the east wall reaches x -505.8)
MESHES = ["alley_snow_ground", "snow_10cm"]              # the render snow of the courtyard / lane (submesh name parts)
RENDER = ["pat-jackson-supermarket", "pat-jackson-alley"]
SNOW = "3200000001020000"                                # collision material record of the stock snow ground of the lane just south of the hall (supermarket item 1, 96 tris at z 273.6..283.9; the courtyard's own snow records sit in items without room for new keys)

# "Leftover gate and bush collisions" in the hallway you still can't pass (dev ray presses id 8 / 9, tools/maps/ray_lookup.py --cast): collision left standing where the
# render was removed.  All in pat-jackson-supermarket, props item 9 (tag 0xc1 = box shapes, 0x301 = bush hull).  Found with the offline cast along the two rays and checked against
# the removed-instance geoedits (every one lies inside the box of a removed prop and has no render surface within 0.35 m):
LEFT_TRASH = [[-507.30053, 20.93976, 277.44135, -507.53126, 20.93976, 277.22903, -507.53126, 17.92563, 277.22903],
[-507.30053, 20.93976, 277.44135, -507.53126, 17.92563, 277.22903, -507.30053, 17.92563, 277.44135],
[-506.67088, 17.92563, 277.47083, -506.48906, 17.92563, 277.80249, -506.48906, 20.93976, 277.80249],
[-506.67088, 17.92563, 277.47083, -506.48906, 20.93976, 277.80249, -506.67088, 20.93976, 277.47083],
[-507.30053, 17.92563, 277.44135, -506.92157, 17.92563, 277.38244, -506.92157, 20.93976, 277.38244],
[-507.30053, 17.92563, 277.44135, -506.92157, 20.93976, 277.38244, -507.30053, 20.93976, 277.44135],
[-506.92157, 17.92563, 277.38244, -506.67088, 17.92563, 277.47083, -506.67088, 20.93976, 277.47083],
[-506.92157, 17.92563, 277.38244, -506.67088, 20.93976, 277.47083, -506.92157, 20.93976, 277.38244],
[-506.48906, 17.92563, 277.80249, -506.09400, 17.92563, 277.77806, -506.09400, 20.93976, 277.77806],
[-506.48906, 17.92563, 277.80249, -506.09400, 20.93976, 277.77806, -506.48906, 20.93976, 277.80249],
[-507.53126, 20.93976, 277.22903, -508.39736, 20.93976, 277.32126, -508.39736, 17.92563, 277.32126],
[-507.53126, 20.93976, 277.22903, -508.39736, 17.92563, 277.32126, -507.53126, 17.92563, 277.22903],
[-508.39736, 20.93976, 277.32126, -509.01083, 20.93976, 277.39524, -509.01083, 17.92563, 277.39524],
[-508.39736, 20.93976, 277.32126, -509.01083, 17.92563, 277.39524, -508.39736, 17.92563, 277.32126]]     # 4 trash bin / bag boxes at x -508.8..-506.2, z 277.3..277.8 (1.5 m tall): ray 8 stopped here at 1.48 m (geoedits 77-85 removed their render)
LEFT_BUSH = [[-503.61546, 17.92563, 276.01342, -503.47975, 17.92563, 276.89274, -503.40887, 18.96929, 277.05167],
[-503.61546, 17.92563, 276.01342, -503.40887, 18.96929, 277.05167, -503.56521, 18.96929, 276.06025],
[-502.64097, 18.09678, 277.46793, -502.65096, 18.96929, 276.95879, -503.40887, 18.96929, 277.05167],
[-502.64097, 18.09678, 277.46793, -503.40887, 18.96929, 277.05167, -503.25054, 18.09678, 277.60228],
[-503.27736, 17.92563, 277.59896, -502.64097, 17.92563, 277.46793, -502.64097, 18.09678, 277.46793],
[-503.27736, 17.92563, 277.59896, -502.64097, 18.09678, 277.46793, -503.25054, 18.09678, 277.60228],
[-503.25054, 18.09678, 277.60228, -503.40887, 18.96929, 277.05167, -503.47975, 17.92563, 276.89274],
[-503.25054, 18.09678, 277.60228, -503.47975, 17.92563, 276.89274, -503.27736, 17.92563, 277.59896],
[-502.65096, 18.96929, 276.95879, -502.66084, 18.96929, 276.00830, -503.56521, 18.96929, 276.06025],
[-502.65096, 18.96929, 276.95879, -503.56521, 18.96929, 276.06025, -503.40887, 18.96929, 277.05167]]      # dead-bush boxes at x -503.5..-502.9, z 276.3..277.6 (geoedits 97-99 removed bush-a-dead-lrg-a)
LEFT_HULL = [[-501.95047, 19.93376, 275.94467, -501.75316, 19.76809, 275.95396, -501.52910, 19.33405, 274.94494],
[-501.95047, 19.93376, 275.94467, -501.52910, 19.33405, 274.94494, -501.99389, 19.55926, 274.98176],
[-501.50903, 18.97092, 275.10824, -501.52910, 19.33405, 274.94494, -501.75316, 19.76809, 275.95396],
[-501.50903, 18.97092, 275.10824, -501.75316, 19.76809, 275.95396, -501.74801, 19.26967, 275.95221],
[-501.74801, 19.26967, 275.95221, -501.56671, 18.62597, 275.94987, -501.50903, 18.97092, 275.10824]]      # the bush hull's last sides on the yard ramp (0.17-0.45 m over the render snow, 1.6 m over the lane): ray 9 stopped here at 1.93 m
STRIP = [-509.2, 275.95, -505.95, 282.1]
YARD = [-509.2, 273.2, -502.5, 275.95]
FLOOR_ASSETS = ["snow", "terrain-chunk", "-floor"]      # render assets that do NOT count as 'drawn' for a steep triangle standing over the floor (the snow render lies under every fin: keys 0x3a00 / 0x6400 were never cleared)
LMESH = ["alley_snow_ground", "snow_10cm", "ext-terrain-chunk", "snow_chunk_render"]
WEXT = [-515.0, 282.85, -509.9, 291.9]                    # the lane's window-entry side west of the old hall rect: the stock alley ground floats 0.2-0.35 m over the render snow there (the 'collision block' at the post office window)
RAMPE = [-502.5, 272.4, -494.4, 276.2]                   # east part of the ramp ground: stock collision floats 0.2 m over the render there (up-facing triangles only)
NEXIT = [-509.2, 291.9, -505.95, 295.0]                   # 2 m past the hall's north end (the exit on that side): same ground, blends to the stock ground at z 295
RAMPC = [-502.5, 272.95, -500.3, 275.9]                   # clear box of the ramp (the bush hull on it)
RAMP = [-502.5, 272.4, -496.0, 276.2]                    # ramp ground, up to the hill's ground (HILL starts at x -496.0)
LANE = [-515.0, 272.4, -494.4, 295.0]                      # union of the lane entries' rects (window side, hall, strip, yard, ramp, north exit)
SMOOTH = {"rect": [-516.0, 272.6, -496.0, 297.0], "open": 0.4, "slope": 0.5}   # the lane's walkable field: ridges under 0.8 m removed (the removed wall's footing), slope <= 0.5, ONE field for every lane entry (no seams)                    # the yard ramp (render: pat-supermarket-ext-terrain-chunk-c, geoedit 73 'snow' lowered it under the old stock collision): ground follows the render again


# lane blockers: collision inside the hallway volume (0.05-2 m over the floor) with NO render surface within 0.25 m (leftovers of the removed trash pile, security fence, bush hull); found by the offline scan of the finished paks
LEFT_LANE = [[-507.30667, 18.86646, 276.64097, -507.32426, 18.86637, 276.65049, -507.32611, 18.86975, 276.63763],
[-507.37214, 18.86629, 277.10138, -507.16756, 18.95947, 277.00983, -507.30314, 19.11423, 277.06843],
[-506.65348, 20.24982, 276.23404, -506.65348, 20.24982, 276.23357, -506.67347, 20.24982, 276.23404],
[-507.38506, 18.83121, 277.04642, -507.38271, 18.83214, 277.04981, -507.36747, 18.83130, 277.03690],
[-507.33939, 18.82910, 276.81025, -507.34125, 18.83249, 276.79741, -507.32181, 18.82920, 276.80075],
[-504.52903, 20.02396, 273.82636, -504.52903, 20.02396, 273.80637, -504.53009, 20.02396, 273.80639],
[-507.58749, 19.02097, 277.15660, -507.63375, 18.98236, 277.07614, -507.39648, 18.83384, 277.06617],
[-507.33171, 18.85415, 276.70414, -507.35115, 18.85744, 276.70082, -507.34929, 18.85406, 276.71366],
[-507.01886, 19.65623, 276.94449, -507.00504, 19.61183, 276.99985, -506.96582, 19.59245, 277.03396],
[-507.01886, 19.65623, 276.94449, -506.96582, 19.59245, 277.03396, -506.97355, 19.64655, 276.95336],
[-507.01886, 19.65623, 276.94449, -507.03781, 19.64030, 276.96106, -507.00504, 19.61183, 276.99985],
[-507.01886, 19.65623, 276.94449, -507.03781, 19.64030, 276.96106, -507.00504, 19.61183, 276.99985],
[-506.96582, 19.59245, 277.03396, -506.97355, 19.64655, 276.95336, -507.01886, 19.65623, 276.94449],
[-506.96582, 19.59245, 277.03396, -507.01886, 19.65623, 276.94449, -507.00504, 19.61183, 276.99985],
[-506.81776, 19.67248, 277.04224, -506.94828, 19.66823, 276.98563, -506.86569, 19.64038, 277.06080],
[-506.81776, 19.67248, 277.04224, -506.86569, 19.64038, 277.06080, -506.81147, 19.64584, 277.07907],
[-506.81776, 19.67248, 277.04224, -506.94828, 19.66823, 276.98563, -506.86569, 19.64038, 277.06080],
[-506.81776, 19.67248, 277.04224, -506.86569, 19.64038, 277.06080, -506.81147, 19.64584, 277.07907],
[-506.95300, 18.80928, 276.69058, -507.39648, 18.83384, 277.06617, -507.46393, 18.80655, 276.96684],
[-506.95300, 18.80928, 276.69058, -507.46393, 18.80655, 276.96684, -507.32892, 18.87290, 276.62625],
[-507.37214, 18.86629, 277.10138, -507.39648, 18.83384, 277.06617, -506.95300, 18.80928, 276.69058],
[-507.37214, 18.86629, 277.10138, -506.95300, 18.80928, 276.69058, -506.87954, 18.84964, 276.66897],
[-506.77065, 19.55168, 276.67987, -506.81570, 19.54061, 276.67981, -506.79538, 19.56420, 276.66554],
[-506.79419, 19.58146, 276.69326, -506.77065, 19.55168, 276.67987, -506.79538, 19.56420, 276.66554],
[-506.79419, 19.58146, 276.69326, -506.79538, 19.56420, 276.66554, -506.82183, 19.57185, 276.69648],
[-506.77065, 19.55168, 276.67987, -506.81570, 19.54061, 276.67981, -506.79538, 19.56420, 276.66554],
[-506.79419, 19.58146, 276.69326, -506.77065, 19.55168, 276.67987, -506.79538, 19.56420, 276.66554],
[-506.79419, 19.58146, 276.69326, -506.79538, 19.56420, 276.66554, -506.82183, 19.57185, 276.69648],
[-504.52797, 20.02396, 275.49350, -504.52903, 20.02396, 275.49354, -504.52903, 20.02396, 275.47353],
[-504.27948, 20.57794, 274.56192, -504.29116, 20.54563, 274.56753, -504.29114, 20.54564, 274.55802],
[-507.44374, 18.80747, 276.95999, -507.42613, 18.80756, 276.95048, -507.44140, 18.80841, 276.96339],
[-506.77065, 19.55168, 276.67987, -506.77952, 19.49929, 276.72755, -506.82844, 19.51071, 276.70966],
[-506.77065, 19.55168, 276.67987, -506.82844, 19.51071, 276.70966, -506.81570, 19.54061, 276.67981],
[-506.77065, 19.55168, 276.67987, -506.77952, 19.49929, 276.72755, -506.82844, 19.51071, 276.70966],
[-506.77065, 19.55168, 276.67987, -506.82844, 19.51071, 276.70966, -506.81570, 19.54061, 276.67981],
[-507.28205, 18.65930, 276.90723, -507.31417, 18.67540, 276.89695, -507.29569, 18.67499, 276.89826],
[-506.63425, 19.53146, 277.02650, -506.61826, 19.52791, 277.04373, -506.61411, 19.53822, 277.03327],
[-504.31607, 20.56785, 275.55466, -504.31607, 20.56785, 275.56419, -504.28516, 20.58294, 275.55856],
[-504.49022, 20.02396, 274.03733, -504.48917, 20.02396, 274.05730, -504.48917, 20.02396, 274.03729],
[-507.69203, 19.01724, 277.02334, -507.67452, 19.01026, 277.03193, -507.67880, 19.01499, 277.04596],
[-507.44140, 18.80841, 276.96339, -507.42613, 18.80756, 276.95048, -507.44374, 18.80747, 276.95999],
[-506.62510, 19.64268, 277.10770, -506.62925, 19.63464, 277.08271, -506.61824, 19.64775, 277.07838],
[-506.62510, 19.64268, 277.10770, -506.61824, 19.64775, 277.07838, -506.61264, 19.65145, 277.09690],
[-506.81776, 19.67248, 277.04224, -506.81147, 19.64584, 277.07907, -506.75031, 19.64013, 277.10823],
[-506.81776, 19.67248, 277.04224, -506.75031, 19.64013, 277.10823, -506.70864, 19.65558, 277.11578],
[-506.66424, 19.63181, 277.07169, -506.64410, 19.62719, 277.07200, -506.64384, 19.62663, 277.08738],
[-506.64693, 19.63161, 277.07013, -506.63033, 19.62078, 277.09855, -506.62778, 19.62152, 277.07349],
[-506.81776, 19.67248, 277.04224, -506.81147, 19.64584, 277.07907, -506.75031, 19.64013, 277.10823],
[-506.81776, 19.67248, 277.04224, -506.75031, 19.64013, 277.10823, -506.70864, 19.65558, 277.11578],
[-504.19832, 19.04879, 273.85716, -503.41631, 19.16494, 274.21411, -503.36679, 19.18588, 273.39699]]


# The visible dead bush bush-a-dead-lrg-a @0x51edc0 (x -496.5..-493.8, z 272.7..276.2) stands at the ramp's east exit; its collision is a vertical
# 2.7 m x 3.7 m wall quad (props item 9, tag 0x101, keys 0x4a2c/0x4a2d) diagonally across the whole exit between the north wall (z 273.1) and the store wall (z 275.93), x -495.2..-494.5.  Render stays, collision goes (SP foliage is walk-through)
LEFT_BUSH_E = [[-495.22813, 20.50266, 275.89278, -494.46367, 20.50266, 272.27686, -494.46367, 17.80845, 272.27686],
[-495.22813, 20.50266, 275.89278, -494.46367, 17.80845, 272.27686, -495.22813, 17.80845, 275.89278]]


# The delete of LEFT_LANE cannot take a section's LAST triangle (it keeps and shrinks it): two specks (0 and 2 cm2, keys 0x8900 / 0x9700 item 1) stayed hanging at x -506.8 z 276.7, 1.35 m over the floor.
# Their five vertices go down under the floor (post entry: runs on the result of the others, positions after the shrink).
SPECK_VERTS = [[-506.79419, 19.58146, 276.69326], [-506.77065, 19.55168, 276.67987], [-506.79538, 19.56420, 276.66554], [-506.77952, 19.49929, 276.72755], [-506.82844, 19.51071, 276.70966]]
SPECK_FLOOR_Y = 17.95


# Whole-map fin scan (lane_scan.py --whole): the five fins of our edits that the morph rule (fins.json) does not take (small, 0.1-0.28 m): alley 0x156c at the window ledge's south edge, Supermarket
# 0x7824 / 0x78aa / 0x78bc (x -504.7 z 287.3) and 0x7906 (x -505.5 z 284.7) in the store.  Targeted deletes, "post": they are triangles the ground grid ADDS (deletes run before adds, so a normal delete never sees them); a section's last triangle is kept and folded flat by the delete stage.
FIN_LEFT_SM = [[-504.54171, 17.93088, 287.38889, -504.75674, 17.74433, 287.39136, -504.75674, 17.88320, 287.63513],
[-504.97101, 17.92614, 287.39136, -504.75674, 17.74433, 287.39136, -504.75674, 18.02725, 287.14758],
[-504.54336, 17.99230, 287.14560, -504.75674, 18.02725, 287.14758, -504.75674, 17.74433, 287.39136],
[-505.58745, 17.98871, 284.54006, -505.60164, 17.98275, 284.85187, -505.44398, 17.76432, 284.86794]]
FIN_LEFT_AL = [[-513.46087, 18.39691, 282.55063, -511.85290, 18.35166, 282.60790, -512.03159, 18.29532, 282.55862]]


def spec():
    ed = []
    for lv in ("pat-jackson-alley", "pat-jackson-supermarket"):
        ed.append({"name": "new hall: stray collision cleared (%s)" % lv, "level": lv, "kind": "clear", "active": True, "box": BOX, "rect": RECT,
                   "meshes": MESHES, "render_levels": RENDER, "down": 0.8, "up": 2.2, "tall": 2.2})
    for lv in ("pat-jackson-alley", "pat-jackson-supermarket"):    # mounds / wedges / stale pocket strips / stock snow over the new ground (0.2-0.4 m over the render snow): up-facing triangles and tiny slivers only, the walls stay
        ed.append({"name": "new hall: stale ground cleared (%s)" % lv, "level": lv, "kind": "clear", "active": True, "box": WBOX, "rect": CRECT, "meshes": MESHES,
                   "render_levels": RENDER, "down": 0.8, "up": 0.8, "tall": 2.2, "min_ny": 0.3, "max_area": 0.03})
    for i, (jb, why) in enumerate(JUNK):
        ed.append({"name": "new hall: leftover slivers cleared %d (%s)" % (i + 1, why), "level": "pat-jackson-supermarket", "kind": "clear", "active": True, "box": jb, "rect": jb, "meshes": MESHES,
                   "render_levels": RENDER, "down": 0.8, "up": 2.2, "tall": 2.2, "max_area": 0.1})
    ed.append({"name": "new hall: east wall wedge removed", "level": "pat-jackson-supermarket", "kind": "delete", "active": True, "tris": WEDGE})
    ed.append({"name": "new hall: collapsed slivers under the floor cleared", "level": "pat-jackson-alley", "kind": "clear", "active": True, "box": SLIV, "rect": SLIV, "meshes": MESHES,
               "render_levels": RENDER, "down": 2.0, "up": 0.5, "tall": 2.2, "and_max_ny": 0.5, "below": 0.3, "post": True})
    ed.append({"name": "new hall: invisible plateau removed", "level": "pat-jackson-alley", "kind": "delete", "active": True, "tris": PLAT_TRIS})
    ed.append({"name": "new hall: render-following snow ground", "level": "pat-jackson-supermarket", "kind": "ground", "active": True, "rect": RECT, "cell": 0.3, "root": 1.3, "tol": 0.05, "seam": "W", "blend": 1.5,
               "lift": 0.05, "meshes": LMESH, "render_levels": RENDER, "mrec": SNOW, "like": [-508.0, 18.1, 282.5], "like_max": 20.0, "smooth": SMOOTH})
    ed.append({"name": "hill: stock collision cleared", "level": "pat-jackson-supermarket", "kind": "clear", "active": True, "box": HILL, "rect": HILL, "meshes": ["snow_chunk_render"],
               "render_levels": ["pat-jackson-supermarket"], "down": 0.8, "up": 0.8, "tall": 2.2})
    ed.append({"name": "hill: render-following snow ground", "level": "pat-jackson-supermarket", "kind": "ground", "active": True, "rect": HILL, "cell": 0.3, "root": 0.65, "tol": 0.035,
               "lift": 0.05, "seam": "ESN", "blend": 1.0, "meshes": ["snow_chunk_render"], "render_levels": ["pat-jackson-supermarket"], "mrec": SNOW, "like": [-493.0, 18.5, 273.0], "like_max": 20.0})
    ed.append({"name": "gate / bush: leftover collision of the removed trash bins removed", "level": "pat-jackson-supermarket", "kind": "delete", "active": True, "tris": LEFT_TRASH})
    ed.append({"name": "gate / bush: leftover collision of the removed bushes removed", "level": "pat-jackson-supermarket", "kind": "delete", "active": True, "tris": LEFT_BUSH + LEFT_HULL})
    ed.append({"name": "yard ramp: stock collision cleared", "level": "pat-jackson-supermarket", "kind": "clear", "active": True, "box": RAMPC, "rect": RAMPC, "meshes": ["ext-terrain-chunk-c"],
               "render_levels": ["pat-jackson-supermarket"], "down": 0.8, "up": 2.2, "tall": 2.2})
    ed.append({"name": "yard ramp east: stale ground cleared", "level": "pat-jackson-supermarket", "kind": "clear", "active": True, "box": RAMPE, "rect": RAMPE, "meshes": LMESH,
               "render_levels": RENDER, "down": 0.8, "up": 0.8, "tall": 2.2, "min_ny": 0.3})
    ed.append({"name": "hall lane north exit: stale ground cleared", "level": "pat-jackson-supermarket", "kind": "clear", "active": True, "box": NEXIT, "rect": NEXIT, "meshes": LMESH,
               "render_levels": RENDER, "down": 0.8, "up": 0.8, "tall": 2.2, "min_ny": 0.3})
    ed.append({"name": "hall lane north exit: render-following snow ground", "level": "pat-jackson-supermarket", "kind": "ground", "active": True, "rect": NEXIT, "cell": 0.4, "root": 1.3, "tol": 0.06,
               "lift": 0.05, "seam": "N", "blend": 1.5, "meshes": LMESH, "render_levels": RENDER, "mrec": SNOW, "like": [-507.5, 18.4, 289.0], "like_max": 20.0, "smooth": SMOOTH})
    ed.append({"name": "yard ramp: render-following snow ground", "level": "pat-jackson-supermarket", "kind": "ground", "active": True, "rect": RAMP, "cell": 0.4, "root": 1.3, "tol": 0.06,
               "lift": 0.05, "meshes": LMESH, "render_levels": RENDER, "mrec": SNOW, "like": [-500.5, 18.3, 274.5], "like_max": 20.0, "smooth": SMOOTH})
    ed.append({"name": "ramp east exit: bush wall collision removed (the bush render stays)", "level": "pat-jackson-supermarket", "kind": "delete", "active": True, "tris": LEFT_BUSH_E})
    ed.append({"name": "hall lane: leftover collision with no render removed", "level": "pat-jackson-supermarket", "kind": "delete", "active": True, "tris": LEFT_LANE})
    for lv_ in ("pat-jackson-alley", "pat-jackson-supermarket"):
        ed.append({"name": "hall lane window side: stale ground cleared (%s)" % lv_, "level": lv_, "kind": "clear", "active": True, "box": WEXT, "rect": WEXT, "meshes": LMESH,
                   "render_levels": RENDER, "down": 0.8, "up": 0.8, "tall": 2.2, "min_ny": 0.3})
    for nm_, rc_ in (("hall lane south strip", STRIP), ("hall lane yard", YARD)):
        crc_ = list(rc_)                                                  # clear rect: padded 0.5 m over the shared strip / yard edge (z 275.95): a stock triangle straddling it was in neither entry's rect and stayed hovering (key 0x410a, 0.5-0.75 m over the floor); both grounds cover the pad      # the rest of the lane (stock ground / earlier deletes left it floating 0.3-0.6 m over the render snow, or missing): ground from the render, no seam (walls on both sides)
        if nm_ == "hall lane yard":
            crc_[3] += 0.5
        else:
            crc_[1] -= 0.5
        ed.append({"name": nm_ + ": stale ground cleared", "level": "pat-jackson-supermarket", "kind": "clear", "active": True, "box": rc_, "rect": crc_, "meshes": LMESH,
                   "render_levels": RENDER, "down": 0.8, "up": 0.8, "tall": 2.2, "min_ny": 0.3})
        ed.append({"name": nm_ + ": render-following snow ground", "level": "pat-jackson-supermarket", "kind": "ground", "active": True, "rect": rc_, "cell": 0.4, "root": 1.3, "tol": 0.06,
                   "lift": 0.05, "meshes": LMESH, "render_levels": RENDER, "mrec": SNOW, "like": [-507.5, 18.4, 279.0], "like_max": 20.0, "smooth": SMOOTH})
    # Invisible collision in the hall's south strip (x -507.5..-506.5 z 275.5..277.6): the morph stage (Snow Stitch collision field) pulls the BOTTOM vertices of stock
    # steep slivers / mound edges down onto the new surface while their top vertex stays: a 0.9 m 'fin' (key 0x5800 item 1, normal (+0.41 0 +0.91), no render surface) standing in the walking
    # floor.  The ground grid itself is a height field (it never made it); the clears above only take up-facing triangles (min_ny).  So after every ground entry: any collision triangle in the lane that
    # is not walkable (ny <= 0.7), stands > 8 cm over the render snow, is shorter than 2.2 m and has NO drawn surface (render or prop) within 0.35 m is removed.  Drawn walls / props stay.
    for lv_ in ("pat-jackson-alley", "pat-jackson-supermarket"):
        ed.append({"name": "hall lane: undrawn fins / folds / slivers cleared (%s)" % lv_, "level": lv_, "kind": "clear", "active": True, "box": LANE, "rect": LANE, "meshes": LMESH,
                   "render_levels": RENDER + ["pat-jackson-supermarket-int"], "down": 0.8, "up": 1.9, "tall": 2.2, "and_max_ny": 0.7, "min_above": 0.08, "no_render": 0.35,
                   "no_render_skip": FLOOR_ASSETS})
    ed.append({"name": "hall lane: the two last-triangle specks of LEFT_LANE moved under the floor", "level": "pat-jackson-supermarket", "kind": "verts", "active": True, "post": True,
               "moves": [{"from": p, "to": [p[0], SPECK_FLOOR_Y, p[2]]} for p in SPECK_VERTS]})
    ed.append({"name": "whole-map fin scan: 4 small fins of our edits removed (Supermarket)", "level": "pat-jackson-supermarket", "kind": "delete", "active": True, "post": True, "tris": FIN_LEFT_SM})
    ed.append({"name": "whole-map fin scan: 1 small fin of our edits removed (alley window ledge)", "level": "pat-jackson-alley", "kind": "delete", "active": True, "post": True, "tris": FIN_LEFT_AL})
    return {"_comment": "Written by tools/maps/hall_floor.py (not by the Scene Editor). Auto collision edits applied by coll_edit.py after the user's colledits: "
                        "the new hall's ground follows the render snow (kinds clear / ground, see coll_edit.py).", "key": KEY, "version": 1, "edits": ed}


def main(a):
    if a[:1] == ["write"]:
        p = os.path.join(HERE, "data", KEY + "-colledits-auto.json")
        json.dump(spec(), open(p, "w", encoding="utf-8", newline="\n"), indent=1)
        print("wrote", p)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
