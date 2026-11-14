"""Reads the translation files tools/loc/<code>/*.txt.

Format (UTF-8, one entry per line):
  ## Group name                 starts a group (the review file lists the groups); "(+upper)" in the name also adds the
                                 upper-case twin of every entry (the post-match tally upper-cases its labels)
  English text => Translation   an entry; "\\n" = a newline; {1} {2} .. = captured %d / %s of the key, {N|a|b|c} = plural
  # comment                     ignored
Keys / values are trimmed for the runtime table; the raw (untrimmed) pair is kept for patches of the game's own text table
(trailing blanks matter there)."""
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _un(s):
    return s.replace("\\n", "\n")


def load(code):
    """-> [(group, key, value, raw_key, raw_value)] (first definition of a key wins)"""
    out, seen = [], set()
    for f in sorted(glob.glob(os.path.join(HERE, code, "*.txt"))):
        group = os.path.basename(f)
        for line in open(f, encoding="utf-8", newline="").read().split("\n"):
            line = line.rstrip("\r")
            if line.startswith("## "):
                group = line[3:].strip()
                continue
            if not line.strip() or line.startswith("#") or " => " not in line:
                continue
            rk, rv = line.split(" => ", 1)
            rk, rv = _un(rk), _un(rv)
            pairs = [(rk, rv)]
            if group.endswith("(+upper)"):
                pairs.append((rk.upper(), rv.upper()))
            for k, v in pairs:
                kk = k.strip()
                norm = kk.replace("%u", "%d")
                if norm in seen or not v.strip():
                    continue
                seen.add(norm)
                out.append((group.replace("(+upper)", "").strip(), kk, v.strip(), k, v))
    return out
