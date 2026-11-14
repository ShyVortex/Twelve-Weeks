"""Journal entry authorship (journal entries had far too many authors with 1-2 events each).
One entry = 3..6 events, ONE author (two only when the lead event names exactly two), authors rotate, no event is dropped.  Temp DBs only.
Run: python tools/tests/test_clan_journal_entries.py"""
import os, sqlite3, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for k in ("T2R_CLAN_CHRONICLE", "T2R_CLAN_SAGA", "T2R_CLAN_STATUS", "T2R_CLAN_ALIFE"):
    os.environ[k] = "1"
sys.path.insert(0, TOOLS)
import clan_demo_seed  # noqa: E402
import clan_ingame  # noqa: E402
import clan_journal_entries as JE  # noqa: E402
import clan_story as CS  # noqa: E402
import clan_chronicle as CH  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

TID = "0123456789abcdef01234567"
TMP = tempfile.mkdtemp()
def seed(days, seed_=11):
    p = os.path.join(TMP, "s%d_%d.db" % (days, seed_))
    sys.argv = ["x", p, "--days", str(days), "--token", TID, "--seed", str(seed_)]
    clan_demo_seed.main()
    return sqlite3.connect(p)

for days, sd in ((14, 11), (9, 3), (3, 5)):
    c = seed(days, sd)
    feed = CS.read_feed(c, TID, 100, 0, "en", callbacks=True, fold=True)
    pub = CH.public(c, TID, "en") or {}
    ents = JE.compose_entries(feed, list(pub.get("roster", [])))
    tag = "(%d days, seed %d)" % (days, sd)
    ids = [m["id"] for e in ents for m in e["events"]]
    check(sorted(ids) == sorted(m["id"] for m in feed), "every event is in exactly one entry %s: %d events / %d entries" % (tag, len(ids), len(ents)))
    check(all(1 <= len(e["authors"]) <= 2 for e in ents if e["authors"]), "one author per entry, two at most %s" % tag)
    body = ents[1:] if len(ents) > 1 else ents                       # the newest entry may be a short tail (today so far)
    check(all(JE.MIN_EVENTS <= len(e["events"]) <= JE.MAX_EVENTS for e in body), "an entry groups 3..6 events %s" % tag)
    if len(ents) >= 6:
        w = [e["authors"][0] for e in ents[:6] if e["authors"]]
        check(len(set(w)) >= 4, "the newest six entries have several voices: %s %s" % (sorted(set(w)), tag))
        check(all(a != b for a, b in zip(w, w[1:])), "no author writes two entries in a row %s" % tag)
    check(all(not a_set - {p["name"] for p in pub.get("roster", [])} for a_set in (set(a) for a in (e["authors"] for e in ents))), "authors are living roster members %s" % tag)
    out = clan_ingame.build(c, TID, "en", 2)
    J = [l.split("\t") for l in out.split("\n") if l.startswith("J\t")]
    check(J and all(len(j) == 14 for j in J) and not any(l.startswith("L\t") for l in out.split("\n")), "wire: J rows with 14 fields (tag + 13), events inside the bodies %s" % tag)
    check(all(len(j[4].encode("utf-8")) <= 1700 for j in J), "bodies fit the 1720-byte client field %s" % tag)
    check(all(j[11].count("&") <= 1 for j in J), "byline names at most two members %s" % tag)
    pl = clan_ingame.build(c, TID, "pl", 2)
    check(pl.count("\nJ\t") + (1 if pl.startswith("J\t") else 0) >= 1, "pl journal renders %s" % tag)

# chunk(): sizes
def ev(i, d): return {"id": i, "day": d, "week": 1}
for sizes in ([1, 1, 1, 1, 5], [9], [2, 2, 2], [13], [1, 8, 2], [4, 4, 4, 1]):
    evs, i = [], 0
    for d, n in enumerate(sizes, 1):
        for _ in range(n):
            i += 1; evs.append(ev(i, d))
    ch = JE.chunk(evs)
    check(sum(len(x) for x in ch) == len(evs) and all(len(x) <= JE.MAX_EVENTS for x in ch) and all(len(x) >= JE.MIN_EVENTS for x in ch[:-1]), "chunk %s -> %s" % (sizes, [len(x) for x in ch]))

print("FAILED: %d" % len(FAILS) if FAILS else "ALL OK")
sys.exit(1 if FAILS else 0)
