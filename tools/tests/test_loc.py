"""Offline checks of the localisation layer (tools/ext/loc.c + tools/loc/pl/*.txt):
  - every entry's placeholders are consistent ({N} / {N|a|b|c} refer to a capture the key has; a key's captures are well formed)
  - the C layer (compiled in a harness with gcc) translates exact texts, composed texts with numbers / names, rich-text segments, plural
    forms and folds Polish letters for the raw text draw
  - widget cipher conversion + language table writing (loc_widgets / loc_tables)
Run: python tools/tests/test_loc.py   (needs the msys gcc of tools/win/ext)."""
import os
import re
import struct
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "loc"))
sys.path.insert(0, os.path.join(TOOLS, "features"))
import locdata  # noqa: E402

GCC = None
for c in (os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe"),
          r"./tools/win/ext/msys64/ucrt64/bin/gcc.exe", "gcc"):
    if os.path.exists(c) or c == "gcc":
        GCC = c
        break

_SPEC = re.compile(r"%(?:\.\d+|\d*)(?:l|ll|z)*[dusfxc]")


def check_entries():
    rows = locdata.load("pl")
    assert len(rows) > 500, len(rows)
    for g, k, v, rk, rv in rows:
        keyk = k.replace("%%", "")
        ncap = len(_SPEC.findall(keyk))
        for m in re.finditer(r"\{=?(\d)(\|[^{}]*)?\}", v):
            n = int(m.group(1))
            assert 1 <= n <= max(ncap, 1) and (ncap or "[A]" in k), "bad capture {%d} in [%s] %s -> %s" % (n, g, k, v)
        assert v.count("{") == v.count("}"), "unbalanced braces: " + v
        # parity: every number / name capture of the English key is used by the Polish text (a plural-word %s after a number, "round%s" / "%d %s LEFT", may be dropped)
        specs = list(_SPEC.finditer(keyk))
        used = {int(m.group(1)) for m in re.finditer(r"\{=?(\d)", v)}
        for i, sp in enumerate(specs, 1):
            suffix = sp.group(0).endswith("s") and (keyk[sp.start() - 1:sp.start()].isalnum() or keyk[:sp.start()].rstrip().endswith(("%d", "%s")) or keyk[sp.end():].startswith(" LEFT"))
            assert i in used or suffix, "capture %d of the key is not used in [%s] %s -> %s" % (i, g, k, v)
        assert not _SPEC.search(v.replace("%%", "")) or "%" not in v.replace("%%", "").replace("%", "", 0) or True
        assert not re.search(r"%(?:\.\d+|\d*)(?:l|ll|z)*[dusfxc]", v), "format specifier in a translation (use {N}): " + v
    print("entries ok:", len(rows))


def build_harness():
    exe = os.path.join(tempfile.gettempdir(), "t2r_loc_harness.exe")
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(GCC) + os.pathsep + env["PATH"] if os.path.dirname(GCC) else env["PATH"]
    subprocess.run([GCC, "-std=gnu2x", "-O1", "-o", exe, os.path.join(HERE, "loc_harness.c")], check=True, env=env)
    return exe


def run(exe, lines, mode="pl"):
    r = subprocess.run([exe, mode], input="\n".join(lines).encode("utf-8"), capture_output=True, check=True)
    return [x.rstrip("\r") for x in r.stdout.decode("utf-8").split("\n")][:len(lines)]


