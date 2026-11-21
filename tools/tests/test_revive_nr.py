"""Kneel help-up revive: revive_nr_pak (page carriers, carrier pick, header) and the ext's walk-in pick / speed rules (revive2013.c rvnr_pick /
rvnr_spd compiled out of the real source with tools/ext/revive_nr.h).
The pak tests need the game's actor97/anim-npc-alert-caps.pak (re/gamebin cache) and are skipped without it; the C tests need gcc (msys64 ucrt64).
    python tools/tests/test_revive_nr.py"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = os.environ.get("T2R_MAIN_ROOT", ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "features"))
import revive_nr_pak as V  # noqa: E402

EXT = os.path.join(ROOT, "tools", "ext")
HOST = next((p for p in (os.path.join(r, "re", "gamebin", "actor97", V.HOST_PAK + ".pak") for r in (ROOT, MAIN)) if os.path.exists(p)), None)


def _gcc():
    for r in (ROOT, MAIN):
        g = os.path.join(r, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
        if os.path.isfile(g):
            return g
    return shutil.which("gcc")


def _rows(n, x0=0.0):
    """(n, 7) locator rows: a walk along +z with a slow yaw"""
    r = np.zeros((n, 7))
    r[:, 0] = x0
    r[:, 2] = np.linspace(0, 1, n)
    th = np.linspace(0, 0.5, n)
    r[:, 4] = np.sin(th / 2)
    r[:, 6] = np.cos(th / 2)
    return r


def _clip(n, seed):
    """stand-in ClipData bytes (the pak tool copies them; a real clip's header is not needed for the page math)"""
    b = bytearray(np.random.default_rng(seed).integers(0, 255, n, dtype=np.uint8).tobytes())
    b[8:12] = n.to_bytes(4, "little")
    return bytes(b)


@unittest.skipUnless(HOST, "no game copy of actor97/" + V.HOST_PAK + ".pak (re/gamebin)")
class Pak(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = open(HOST, "rb").read()

    def test_used_carriers_of_unchanged_pak_is_empty(self):
        self.assertEqual(V.used_carriers(self.host, self.host), set())

    def test_build_verify_and_untouched_rest(self):
        free = V.candidates(self.host)
        halves = [(free[i], _clip(3000 + 500 * i, i), _rows(10 + i), _rows(10 + i, 0.5)) for i in range(4)]
        out = V.build(self.host, halves)
        self.assertTrue(V.verify(self.host, out, halves))
        self.assertEqual(V.used_carriers(self.host, out), {h[0] for h in halves})       # exactly those carriers count as taken afterwards

    def test_halves_spill_onto_a_second_page(self):
        free = V.candidates(self.host)
        big = V.MAX_PAGE // 3
        halves = [(free[i], _clip(big, 10 + i), _rows(20), _rows(20)) for i in range(4)]     # 4 x 1/3 page: two pages
        out = V.build(self.host, halves)
        self.assertTrue(V.verify(self.host, out, halves))
        self.assertGreater(len(out), len(self.host) + 4 * big)

    def test_one_half_bigger_than_a_page_is_refused(self):
        free = V.candidates(self.host)
        with self.assertRaises(ValueError):
            V.build(self.host, [(free[0], _clip(V.MAX_PAGE, 1), _rows(5), _rows(5))])

    def test_assign_skips_taken_carriers(self):
        free = V.candidates(self.host)
        taken = V.build(self.host, [(free[0], _clip(4000, 3), _rows(8), _rows(8))])
        car = V.assign(self.host, taken, ["a", "b"])
        self.assertNotIn(free[0], car.values())
        self.assertEqual(list(car.values()), free[1:3])

    def test_assign_refuses_when_too_few(self):
        with self.assertRaises(SystemExit):
            V.assign(self.host, self.host, [str(i) for i in range(len(V.candidates(self.host)) + 1)])


class Header(unittest.TestCase):
    def test_empty_header(self):
        with tempfile.TemporaryDirectory() as d:
            txt = V.write_header(os.path.join(d, "h.h"), {}, {})
        self.assertIn("#define RVNR_N_ENTER 0", txt)
        self.assertIn('RVNR_FIN[2][2][2] = {{{"", ""}, {"", ""}}, {{"", ""}, {"", ""}}}', txt)

    def test_full_header_lists_every_walk_in(self):
        metas = [dict(role="enter_vic", seconds=3.2), dict(role="loop_vic", seconds=0.93)]
        for s in "LR":
            for b in (0, 90):
                metas.append(dict(role=f"enter_{s}_{b}", side=s, bearing=b, walk_s=1.0, seconds=1.2, path=[[0.1 * k, 1.0] for k in range(40)]))
            metas += [dict(role=f"loop_{s}", seconds=0.93), dict(role=f"pull_{s}", seconds=4.4), dict(role=f"pull_{s}_vic", seconds=4.4)]
        prone = [dict(role="enter_L_0", side="L", bearing=0, walk_s=2.0, seconds=3.0, path=[[0.0, 1.0]]), dict(role="enter_L_0_vic", seconds=3.0),
                 dict(role="loop_L", seconds=1.1), dict(role="loop_L_vic", seconds=1.1), dict(role="fin_L", seconds=2.5), dict(role="fin_L_vic", seconds=2.5)]
        sets = {"kneel": metas, "prone": prone}
        car = {f"{k}/{m['role']}": f"c-{k}-{m['role']}" for k, ms in sets.items() for m in ms}
        with tempfile.TemporaryDirectory() as d:
            txt = V.write_header(os.path.join(d, "h.h"), car, sets)
        self.assertIn("#define RVNR_N_ENTER 5", txt)
        self.assertEqual(txt.count('"c-kneel-enter_vic"'), 4)         # every kneel walk-in shares the revived's enter half
        self.assertIn('''{1, 'L', 0, 2.000f, 3.000f, "c-prone-enter_L_0", "c-prone-enter_L_0_vic", 1,''', txt)   # the prone start has its own
        self.assertIn(f", {V.NPATH}, {{", txt)                         # a 40-sample path is cut to RVNR_NPATH
        self.assertIn('RVNR_FIN[2][2][2] = {{{"c-kneel-pull_L", "c-kneel-pull_L_vic"}, {"c-kneel-pull_R", "c-kneel-pull_R_vic"}}, '
                      '{{"c-prone-fin_L", "c-prone-fin_L_vic"}, {"", ""}}}', txt)
        self.assertIn('{"c-prone-loop_L", "c-prone-loop_L_vic"}', txt)
        self.assertIn("RVNR_LOOP_S[2] = {0.930f, 1.100f}, RVNR_FIN_S[2] = {4.400f, 2.500f}", txt)


def _ext_funcs():
    """rvnr_spd + rvnr_pick out of revive2013.c (the real code)"""
    src = open(os.path.join(EXT, "revive2013.c")).read()
    out = []
    for name in ("rvnr_spd", "rvnr_pick"):
        m = re.search(r"^static (?:float|int) %s\(.*?^}\n" % name, src, re.S | re.M)
        assert m, name
        out.append(m.group(0))
    return "\n".join(out)


HARNESS = r"""
#include <stdio.h>
#include <math.h>
#include "revive_nr.h"
#define RVNR_MAX_SPD 1.6f
%s
int main(void) {
    printf("N %%d\n", RVNR_N_ENTER);
    printf("SPD %%.4f %%.4f %%.4f %%.4f\n", rvnr_spd(4400, 5000), rvnr_spd(4400, 2200), rvnr_spd(4400, 3500), rvnr_spd(4400, 0));
    for (int i = 0; i < RVNR_N_ENTER; i++)                      // standing ON a path sample: that sample (or one at the same spot)
        for (int k = 0; k < RVNR_ENTER[i].npath; k++) {
            float sk, mi; int j = rvnr_pick(RVNR_ENTER[i].set, RVNR_ENTER[i].path[k][0], RVNR_ENTER[i].path[k][1], &sk, &mi);
            printf("ON %%d %%d %%d %%.4f %%.2f\n", i, k, j, mi, sk);
        }
    for (int set = 0; set < 2; set++)                           // per set: a ring of reviver spots inside the 2.12 m revive range
        for (int a = 0; a < 360; a += 10)
            for (float r = 0.7f; r < 2.15f; r += 0.35f) {
                float sk, mi, x = r * sinf(a * 0.0174533f), z = r * cosf(a * 0.0174533f);
                int j = rvnr_pick(set, x, z, &sk, &mi);
                printf("RING %%d %%.2f %%d %%.4f %%.2f %%.2f %%d\n", a, r, j, mi, sk, j >= 0 ? RVNR_ENTER[j].dur_s - sk : -1.0f, set);
            }
    return 0;
}
"""


@unittest.skipUnless(_gcc(), "no gcc")
class ExtPick(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        c = os.path.join(cls.d, "h.c")
        open(c, "w").write(HARNESS % _ext_funcs())
        exe = os.path.join(cls.d, "h.exe")
        g = _gcc()
        env = dict(os.environ, PATH=os.path.dirname(g) + os.pathsep + os.environ.get("PATH", ""))
        subprocess.check_call([g, "-std=gnu2x", "-O1", "-I", EXT, "-o", exe, c], env=env)
        cls.out = subprocess.run([exe], capture_output=True, text=True, env=env, check=True).stdout.split("\n")
        cls.n = int(cls.out[0].split()[1])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def test_speed_clamps(self):
        s = [float(x) for x in self.out[1].split()[1:]]
        self.assertAlmostEqual(s[0], 1.0)          # more time than the clip: never slower than authored
        self.assertAlmostEqual(s[1], 1.6)          # capped
        self.assertAlmostEqual(s[2], 4400 / 3500, places=3)
        self.assertAlmostEqual(s[3], 1.6)          # no time left: the cap, no division by zero

    def test_standing_on_a_path_sample_picks_that_spot(self):
        if not self.n:
            self.skipTest("empty revive_nr.h (no baked set in this checkout)")
        on = [l.split() for l in self.out if l.startswith("ON ")]
        self.assertTrue(on)
        self.assertLess(max(float(x[4]) for x in on), 0.06)

    def test_every_spot_in_range_has_a_walk_in_near_it(self):
        if not self.n:
            self.skipTest("empty revive_nr.h (no baked set in this checkout)")
        ring = [l.split() for l in self.out if l.startswith("RING ") and l.split()[7] == "0"]
        if not any(e for e in ring if int(e[3]) >= 0):
            self.skipTest("no kneel set in this build")
        self.assertTrue(all(int(x[3]) >= 0 for x in ring))
        # measured with the bake (walk-ins start 1.35 m out, every 45 deg): within 1.4 m <= 0.43 m off a path at 1.05 / 1.4 m and 0.59 m right at
        # her head / feet (0.7 m); at the 2.1 m range edge up to 0.95 m (the drive blend slides that). Gates = those numbers + a margin (no regression).
        mid = max(float(x[4]) for x in ring if 0.9 <= float(x[2]) <= 1.45)
        near = max(float(x[4]) for x in ring if float(x[2]) <= 1.45)
        far = max(float(x[4]) for x in ring)
        self.assertLess(mid, 0.5, "a reviver spot 1.05 .. 1.4 m out is %.2f m from every walk-in path" % mid)
        self.assertLess(near, 0.65, "a reviver spot within 1.4 m is %.2f m from every walk-in path" % near)
        self.assertLess(far, 1.0, "a reviver spot within 2.1 m is %.2f m from every walk-in path" % far)

    def test_prone_spots_in_range_have_a_crawl_in_near_them(self):
        ring = [l.split() for l in self.out if l.startswith("RING ") and l.split()[7] == "1"]
        if not any(int(x[3]) >= 0 for x in ring):
            self.skipTest("no prone set in this build")
        self.assertTrue(all(int(x[3]) >= 0 for x in ring))
        # measured (6 crawl-ins, paths start 0.9 .. 1.5 m out): 1.05 .. 1.4 m out <= 0.71 m off a path, at the 2.1 m edge up to 1.41 m.
        # KNOWN LIMIT (open): a prone reviver more than ~1.5 m out has no path near it. Gates = no regression only.
        mid = max(float(x[4]) for x in ring if 0.9 <= float(x[2]) <= 1.45)
        far = max(float(x[4]) for x in ring)
        self.assertLess(mid, 0.75, "a prone reviver 1.05 .. 1.4 m out is %.2f m from every crawl-in path" % mid)
        self.assertLess(far, 1.45, "a prone reviver within 2.1 m is %.2f m from every crawl-in path" % far)

    def test_one_reviver_stands_her_up_as_the_bar_fills(self):
        """5 s hold, walk-in from its first frame (worst case, no skip): ENTER at x spd0, then PULL; spd0 under the cap = standing at 5.0 s"""
        if not self.n:
            self.skipTest("empty revive_nr.h (no baked set in this checkout)")
        txt = open(os.path.join(EXT, "revive_nr.h")).read()
        pull = float(re.search(r"RVNR_FIN_S\[2\] = \{([\d.]+)f", txt).group(1))
        durs = [float(m) for m in re.findall(r"\{0, '[LR]', -?\d+, [\d.]+f, ([\d.]+)f,", txt)]
        self.assertTrue(durs)
        for d in durs:
            spd0 = max(1.0, (d + pull) / 5.0)
            self.assertLessEqual(spd0, 1.6, "walk-in of %.2f s + pull %.2f s needs x%.2f" % (d, pull, spd0))



def _table():
    txt = open(os.path.join(EXT, "revive_nr.h")).read()
    f2 = lambda name: [float(x) for x in re.search(name + r"\[2\] = \{([\d.]+)f, ([\d.]+)f\}", txt).groups()]
    ents = [(int(a), float(d)) for a, d in re.findall(r"\{(\d), '[LR]', -?\d+, [\d.]+f, ([\d.]+)f,", txt)]
    return ents, f2("RVNR_LOOP_S"), f2("RVNR_FIN_S"), f2("RVNR_FIN_SKIP_S")


def _sim(enter, loop_s, fin_s, skip_max, book, skip0=0.0):
    """revive2013.c's chain rules in time (s): ENTER from skip0 at spd0; at every segment end LOOP while the time left > FINISH + 0.1, else FINISH
    (rvnr_fin: x1..x1.6, or started up to skip_max in and the rest at x1.3); booked mid loop = FINISH now; booked in ENTER = at ENTER's end.
    -> (FINISH end time, its speed, its skip)"""
    cap, sk_spd = 1.6, 1.3
    spd = lambda c, l: cap if l < 0.001 else min(cap, max(1.0, c / l))

    def fin(t, left):
        sk, s = 0.0, spd(fin_s, left)
        if left < 0.001 or fin_s / left > cap:
            sk = min(skip_max, max(0.0, fin_s - left * sk_spd))
            s = spd(fin_s - sk, left)
        return t + (fin_s - sk) / s, s, sk
    s0 = spd(enter - skip0 + fin_s, book)
    t = (enter - skip0) / s0
    while True:
        if t >= book:
            return fin(t, 0.0)
        left = book - t
        if left > fin_s + 0.1:
            if t + loop_s > book:
                return fin(book, 0.0)
            t += loop_s
            continue
        return fin(t, left)


@unittest.skipUnless(os.path.exists(os.path.join(EXT, "revive_nr.h")), "no revive_nr.h")
class Timing(unittest.TestCase):
    """the 5 s hold is the whole help-up: how late is she standing (FINISH end - booking) for every walk-in, revive time and co-revive case"""
    @classmethod
    def setUpClass(cls):
        cls.ents, cls.loop, cls.fin, cls.skip = _table()
        cls.kneel = [d for k, d in cls.ents if k == 0]

    def late(self, book, skip0=0.0):
        return [_sim(d, self.loop[0], self.fin[0], self.skip[0], book, skip0)[0] - book for d in self.kneel]

    def test_one_reviver_on_time(self):
        if not self.kneel:
            self.skipTest("no kneel set in this build")
        self.assertLess(max(self.late(5.0)), 0.05)                       # standing as the bar fills
        self.assertGreater(min(self.late(5.0)), -0.05)                   # and not before it

    def test_reviver_perk_and_co_revive(self):
        """Reviver perk 0.70 / 0.55 / 0.45 x 5 s; two revivers (1.6x from the start); worst case = the longest walk-in, no start skip"""
        if not self.kneel:
            self.skipTest("no kneel set in this build")
        # measured (longest walk-in 3.13 s, no skip): 3.5 s on time, two revivers 0.21 s late, perk 2 0.58 s, perk 3 1.08 s (was ~2.5 s
        # before FINISH could start into its hands-on part); a reviver that starts close (start skip) is on time more often
        for book, worst in ((3.5, 0.05), (5.0 / 1.6, 0.3), (2.75, 0.7), (2.25, 1.2)):
            w = max(self.late(book))
            self.assertLess(w, worst, "revive in %.2f s: standing %.2f s after the bar" % (book, w))

    def test_prone_timing(self):
        """prone dap-up: ENTER = crawl-in + lay down + roll onto her back (3.0 s) + clasp; FINISH (back onto her belly) 1.73 s, no skip"""
        prone = [d for k, d in self.ents if k == 1]
        if not prone:
            self.skipTest("no prone set in this build")
        late = lambda book: max(_sim(d, self.loop[1], self.fin[1], self.skip[1], book)[0] - book for d in prone)
        # measured (longest crawl-in 6.53 s): 5 s hold 0.17 s late (needs x1.65 vs the x1.6 cap); KNOWN LIMIT (open): reviver perk
        # 3.5 s 1.67 s late, two revivers 2.04 s, perk 2 2.42 s, perk 3 2.92 s. Gates = no regression only.
        for book, worst in ((5.0, 0.2), (3.5, 1.75), (5.0 / 1.6, 2.1), (2.75, 2.5), (2.25, 3.0)):
            w = late(book)
            self.assertLess(w, worst, "prone revive in %.2f s: done %.2f s after the bar" % (book, w))

    def test_finish_speed_and_skip_stay_in_bounds(self):
        if not self.kneel:
            self.skipTest("no kneel set in this build")
        for book in (5.0, 4.0, 3.0, 2.25, 1.3):
            for d in self.kneel:
                end, s, sk = _sim(d, self.loop[0], self.fin[0], self.skip[0], book)
                self.assertTrue(1.0 <= s <= 1.6 and 0.0 <= sk <= self.skip[0] + 1e-6)


if __name__ == "__main__":
    unittest.main()
