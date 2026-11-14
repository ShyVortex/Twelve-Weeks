"""Adds GET /ban-check to an EXISTING server.py in place (the Pi's copy differs from the repo: patch it, never replace it).

  python patch_banlauncher_server.py <path to server.py>      (ban_check.py must sit next to it; running it twice is harmless)

Safety: the original is copied to server.py.bak-ban first, the patched text must parse (ast), every anchor must match exactly once
(otherwise nothing is changed), the file is written through a temp file + rename. Restart the update server only after "patched ... ok".
"""
import ast
import os
import shutil
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
p = sys.argv[1]
if not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(p)), "ban_check.py")):
    sys.exit("ban_check.py must sit next to " + p)
raw = open(p, "rb").read()
s = raw.decode("utf-8")
crlf = "\r\n" in s
if "import ban_check" in s:
    print("already patched", p)
    sys.exit(0)


def rep(a, b, required=True):
    global s
    if crlf:
        a = a.replace("\n", "\r\n")
        b = b.replace("\n", "\r\n")
    if s.count(a) != 1:
        if required:
            sys.exit("anchor not found exactly once (nothing changed): " + a.strip().splitlines()[0])
        return
    s = s.replace(a, b)


rep("import report_store\n", "import report_store\nimport ban_check\n")
rep('''            if p == "/news.json":
''', '''            if p == "/ban-check":                 # launcher ban screen (ban_check.py): read-only, answers {"banned": bool, "reason": str}
                try:
                    r = ban_check.route(db_path, q)
                except Exception as e:           # never a 500 that could read as a verdict: banned:false, the error goes to the log
                    sys.stderr.write("ban-check failed: %r\\n" % (e,))
                    r = {"banned": False, "reason": ""}
                if r["banned"]:
                    sys.stderr.write("ban-check: BANNED %s\\n" % self.path[:200])
                return self._json(r, 200, head)
            if p == "/news.json":
''')
rep('''  GET /news.json  ''', '''  GET /ban-check?h=<hw hashes>&s=<steam ids>        launcher ban screen (ban_check.py), read-only
  GET /news.json  ''', required=False)
try:
    ast.parse(s)
except SyntaxError as e:
    sys.exit("the patched text does not parse (%s); nothing written" % e)
shutil.copyfile(p, p + ".bak-ban")
tmp = p + ".new"
open(tmp, "wb").write(s.encode("utf-8"))
os.replace(tmp, p)
print("patched", p, "ok (backup: %s.bak-ban)" % p)
