"""Loadout point total with free (0 LP) picks in every slot, and the sidearm row order.

The bug: since the sidearm list moved from winmm's own table (0x1800A0E90) to ours, lo_cost / the lo_valid log / the GEAR UP mirror still read a
sidearm's LP at winmm's table (VMA(0x1800A0EA8) + row * 0x38). winmm's table holds only the game's 3 rows, so a later row (the Snubby, row 5
then) read foreign memory: the GEAR UP edit page showed "955046544 | 13" with the Snubby as sidearm.

Checks:
1. No sidearm read goes to winmm's old table outside small_tab() / the table install.
2. Every LP read of a loadout row (lo_cost, the lo_valid log, the skills.c mirror) uses the live table of its slot.
3. A model of the live sidearm table built from the ext's own install code: the Snubby is row 2 at 0 LP. A loadout with a free pick in each
   slot (no primary, each free sidearm, no purchasable) costs only its skills, and every sidearm row's LP is that row's own value.
4. The T2RLO8 remap of older t2r-loadout.txt sidearm rows (files saved with the Snubby last, and without it).
Run: python tools/tests/test_lp_sidearm.py"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FAILS = []


def check(c, w):
    print(("ok   " if c else "FAIL ") + w)
    if not c:
        FAILS.append(w)


def rd(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8", errors="replace").read()


ext, sk_c = rd("tools", "ext", "t2r-ext.c"), rd("tools", "ext", "skills.c")

# 1. winmm's old sidearm table: only small_tab()'s fallback, the install's read of winmm's rows and the lea repoint targets may name it
for name, src in (("t2r-ext.c", ext), ("skills.c", sk_c)):
    bad = [ln.strip() for ln in src.splitlines()
           if re.search(r"VMA\(0x1800A0E(90|98|A0|A8|B0)\)", ln)
           and not re.search(r"static uint8_t \*small_tab\(void\)|small_real = |TARGETS\[\] = ", ln)]
    check(not bad, "%s: no read of winmm's old sidearm table outside small_tab() / the install%s" % (name, (": " + bad[0][:100]) if bad else ""))

# 2. the slot LP reads
body = ext[ext.index("static int lo_cost(const loadout_t *l) {"):]
body = body[:body.index("\n}") + 2]
check("g_large_tab + 0x18 + l->w[0] * 0x38" in body, "lo_cost: primary LP from the live large table")
check("small_tab() + 0x18 + l->w[1] * 0x38" in body, "lo_cost: sidearm LP from the live sidearm table (small_tab)")
check("lo_purch_tab() + 0x18 + l->w[2] * 0x40" in body, "lo_cost: purchasable LP from the live purchasable table")
check(ext.count("small_tab() + 0x18 + l->w[1] * 0x38") >= 2, "the lo_valid failure log prices the sidearm from small_tab too")
check("small_tab() + 0x18 + l->w[1] * 0x38" in sk_c, "skills.c GEAR UP mirror prices the sidearm from small_tab")
check(body.count("lo_lp(") >= 4 and re.search(r"static int lo_lp\(int v\) \{ return v >= 0 && v <= 13 \? v : 14; \}", ext),
      "lo_cost: every row price goes through lo_lp (a price outside 0..13 costs 14, so a bad read refuses the loadout)")

# 3. the live sidearm table, from the install code: the game's rows (launcher data = winmm's table) + the ext's appended rows in order
inst = ext[ext.index("static void install_weapon_tables(void) {"):]
inst = inst[:inst.index("\n}\n") if "\n}\n" in inst else inst.index("\r\n}\r\n")]
GAME = [("pistol-beretta", 0), ("pistol-revolver-taurus", 0), ("pistol-glock", 1)]
added = []
for m in re.finditer(r'\*\(const char \*\*\)\(e \+ 0x10\) = "([a-z0-9-]+)";(.*?)nsmall\+\+;', inst, re.S):
    lp = re.search(r"\*\(uint32_t \*\)\(e \+ 0x18\) = (\d+);", m.group(2))
    added.append((m.group(1), int(lp.group(1)) if lp else None))
check([a for a, _ in added] == ["pistol-cz75-enforcer", "shotgun-shorty", "pistol-snubby"],
      "install adds Enforcer, Shorty, Snubby to the sidearms (found %s)" % [a for a, _ in added])
rows = GAME + added
snub_row = int(re.search(r"#define SNUB_ROW (\d+)u", ext).group(1))
if re.search(r"memmove\(small \+ \(SNUB_ROW \+ 1\) \* 0x38, small \+ SNUB_ROW \* 0x38", inst):
    rows.insert(snub_row, rows.pop())
check(rows[snub_row] == ("pistol-snubby", 0), "the Snubby is sidearm row %d (3rd) at 0 LP" % snub_row)
check([lp for _, lp in rows[:3]] == [0, 0, 0], "the first three sidearms are the free ones (9mm, revolver, Snubby)")
supp = re.search(r'SMALL_SUPP\[\] = \{([^}]*)\}', ext).group(1)
for sid in re.findall(r'"([a-z0-9-]+)"', supp):
    lp = dict(rows)[sid]
    rows.append((sid + "-supp", lp + 1))
check(len(rows) <= 16, "the sidearm table fits our 16 rows (%d)" % len(rows))


def lo_cost(w, skills=0):
    c = 0
    if w[1] is not None:
        c += rows[w[1]][1]        # the live table, row w[1] (old code: winmm's 3-row table -> garbage past row 2)
    return c + skills


for r, (sid, lp) in enumerate(rows):
    if lp == 0:
        check(lo_cost((None, r, None), 9) == 9, "free pick in every slot: no primary, sidearm row %d %s, no purchasable = skills only (9)" % (r, sid))
for r, (sid, lp) in enumerate(rows):
    check(lo_cost((None, r, None)) == lp and 0 <= lp <= 2, "sidearm row %d %s costs its own %d LP" % (r, sid, lp))


# 4. T2RLO8: older files had the Snubby last (sb == current base count) or no Snubby (sb == base - 1)
def remap(w1, sb, base, v8=False):
    """lo_load's sidearm remap: the suppressed shift, then the Snubby move (same order and rules as the ext)"""
    saved = w1
    if w1 >= sb and base != sb:
        w1 = w1 + base - sb
    if not v8 and saved < sb and saved >= snub_row:
        w1 = snub_row if sb == base and saved == sb - 1 else saved + 1
    return w1


base = 6
old_with = ["pistol-beretta", "pistol-revolver-taurus", "pistol-glock", "pistol-cz75-enforcer", "shotgun-shorty", "pistol-snubby",
            "pistol-beretta-supp", "pistol-glock-supp", "pistol-cz75-enforcer-supp"]
old_without = [x for x in old_with if x != "pistol-snubby"]
for name, old, sb in (("saved with the Snubby last", old_with, 6), ("saved without the Snubby", old_without, 5)):
    for r, sid in enumerate(old):
        n = remap(r, sb, base)
        check(n < len(rows) and rows[n][0] == sid, "LO7 %s: row %d %s -> row %d %s" % (name, r, sid, n, rows[n][0] if n < len(rows) else "?"))
check(all(remap(r, base, base, v8=True) == r for r in range(len(rows))), "LO8 files keep their rows")
check('"T2RLO8 %d' in ext and 'strcmp(tag, "T2RLO8")' in ext, "lo_save writes T2RLO8, lo_load reads it")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
