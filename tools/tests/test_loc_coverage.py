"""Localisation coverage: every user-visible English literal the ext hands to a text sink must translate in Polish.

Sinks (function -> index of the text argument): msg_hook, msg_tag, ntf_push, dn_show, ui_text, ui_text_db, ls_text, du_text, pm_text,
mw_show, ui_deny, world_prompt, wpq_begin, popup_push, award, ev_pay (label; its `why` is a log line), imm_text_center, int_text_c.
Per call the text argument is resolved to its literals: the string literals of the expression itself (ternaries, adjacent literals)
or - for a plain variable - the format / literal strings the same function put into it (snprintf(var, .., "fmt"), var = "lit").
Format strings are rendered with sample values (%d -> 7, %s -> a name) and run through a Python port of loc.c's loc_core (exact key,
printf-capture templates, rich-text / newline splitting), so a composed text passes exactly when the game would translate it.
A literal also passes when it is a template key itself (the format string equals a key after %u -> %d).
A literal is exempt when it has no 3-letter run (glyphs, numbers) or is an id / path token (lower-case, no spaces).
Add an exempt literal to ALLOW below only when it is never shown to players (debug logs, widget paths).

Run: python tools/tests/test_loc_coverage.py [-v]   (-v also lists unresolved variable arguments)"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "loc"))
import locdata  # noqa: E402

SINKS = {"msg_hook": [0], "msg_tag": [0], "ntf_push": [1], "dn_show": [0], "ui_text": [1], "ui_text_db": [1], "ls_text": [1],
         "du_text": [1], "pm_text": [2], "mw_show": [0], "ui_deny": [0], "world_prompt": [1], "wpq_begin": [0], "popup_push": [1],
         "award": [2], "ev_pay": [2], "T2R_PROMPT_MSG": [0], "imm_text_center": [3], "int_text_c": [5]}
# literals that are shown to nobody (or are engine tokens): exact text. Dev-only F-key tools (sound audition / probe).
ALLOW = {"FAR sound %d/%d: %s%s", " (finding the gun's sound, press again)", "sound probe %d: %s -> %llx",
         "puppet", "FAILED",
         "one", "a few", "them"}                     # (the F-key animation hotkey line "%s %s -> %s")
# composed texts whose %s take fixed word sets (positional): every combination must translate
FORMAT_ARGS = {
    "Only %s %s per team - a teammate already has %s. Your loadout was switched to %s.": [
        ("one", "Tactical Shotgun", "it", "Rifle"), ("a few", "Tactical Shotgun", "them", "Rifle")],
}
# values the %s captures of composed texts take at run time (faction names, weapon names, ...): a format passes when it translates
# with at least ONE of these filling every %s
SAMPLES = ["Player", "Seraphites", "WLF", "SERAPHITE", "SERAPHITES", "Rifle", "Pistol", "Bow"]

C_ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "'": "'", "r": "\r"}
_SPEC = re.compile(r"%(?:\.\d+|\d*)(?:l|ll|z|h|hh)*([dusfxXcg])")


def unesc(s):
    return re.sub(r"\\(.)", lambda m: C_ESC.get(m.group(1), m.group(1)), s)


def strip_comments(t):
    out, i, n = [], 0, len(t)
    while i < n:
        c = t[i]
        if c == '"' or c == "'":
            j = i + 1
            while j < n and t[j] != c:
                j += 2 if t[j] == "\\" else 1
            out.append(t[i:j + 1])
            i = j + 1
        elif t.startswith("//", i):
            while i < n and t[i] != "\n":
                i += 1
        elif t.startswith("/*", i):
            j = t.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * t.count("\n", i, j))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def split_args(s):
    args, depth, cur, i, n = [], 0, [], 0, len(s)
    while i < n:
        c = s[i]
        if c == '"' or c == "'":
            j = i + 1
            while j < n and s[j] != c:
                j += 2 if s[j] == "\\" else 1
            cur.append(s[i:j + 1])
            i = j + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    args.append("".join(cur).strip())
    return args


def call_args(t, start):
    """t[start:] is the text after '('; returns the argument text up to the matching ')'"""
    depth, i, n = 1, start, len(t)
    while i < n and depth:
        c = t[i]
        if c == '"' or c == "'":
            j = i + 1
            while j < n and t[j] != c:
                j += 2 if t[j] == "\\" else 1
            i = j + 1
            continue
        depth += c in "([{"
        depth -= c in ")]}"
        i += 1
    return t[start:i - 1]


_LITS = re.compile(r'(?:"(?:[^"\\\n]|\\.)*"\s*)+')
_ONE = re.compile(r'"((?:[^"\\\n]|\\.)*)"')


def literals(expr):
    return ["".join(unesc(x) for x in _ONE.findall(m.group(0))) for m in _LITS.finditer(expr)]


_FN = re.compile(r"^[A-Za-z_][^\n;{}]*\)\s*\{\s*$|^[A-Za-z_][^\n;]*\)\s*$", re.M)


def fn_start(t, pos):
    m = None
    for m in _FN.finditer(t, 0, pos):
        pass
    return m.start() if m else max(0, pos - 6000)


def var_literals(t, pos, var):
    """literals put into `var` earlier in the same function: snprintf(var, .., "fmt"), var = cond ? "a" : "b", str*cpy"""
    out = []
    seg = t[fn_start(t, pos):pos]
    for m in re.finditer(r"\b(?:snprintf|sprintf|strcpy|strncpy|strcat)\s*\(\s*" + re.escape(var) + r"\b", seg):
        k = seg.index("(", m.start()) + 1
        out += literals(call_args(seg, k))
    for m in re.finditer(r"(?:^|[;{}\s\*])" + re.escape(var) + r"(?:\[\d*\])?\s*=\s*([^;]*);", seg):
        out += literals(m.group(1))
    return out


def _members(body):
    """member names of a struct body in declaration order"""
    out = []
    for decl in body.split(";"):
        decl = decl.strip()
        if not decl:
            continue
        for part in decl.split(","):
            nm = re.findall(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*$", part.strip())
            if nm:
                out.append(nm[0])
    return out


def _block(t, i):
    """index just past the {...} block whose '{' is at t[i-1]"""
    depth = 1
    while i < len(t) and depth:
        c = t[i]
        if c == '"':
            j = i + 1
            while j < len(t) and t[j] != '"':
                j += 2 if t[j] == "\\" else 1
            i = j
        depth += c == "{"
        depth -= c == "}"
        i += 1
    return i


def table_literals(texts, base, field=None, col=None):
    """literals of the `BASE[..] = { ... }` initializer in any ext source. With a struct member name (SK[id].name): only that
    member's literals, found by its position in the struct declaration (typedef or inline); without: every literal of the table."""
    out = []
    for t in texts:
        for m in re.finditer(r"\b" + re.escape(base) + r"\s*(?:\[[^\]=;]*\]\s*)+=\s*\{", t):
            end = _block(t, m.end())
            body = t[m.end():end - 1]
            if col is not None:                                  # LBL[i][1]: column `col` of a 2-D table
                for el in split_args(body):
                    el = el.strip()
                    if el.startswith("{") and el.endswith("}"):
                        items = split_args(el[1:-1])
                        if col < len(items):
                            out += literals(items[col])
                continue
            if not field:
                out += literals(body)
                continue
            head = t[max(0, m.start() - 400):m.start()]
            mem = None
            sm = re.search(r"struct\s*\{([^{}]*)\}\s*$", head)
            if sm:
                mem = _members(sm.group(1))
            else:
                tn = re.search(r"([A-Za-z_]\w*)\s+$", head.replace("const ", ""))
                if tn:
                    for tt in texts:
                        td = re.search(r"typedef\s+struct\s*(?:\w+\s*)?\{([^{}]*)\}\s*" + re.escape(tn.group(1)) + r"\s*;", tt)
                        if td:
                            mem = _members(td.group(1))
                            break
            if not mem or field not in mem:
                continue
            ix = mem.index(field)
            for el in split_args(body):
                el = re.sub(r"^\[[^\]]*\]\s*=\s*", "", el.strip())
                if el.startswith("{") and el.endswith("}"):
                    items = split_args(el[1:-1])
                    if ix < len(items):
                        out += literals(items[ix])
    return out


