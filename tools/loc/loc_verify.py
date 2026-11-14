"""Is a translation key (or each literal part of a pattern key) really present in a text source of the mod?

Sources: the string literals of tools/ext/*.c|h (adjacent literals joined, C escapes resolved), tools/features/*.py, daemon.py / names.py /
clan.py, plus tools/loc/extern.txt (texts of winmm.dll and the game's own tables that the mod shows but this repo does not contain).
  python loc_verify.py            -> lists every key of every language file that is NOT found (composed / extern texts show up here)
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)

_C_ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "'": "'", "r": "\r"}
_LIT = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
_corpus = None


def _unc(s):
    return re.sub(r"\\(.)", lambda m: _C_ESC.get(m.group(1), m.group(1)), s)


def _c_texts(text):
    # join adjacent string literals ("a" "b" and across lines / macro continuation)
    out = []
    for m in re.finditer(r'(?:"(?:[^"\\\n]|\\.)*"\s*)+', text):
        out.append("".join(_unc(x) for x in _LIT.findall(m.group(0))))
    return out


def corpus():
    global _corpus
    if _corpus is not None:
        return _corpus
    parts = []
    for f in glob.glob(os.path.join(TOOLS, "ext", "*.c")) + glob.glob(os.path.join(TOOLS, "ext", "*.h")):
        if os.path.basename(f).startswith("loc_"):
            continue
        parts += _c_texts(open(f, encoding="utf-8", errors="replace").read())
    for f in glob.glob(os.path.join(TOOLS, "features", "*.py")) + [os.path.join(TOOLS, n) for n in ("daemon.py", "names.py", "clan.py")]:
        if not os.path.exists(f):
            continue
        s = open(f, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"""(?:"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)')""", s):
            parts.append(_unc(m.group(1) if m.group(1) is not None else m.group(2)))
    ex = os.path.join(HERE, "extern.txt")
    if os.path.exists(ex):
        parts += [l.rstrip("\r\n") for l in open(ex, encoding="utf-8")]
    _corpus = "\0".join(parts)
    return _corpus


def _lits(key):
    # literal parts of a pattern key (split at %d %s %.1f ...); "%%" stays "%%" (the source holds the C format)
    out, cur, i = [], "", 0
    while i < len(key):
        if key[i] == "%" and key[i + 1:i + 2] == "%":
            cur += "%%"; i += 2; continue
        m = re.match(r"%(?:\.\d+|\d*)(?:l|ll|z)*[dusfxc]", key[i:])
        if key[i] == "%" and m:
            out.append(cur); cur = ""; i += len(m.group(0)); continue
        cur += key[i]; i += 1
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def verify(keys):
    c = corpus()
    res = []
    for k in keys:
        res.append(all(p in c for p in _lits(k)))
    return res


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    import locdata
    for code in sys.argv[1:] or ["pl"]:
        rows = locdata.load(code)
        for (g, k, v, rk, rv), ok in zip(rows, verify([r[1] for r in rows])):
            if not ok:
                print("[%s] %s" % (g[:30], k[:140]))
