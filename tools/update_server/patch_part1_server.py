"""Adds the Part I map pack routes to an EXISTING server.py in place (the Pi's copy may differ from the repo: patch it, never replace it).

  python patch_part1_server.py <path to server.py>      (part1_maps.py must sit next to it; running it twice is harmless)

Safety: the original is copied to server.py.bak-part1 first, the patched text must parse (ast) before it is written, and it is written through a temp file +
rename. The import, the two routes and the _file() signature are required (the script stops, changing nothing, when one of them does not fit the
file); the docstring line is cosmetic and skipped when its anchor is not there. Restart the update server only after "patched ... ok".
"""
import ast
import os
import shutil
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
p = sys.argv[1]
if not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(p)), "part1_maps.py")):
    sys.exit("part1_maps.py must sit next to " + p)
raw = open(p, "rb").read()
s = raw.decode("utf-8")
crlf = "\r\n" in s
if "import part1_maps" in s:
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


rep("import report_store\n", "import report_store\nimport part1_maps\n")
rep('''            if p.startswith("/files/"):
                return self._file(p[7:], head)
''', '''            if p.startswith("/files/"):
                return self._file(p[7:], head)
            if p == "/part1-maps.json":           # playtester pack, separate from the release manifest (part1_maps.py)
                pm = part1_maps.public(store.data, self._base())
                if not pm:
                    return self._json({"error": "no Part I map pack published"}, 404, head)
                return self._json(pm, 200, head)
            if p.startswith("/part1-files/"):
                return self._file(p[13:], head, part1_maps.blob_path(store.data, p[13:]))
''')
rep('''        def _file(self, sha, head):
            path = store.blob_path(sha)
''', '''        def _file(self, sha, head, path=None):
            path = path or store.blob_path(sha)
''')
rep('''  GET /news.json  ''', '''  GET /part1-maps.json, /part1-files/<sha256>      Part I map pack for playtesters (part1_maps.py, publish_part1.py); never in /manifest.json
  GET /news.json  ''', required=False)
try:
    ast.parse(s)
except SyntaxError as e:
    sys.exit("the patched text does not parse (%s); nothing written" % e)
shutil.copyfile(p, p + ".bak-part1")
tmp = p + ".new"
open(tmp, "wb").write(s.encode("utf-8"))
os.replace(tmp, p)
print("patched", p, "ok (backup: %s.bak-part1)" % p)