# ---- Python port of loc.c lookups -----------------------------------------------------------------------------------------------
class Loc:
    def __init__(self):
        rows = locdata.load("pl")
        self.exact, self.tpl = {}, []
        for g, k, v, rk, rv in rows:
            if self._has_cap(k):
                self.tpl.append((self._regex(k), k))
            else:
                self.exact[k] = v
        self.keys = {self._norm(k) for g, k, v, rk, rv in rows}

    @staticmethod
    def _norm(k):
        return _SPEC.sub(lambda m: "%d" if m.group(1) in "dufxXg" else "%s", k.replace("%%", "\0")).replace("\0", "%%")

    @staticmethod
    def _has_cap(k):
        return bool(_SPEC.search(k.replace("%%", "")))

    @staticmethod
    def _regex(k):
        out, i = [], 0
        k = k.replace("%%", "\0")
        for m in _SPEC.finditer(k):
            out.append(re.escape(k[i:m.start()]).replace("\0", "%"))
            out.append(r"[+-]?\d+(?:\.\d+)?" if m.group(1) in "dufxXg" else r"(?:.*?)")
            i = m.end()
        out.append(re.escape(k[i:]).replace("\0", "%"))
        return re.compile("^" + "".join(out) + "$", re.S)

    def piece(self, s):
        s = s.strip(" \t")
        if not s or not re.search(r"[A-Za-z]", s):
            return True                                      # nothing to translate
        if s in self.exact:
            return True
        return any(rx.match(s) for rx, _ in self.tpl)

    def core(self, s):
        """untranslated text pieces of s ([] = the game translates it): whole string first, then split at tags and newlines"""
        if self.piece(s):
            return []
        miss = []
        for p in re.split(r"(<[^>\n]*>|\|[^|\n]*\||\n)", s):
            if not p or p == "\n" or (len(p) > 1 and p[0] in "<|" and p[-1] in ">|"):
                continue
            if not self.piece(p):
                miss.append(p.strip())
        return miss


