"""Clan supply perks (tools/clan_perks.py): surplus -> active perks + credited member, wire text, uses drawn from the stock, the saga line.
Run: python tools/tests/test_clan_perks.py   (plain python; temp database only)."""
import json, os, random, re, sqlite3, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import clan, clan_perks as P, clan_story as CS, clan_supply as S   # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

d = tempfile.mkdtemp()
c = sqlite3.connect(os.path.join(d, "t2r.db"))
tid = "0123456789abcdef01234567"
clan.choose_side(c, tid, clan.WLF)
clan.rng = random.Random(1)
cl, r = clan.apply_match(c, tid, 201, 2400, False, {1: 12, 2: 2, 3: 3, 4: 5})        # a big surplus day: stock banked
CS.on_day(c, tid, cl, r)
cl = clan.load(c, tid)
stock = P.stock_of(cl)
need = P.need_of(cl)
check(any(stock[k] > 0 for k in S.CATS), "setup: the surplus day banked goods %r" % stock)
sp = P.surplus(cl)
check(all(sp[k] == max(0, stock[k] - need[k]) for k in S.CATS), "surplus = stock - one day of need")
# force a known stock so the numbers are exact
meta = clan.meta_of(cl)
meta["sup"] = {"stock": {"food": need["food"] + 1, "water": need["water"], "med": need["med"] + 9, "ammo": need["ammo"] + 2, "mat": 0}}
cl["meta"] = json.dumps(meta)
clan.save(c, tid, cl)
cl = clan.load(c, tid)
story = CS._load(c, tid)
pk = P.active(cl, story)
keys = {p["key"]: p for p in pk}
check(set(keys) == {"stamina", "medkit", "clip"}, "active perks = the categories with a surplus (food +1, med +9, ammo +2): " + ",".join(keys))
check(keys["medkit"]["cap"] == 2 and keys["clip"]["cap"] == 2 and keys["stamina"]["cap"] == 1, "caps: medkit 2 (cap), clip min(3, surplus 2) = 2, stamina 1")
check(all(p["who"] and p["who"]["n"] for p in pk), "every perk names a member (with or without credit)")
check(not P.active(dict(cl, status=clan.DEAD), story) and not P.active(None), "no perks for a dead clan / no clan")
os.environ["T2R_CLAN_PERKS"] = "0"
check(P.active(cl, story) == [], "T2R_CLAN_PERKS=0 switches the perks off")
del os.environ["T2R_CLAN_PERKS"]
# ---- wire text
t = P.wire_text(pk)
check(t.startswith("pk=3 ") and "pkc0=1" in t and re.search(r"pkm0=[A-Za-z_'-]+", t), "wire text: " + t[:120])
ints_first = t.index("pkm0=") > max(t.index("pkr%d=" % i) for i in range(3))
check(ints_first, "wire text: all integer keys come before the names (an old ext stops at the first name)")
check(P.wire_text([]) == "", "no perks = no tail (an old daemon looks the same)")
# the ext's parser (clanperk.c cp_parse) mirrored: key=value tokens
kv = dict(x.split("=", 1) for x in t.split())
check(int(kv["pk"]) == 3 and int(kv["pkn0"]) == 2 and kv["pkm0"] == pk[0]["who"]["n"].replace(" ", "_"), "wire text round trips")
# ---- uses
check(P.uses_of({31: 2 | (3 << 4), 32: 1 | (1 << 4)}) == {"med": 2, "ammo": 3, "food": 1, "water": 1}, "uses_of unpacks the nibbles")
check(P.uses_of({31: 15}) == {"med": 2} and P.uses_of({}) == {} and P.uses_of(None) == {}, "uses_of clamps to the per-match cap")
# ---- credit: the day's goods go to a member by role, the most credited one is named
st2 = CS._load(c, tid)
for day in range(1, 12):
    P.credit_day(st2, {"med": 4, "ammo": 0, "mat": 0, "food": 0, "water": 0}, day)
