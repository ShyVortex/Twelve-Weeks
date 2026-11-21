"""Admin team rules: quoted / unquoted names with spaces, together is hard at formation, joiner team pick.
Run: python tools/tests/test_team_rules.py"""
import os, sys, socket, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_STEAM_ONLY="0")
import daemon  # noqa: E402
FAILS = []
def check(c, w):
    print(("ok   " if c else "FAIL ") + w)
    if not c: FAILS.append(w)
daemon.get_name = lambda t: t
daemon.token_steamid = lambda t: None
daemon.top_players = lambda tokens: set()
daemon.TEAM_RULES_FILE = os.path.join(tempfile.mkdtemp(), "r.txt")
P = ["PlayerOne", "Player Two", "PlayerTwo", "PlayerThree", "PlayerFour"]
for txt in ('apart PlayerOne PlayerThree\ntogether Player Two PlayerThree\n', 'apart PlayerOne PlayerThree\ntogether "Player Two" PlayerThree\n'):
    daemon.team_rules_set(txt)
    g = dict((k + str(i), v) for i, (k, v) in enumerate(daemon.rule_groups(P)))
    check(g.get("together1") == ["Player Two", "PlayerThree"], "together group (Player Two, PlayerThree) from %r" % txt.splitlines()[1])
    check(g.get("apart0") == ["PlayerOne", "PlayerThree"], "apart group")
sk = {"PlayerOne": 0.62, "Player Two": 0.48, "PlayerThree": 0.7}
q = ["PlayerOne", "Player Two", "PlayerThree"]
t0, t1 = daemon.split_teams(q, {}, sk, set(), daemon.rule_groups(q))
sides = [set(t0), set(t1)]
check(any({"Player Two", "PlayerThree"} <= x for x in sides) and any("PlayerOne" in x for x in sides) and not any({"PlayerOne", "PlayerThree"} <= x for x in sides), "formation: PlayerTwo+jas together, apart from Brandon")
rg = daemon.rule_groups(["PlayerOne", "Player Two", "PlayerThree"])
check(daemon.rule_team_for("PlayerThree", {"PlayerOne": 0, "Player Two": 1}, rg)[0] == 1, "joiner -> PlayerTwo's team")
check(daemon.rule_team_for("PlayerThree", {"PlayerOne": 1, "Player Two": 1}, rg)[0] == 1, "together beats apart when both name the same team")
check(daemon.rule_team_for("PlayerThree", {"PlayerOne": 0}, rg)[0] == 1, "apart only -> other team")
check(daemon.rule_team_for("PlayerThree", {}, rg)[0] is None, "no rule players -> balance")
print("FAILED" if FAILS else "ALL OK"); sys.exit(1 if FAILS else 0)