def render(fmt, word="Player", args=None):
    it = iter(args or ())

    def sub(m):
        if args is not None:
            return str(next(it, word))
        return "7" if m.group(1) in "dufxXg" else ('"' if m.group(1) == "c" else word)
    return _SPEC.sub(sub, fmt.replace("%%", "\0")).replace("\0", "%")


def needs_check(s):
    bare = re.sub(r"<[^>]*>|%(?:\.\d+|\d*)(?:l|ll|z|h|hh)*[a-zA-Z]", "", s)     # rich-text tags and captures carry no wording
    if not re.search(r"[A-Za-z]{3}", bare):
        return False
    if re.fullmatch(r"[A-Za-z0-9_.\-/\\:%]+", s) and re.search(r"[./\\]", s):  # an asset / widget path or file name
        return False
    return s not in ALLOW


def scan():
    loc = Loc()
    missing, unresolved, checked = {}, [], 0
    files = [f for f in sorted(glob.glob(os.path.join(TOOLS, "ext", "*.c")) + glob.glob(os.path.join(TOOLS, "ext", "*.h")))
             if not os.path.basename(f).startswith("loc_")]
    pat = re.compile(r"\b(" + "|".join(SINKS) + r")\s*\(")
    texts = [strip_comments(open(f, encoding="utf-8", errors="replace").read()) for f in files]
    for f, t in zip(files, texts):
        for m in pat.finditer(t):
            name = m.group(1)
            head = t[t.rfind("\n", 0, m.start()) + 1:m.start()]
            if head.strip() and re.fullmatch(r"\s*(?:static\s+)?[A-Za-z_][\w\s\*]*", head) and not re.match(r"\s*(?:return|else)\b", head):
                continue                                  # a declaration / definition, not a call
            args = split_args(call_args(t, m.end()))
            ln = t.count("\n", 0, m.start()) + 1
            for ix in SINKS[name]:
                if ix >= len(args):
                    continue
                e = args[ix]
                lits = literals(e)
                if not lits:
                    var = re.fullmatch(r"([A-Za-z_]\w*)", e)
                    if var:
                        lits = var_literals(t, m.start(), var.group(1))
                    for base, fld, col in re.findall(r"\b([A-Za-z_]\w*)\s*\[[^\]]*\](?:\s*\.\s*([A-Za-z_]\w*)|\s*\[(\d+)\])?", e):   # SK[id].name, LBL[i][1]: the table's literals
                        lits += table_literals(texts, base, fld or None, int(col) if col else None)
                    if not lits:
                        unresolved.append("%s:%d %s(arg %d = %s)" % (os.path.basename(f), ln, name, ix, e[:50]))
                        continue
                for s in lits:
                    if not needs_check(s):
                        continue
                    checked += 1
                    if Loc._norm(s) in loc.keys:
                        continue
                    if s in FORMAT_ARGS:
                        bad = any(loc.core(render(s, args=a)) for a in FORMAT_ARGS[s])
                    else:
                        bad = all(loc.core(render(s, w)) for w in SAMPLES)
                    if bad:
                        missing.setdefault(s, []).append("%s:%d %s" % (os.path.basename(f), ln, name))
    # daemon -> client notes (op 0x11 text, shown by the ext through the same loc tables): every literal sentence needs an entry too
    npat = re.compile(r"msg\(0x11,\s*b\"((?:[^\"\\]|\\.)*)\"|\bpush_menu_note\(\"((?:[^\"\\]|\\.)*)\"")
    for f in ("daemon.py", "hostmig.py"):
        fp = os.path.join(TOOLS, f)
        if not os.path.exists(fp):
            continue
        for m in npat.finditer(open(fp, encoding="utf-8").read()):
            s = unesc(m.group(1) or m.group(2))
            if needs_check(s) and " " in s:
                checked += 1
                if Loc._norm(s) not in loc.keys and loc.core(render(s)):
                    missing.setdefault(s, []).append(f + " note")
    return checked, len(files), unresolved, missing


def main():
    checked, nf, unresolved, missing = scan()
    print("checked %d literals in %d files; unresolved variable args: %d" % (checked, nf, len(unresolved)))
    if "-v" in sys.argv:
        for u in unresolved:
            print("  unresolved " + u)
    for s, w in sorted(missing.items()):
        print("MISSING pl: %r   (%s)" % (s, ", ".join(w[:3])))
    bad = 0                                                  # locdata drops empty translations silently: flag them
    for fpath in sorted(glob.glob(os.path.join(TOOLS, "loc", "pl", "*.txt"))):
        for i, line in enumerate(open(fpath, encoding="utf-8").read().split("\n"), 1):
            line = line.rstrip("\r")
            if " => " in line and not line.startswith("#") and not line.split(" => ", 1)[1].strip():
                print("EMPTY translation %s:%d" % (os.path.basename(fpath), i))
                bad += 1
    print("FAILED: %d missing, %d empty" % (len(missing), bad) if missing or bad else "ALL OK")
    return 1 if missing or bad else 0


if __name__ == "__main__":
    sys.exit(main())
