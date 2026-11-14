"""News media route of the update server: GET /media/<name> serves <data>/media/<name> with its type, a cache header and Range; bad names / missing files are 404.
Run: python tools/update_server/test_media.py"""
import os, sys, tempfile, threading, http.client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "media"))
open(os.path.join(d, "media", "melee_duel_1.gif"), "wb").write(b"GIF89a" + b"x" * 1000)
srv = server.make_server(d, "127.0.0.1", 0)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]

def get(path, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", path, headers=headers or {})
    r = c.getresponse(); b = r.read(); c.close()
    return r.status, dict(r.getheaders()), b

st, h, b = get("/media/melee_duel_1.gif")
check(st == 200 and len(b) == 1006, "gif served (%d, %d bytes)" % (st, len(b)))
check(h.get("Content-Type") == "image/gif", "content type image/gif")
check("max-age" in h.get("Cache-Control", ""), "cache header %r" % h.get("Cache-Control"))
st, h, b = get("/media/melee_duel_1.gif", {"Range": "bytes=0-9"})
check(st == 206 and len(b) == 10, "range request (%d)" % st)
check(get("/media/nope.gif")[0] == 404, "missing file 404")
check(get("/media/..%2fnews.json")[0] == 404, "path trick 404")
check(get("/media/a.exe")[0] == 404, "unknown type 404")
st, h, b = get("/files/" + "0" * 64)
check(st == 404 and "max-age" not in h.get("Cache-Control", ""), "other routes untouched")
srv.shutdown()
print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
