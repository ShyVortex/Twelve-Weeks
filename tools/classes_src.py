"""Reads the pre-made classes (GEAR UP presets) from their one source, CLASSES[] in tools/ext/t2r-ext.c.

Used by release/launcher/scripts/gen-gamedata.py (launcher data) and tools/tests/test_classes.py. Returns
[{"name", "desc", "w": [large, small, purchasable] (weapon id or None; "<id>-supp" = the suppressed variant),
  "skills": [(SK_KEY, level) x3 + the 4th row if any]}]."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_C = os.path.join(ROOT, "tools", "ext", "t2r-ext.c")


def parse(path=EXT_C):
    src = open(path, encoding="utf-8", errors="replace").read()
    a = src.index("CLASSES[] = {")
    b = src.index("\n};", a)
    blk = "\n".join(re.sub(r"\s//.*$", "", l) for l in src[a:b].split("\n"))
    out = []
    pat = re.compile(r'\{"([A-Z]+)",\s*((?:"(?:[^"\\]|\\.)*"\s*)+),\s*\{([^}]*)\},\s*\{\{0, 0, 0\}, \{([^}]*)\}\},\s*(0|SK_V\(SK_[A-Z]+, \d\))\}', re.S)
    for m in pat.finditer(blk):
        name, desc, ws, sk, s4 = m.groups()
        desc = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', desc))
        w = [x.group(1) if x.group(1) else None for x in re.finditer(r'"([^"]+)"|NULL', ws)]
        sks = re.findall(r"SK_V\((SK_[A-Z]+), (\d)\)", sk) + re.findall(r"SK_V\((SK_[A-Z]+), (\d)\)", s4)
        out.append({"name": name, "desc": desc, "w": w, "skills": [(k, int(v)) for k, v in sks]})
    # every entry of the table must have been parsed (an entry starts with {"NAME", at 4 spaces of indent)
    n_entries = len(re.findall(r'^    \{"[A-Z]+",', blk, re.M))
    assert out and len(out) == n_entries and all(len(c["w"]) == 3 for c in out), "CLASSES[] parse failed (%d of %d entries)" % (len(out), n_entries)
    return out


if __name__ == "__main__":
    for c in parse():
        print(c["name"], c["w"], c["skills"])
