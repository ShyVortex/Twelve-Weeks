"""Op 0xE2 re-send (ext outage hardening, re/ext-daemon-outage-1019.md): the ext sends the match report again until it gets a reply, so a report
whose first copy was already booked must be acknowledged and NOT booked twice (parts_total / parts_n, the clan day). Temp DB only.
Run: python tools/tests/test_clan_report_resend.py"""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TMP = tempfile.mkdtemp()
os.environ["T2R_DB"] = os.path.join(TMP, "t.db")
sys.path.insert(0, TOOLS)
import daemon  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

TOK = "54324e3a" + "416c696365" + "00" * 11 + "0123456789abcdef01234567"
def totals():
    with daemon._dblock, daemon.dbc() as c:
        r = c.execute("SELECT parts_total, parts_n FROM players WHERE token = ?", (TOK,)).fetchone()
    return tuple(r) if r else None

daemon.clan_side(TOK, 1)
daemon.clan_match_started([TOK], "mid1")
with daemon._dblock, daemon.dbc() as c:                      # a players row exists for the token (login does this live)
    try: c.execute("INSERT OR IGNORE INTO players (token) VALUES (?)", (TOK,))
    except Exception as e: print("note: players insert", e)
st1 = daemon.clan_report(TOK, 100, 2)                        # first copy: resolved at once (flag bit 1)
t1 = totals()
day1 = daemon.clan.state_text(st1)
st2 = daemon.clan_report(TOK, 100, 2)                        # the re-send after a lost reply
t2 = totals()
check(t1 is not None and t1[1] == 1, "first report booked once (%s)" % (t1,))
check(t2 == t1, "re-sent report not booked again (parts_total / parts_n %s -> %s)" % (t1, t2))
check(TOK not in daemon.CLAN_PENDING, "re-sent report leaves nothing pending")
check(daemon.clan.state_text(st2) == daemon.clan.state_text(daemon.clan_state(TOK)), "re-send is answered with the current state (the client's acknowledgement)")
# a new match is booked normally
daemon.clan_match_started([TOK], "mid2")
daemon.clan_report(TOK, 50, 2)
t3 = totals()
check(t3 is not None and t3[1] == 2, "the next match's report is booked (%s)" % (t3,))
print("\nall passed" if not FAILS else "\n%d FAILED" % len(FAILS))
sys.exit(1 if FAILS else 0)