CASES = [
    ("KILLED BY", "ZABITY PRZEZ"),
    ("RESPAWNING IN", "ODRODZENIE ZA"),
    ("WEEK 3: DAY 5", "TYDZIEŃ 3: DZIEŃ 5"),
    ("HEALTHY: 12", "ZDROWI: 12"),
    ("%d" and "5 SURVIVORS", "OCALALI: 5"),
    ("SHORT BY 4 SUPPLIES", "BRAKUJE ZAOPATRZENIA: 4"),
    ("3 Points", "3 punkty"),
    ("1 Point", "1 punkt"),
    ("7 Points", "7 punktów"),
    ("12 Points", "12 punktów"),
    ("22 Points", "22 punkty"),
    ("REVOLVER AMMO", "AMUNICJA: REWOLWER"),
    ("SUPPRESSED ENFORCER AMMO", "AMUNICJA: EGZEKUTOR Z TŁUMIKIEM"),
    ("Revolver rounds for your Revolver.", "Naboje rewolwerowe dla twojego Rewolwera."),
    ("Bolts for your Crossbow.", "Bełty dla twojej Kuszy."),
    ("Pistol rounds for your Suppressed Enforcer.", "Naboje pistoletowe dla twojego Egzekutora."),
    ("FIND MATCH", "ZNAJDŹ MECZ"), ("LEADERBOARDS", "TABELA"), ("OPTIONS", "OPCJE"), ("QUIT", "WYJDŹ"), ("CONNECTING", "ŁĄCZENIE"),
    ("SURVIVORS GAINED:", "NOWI OCALALI:"),
    ("Hides shots from appearing on enemy radar.", "Chowa strzały przed pojawianiem się na radarze przeciwnika."),
    ("HUNTING RIFLE UPGRADE II", "KARABIN MYŚLIWSKI - ULEPSZENIE II"),
    ("SHARP EARS II", "CZUŁY SŁUCH II"),
    ("EQUIPPED III", "W UŻYCIU: III"),
    ("3 CLAN MEMBERS DIED IN THE WLF ATTACK", "W ATAKU WLF ZGINĘŁO CZŁONKÓW KLANU: 3"),
    ("MATCH STARTS IN <font color=\"#e04848\">00:12</font>", "MECZ ROZPOCZNIE SIĘ ZA <font color=\"#e04848\">00:12</font>"),
    ("DAY DONE  -  DAILY SUPPLIES: <font color=\"#3fa9f5\">+14</font>   SURVIVORS GAINED: 2",
     "DZIEŃ ZAKOŃCZONY  -  DZIENNE ZAOPATRZENIE: <font color=\"#3fa9f5\">+14</font>   NOWI OCALALI: 2"),
    ("RISK: <font color=\"#e04848\">25%</font> OF POPULATION", "RYZYKO: <font color=\"#e04848\">25%</font> POPULACJI"),
    ("LOADING...", "WCZYTYWANIE..."),
    ("LOADING.", "WCZYTYWANIE."),
    ("2 / 9 Downs  -  1 MATCH LEFT", "Powalenia: 2 / 9  -  pozostało meczów: 1"),
    ("MISSION COMPLETE: 9 Downs (TIER 2)", "MISJA UKOŃCZONA: Powalenia - 9 (POZIOM 2)"),
    ("3 Downs:   +1 SURVIVOR   +1 BOOSTER", "Powalenia: 3   Ocalali: +1   Dopalacze: +1"),
    ("6 Downs:   LOSE 25%   +2 BOOSTERS", "Powalenia: 6   Strata: 25%   Dopalacze: +2"),
    ("<color=red>Bob</color> killed <color=blue>Al</color>", "<color=red>Bob</color> zabił <color=blue>Al</color>"),
    ("Hold E to break into the enemy lockbox (stage 2 of 3)", "Przytrzymaj E, aby włamać się do skrytki wroga (etap 2 z 3)"),
    ("Starts with 1 round.", "Zaczynasz z 1 nabojem."),
    ("Ammo: 3 rounds for 120 parts.", "Amunicja: 3 naboje za 120 części."),
    ("Ammo: 8 rounds for 120 parts.", "Amunicja: 8 naboi za 120 części."),
    ("The host left - FREE is hosting now", "Host wyszedł - teraz hostuje: FREE"),      # a player name that equals an entry stays as typed
    ("Scavenger: ammo + supplies", "Zbieracz: amunicja i zapasy"),
    ("Version mismatch: your game is build abc but this server runs def. Get the current download from your host and start it with Play.bat.",
     "Niezgodność wersji: twoja gra to kompilacja abc, a serwer działa na def. Pobierz aktualną wersję od hosta i uruchom ją przez Play.bat."),
    ("Zabity przez Bob", "Zabity przez Bob"),                     # a text the table does not know passes through
    ("Player123", "Player123"),
    ("", ""),
    ("DOWNED ENEMY\\nEXECUTION", "POWALONY WRÓG\\nEGZEKUCJA"),
    ("SPECIAL EXECUTION", "EGZEKUCJA SPECJALNA"),
]


def check_layer():
    if not GCC:
        print("no gcc: C layer test skipped")
        return
    exe = build_harness()
    got = run(exe, [c[0] for c in CASES])
    bad = 0
    for (src, want), g in zip(CASES, got):
        if g != want:
            bad += 1
            print("FAIL: %r\n   got  %r\n   want %r" % (src, g, want))
    assert not bad, "%d C layer case(s) failed" % bad
    folded = run(exe, ["KILLED BY", "REWOLWER", "SHARP EARS"], "draw")
    assert folded[0] == "ZABITY PRZEZ" and folded[2] == "CZUŁY SŁUCH".replace("Ł", "L").replace("Ó", "O").replace("Ś", "S").replace("Ć", "C"), folded
    assert run(exe, ["KILLED BY"], "en") == ["KILLED BY"]       # English: untouched
    print("C layer ok:", len(CASES), "cases")


def check_tables():
    import loc_widgets
    import loc_tables
    d = tempfile.mkdtemp()
    t = {0x11: b"a", 0x22: b"bb"}
    p = os.path.join(d, "x.common")
    loc_tables.save(p, t)
    assert loc_tables.load(p) == t
    n1 = loc_widgets.cipher_name("KILLED BY")
    assert n1 == loc_widgets.cipher_name("KILLED BY") and n1.startswith("T2RL_")
    print("tables ok")


if __name__ == "__main__":
    check_entries()
    check_layer()
    check_tables()
    print("ALL OK")
