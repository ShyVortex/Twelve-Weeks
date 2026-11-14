"""Offline test of the match-start voice exchanges (tools/features/vox_lines.py PAIRS / COMMENTS).
Run: python tools/tests/test_vox_exchanges.py   (plain python, data files only, no game needed).
t2r-ext maps an exchange line across factions / genders by INDEX, so the tables must line up."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FEAT = os.path.join(os.path.dirname(HERE), "features")
sys.path.insert(0, FEAT)
import vox_lines as v  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

male = json.load(open(os.path.join(FEAT, "data", "vox_lines.json")))
female = json.load(open(os.path.join(FEAT, "data", "vox_lines_female.json")))["lines"]

def rows(data, kind, fac):
    return [l for l in data if l["kind"] == kind and l["fac"] == fac]

check(len(v.PAIRS["mlt"]) == len(v.PAIRS["scr"]) >= 12, "same number of pairs in both factions (>= 12)")
for fac in v.FACTIONS:
    for name, data in (("male", male), ("female", female)):
        st, rp, cm = (rows(data, k, fac) for k in v.EXCH_KINDS)
        check(len(st) == len(rp) == len(v.PAIRS[fac]), "%s %s: statement / reply tables = the pairs" % (fac, name))
        check(len(cm) == len(v.COMMENTS[fac]) >= 6, "%s %s: >= 6 comments" % (fac, name))
        check([l["n"] for l in st] == list(range(1, len(st) + 1)), "%s %s: statement n = pair n" % (fac, name))
        check(all(l["text"].strip() for l in st + rp + cm), "%s %s: every line has a subtitle text" % (fac, name))
        check(all(len(l["ids"]) == 4 and len(l["speech"]) == 4 for l in st + rp + cm), "%s %s: 4 voices per line" % (fac, name))
    # the female pair has the same words as the male one (the gender never changes what is said)
    for kind in v.EXCH_KINDS:
        m, f = rows(male, kind, fac), rows(female, kind, fac)
        check([x["text"] for x in m] == [x["text"] for x in f], "%s %s: female texts = male texts" % (fac, kind))
    # no comment repeats a reply's words (speaker 3 never echoes speaker 2)
    replies = {l["text"].strip() for l in rows(male, "xrply", fac)}
    check(not any(l["text"].strip() in replies for l in rows(male, "xcomm", fac)), "%s: no comment equals a reply" % fac)
    # nobody answers a statement with the statement
    check(all(a["text"] != b["text"] for a, b in zip(rows(male, "xstmt", fac), rows(male, "xrply", fac))), "%s: reply != statement" % fac)
# round 2: the statements are the old winmm intro lines (long, characterful), not the short srch-start commands
check(any("take the other side" in l["text"] for l in rows(male, "xstmt", "scr")), "scr: 'You two, take the other side.' is a statement")
check(all(len(l["text"]) >= 14 for fac in v.FACTIONS for l in rows(male, "xstmt", fac)), "statements are full sentences")
# line ids are unique over all kinds (they become DC records)
ids = [i for l in male + female for i in l["ids"]]
check(len(ids) == len(set(ids)), "line ids unique (male + female)")
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