who = P.credit_of(st2, "med")
cr = st2["ch"]["pk"]["cr"]["med"]
top = max(cr.items(), key=lambda kv: (kv[1], -int(kv[0])))
check(who is not None and str(who["i"]) == top[0] and sum(cr.values()) == 44, "credit_of = the most credited living member; credits add up")
check("ammo" not in st2["ch"]["pk"]["cr"], "no intake, no credit")
# ---- on_day: draws the uses from the stock (floor 0), writes the saga line (EN + PL), credits the day
before = P.stock_of(clan.load(c, tid))
cl3, r3 = clan.apply_match(c, tid, 202, 600, False, {1: 4})
CS.on_day(c, tid, cl3, r3)
mid = P.stock_of(clan.load(c, tid))
drawn = P.on_day(c, tid, cl3, r3, {31: 2 | (1 << 4), 32: 1}, {"map": "Hillside"})
after = P.stock_of(clan.load(c, tid))
check(sorted(drawn) == [("ammo", 1), ("food", 1), ("med", 2)], "on_day reports the uses drawn: %r" % (drawn,))
check(after["med"] == max(0, mid["med"] - 2) and after["ammo"] == max(0, mid["ammo"] - 1) and after["food"] == max(0, mid["food"] - 1), "each use draws 1 from the stock (%r -> %r)" % (mid, after))
check(P.on_day(c, tid, cl3, r3, {31: 15 << 8}, {}) and P.stock_of(clan.load(c, tid))["mat"] >= 0, "a draw on an empty stock stops at 0")
# A used perk writes NO feed row any more (such rows made up most of the feed text, "x kept you going on (map)"); it is one sentence in the day's journal entry
# (tools/clan_journal.add_perk: a line is used once per clan run, one sentence a day)
rows = CS.read_feed(c, tid, 50, lang="en")
check(not [m for m in rows if m.get("style") == "perk"], "a used perk writes no feed row")
import clan_journal as CJ
recs = [json.loads(d) for (d,) in c.execute("SELECT data FROM clan_journal WHERE token_id=? ORDER BY day", (tid,))]
pks = [q for rec in recs for para in rec["pa"] for q in para[2] if q[0].startswith("jn/perk_")]
check(len(pks) == 1 and sum(1 for rec in recs if rec.get("pk")) == 1, "the day's journal entry gets ONE perk sentence for the three uses (%d)" % len(pks))
en_t, pl_t = (CJ.render(pks[0], "en"), CJ.render(pks[0], "pl")) if pks else ("", "")
check(en_t and pl_t and en_t != pl_t and "{" not in en_t + pl_t, "the sentence renders in English and Polish: " + en_t)
check(" at " not in P.line("med", {"n": "Tyler", "g": "m"}, "", "en", 0) and "{" not in P.line("med", {"n": "Tyler", "g": "m"}, "", "pl", 1) and re.search(r"Dina \w+ła", P.line("med", {"n": "Dina", "g": "f"}, "", "pl", 0)), "no map name drops the place; female members take feminine Polish verbs")
who2 = CS._load(c, tid)
check(sum(sum(v.values()) for v in who2["ch"]["pk"]["cr"].values()) > 0, "on_day credits the day's goods")
# ---- every line template fills in cleanly, both languages, both genders
bad = 0
for cat in P.LINES:
    for g in ("m", "f"):
        for lang in ("en", "pl"):
            for day in range(8):
                t = P.line(cat, {"n": "Tyler", "g": g}, "Hillside", lang, day)
                if "{" in t or "Tyler" not in t or "Hillside" not in t or (lang == "pl" and g == "f" and re.search(r"Tyler \w+³", t)):
                    bad += 1
check(bad == 0, "all %d saga line templates fill in" % (len(P.LINES) * 2 * 2 * 2))
check(P.render_msg("pk/use", {"t": "a", "tp": "b"}, "en") == "a" and P.render_msg("pk/use", {"t": "a", "tp": "b"}, "pl") == "b" and P.render_msg("ch/x", {}, "en") is None, "render_msg")
# ---- loss streak: trailing lost matches of the saga history; a plain day neither counts nor breaks it
H = lambda *w: {"ch": {"sg_hist": [{"d": i, "win": x} for i, x in enumerate(w)]}}
check(P.loss_streak(H(True, False, False)) == 2 and P.loss_streak(H(False, False, True)) == 0 and P.loss_streak(H(False, None, False, False)) == 3, "loss_streak: trailing losses, plain days skipped")
check(P.loss_streak(None) == 0 and P.loss_streak({}) == 0 and P.loss_streak({"ch": {"log": [{"win": False}, {"win": False}]}}) == 2 and P.loss_streak(H(*([False] * 20))) == 9, "loss_streak: unknown = 0, falls back to the raid log, capped at 9")
t2 = P.wire_text(pk, 3)
kv2 = dict(x.split("=", 1) for x in t2.split())
check(kv2["pks"] == "3" and t2.index("pks=") < t2.index("pkc0=") and P.wire_text(pk, 0) == P.wire_text(pk) and P.wire_text([], 5) == "", "wire text: pks=<streak> only with a streak, ints first, nothing without perks")
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
