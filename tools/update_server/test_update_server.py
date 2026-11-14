import json
import os
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish
import server


def mkclient(root, files):
    for rel, data in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.c1 = os.path.join(self.tmp.name, "c1")
        self.c2 = os.path.join(self.tmp.name, "c2")
        mkclient(self.c1, {"a.bin": b"A" * 1000, "sub/b.txt": b"hello", "t2r-play.log": b"skip"})
        mkclient(self.c2, {"a.bin": b"A" * 1000, "sub/b.txt": b"hello2"})
        publish.publish(self.c1, self.data, "stable", "1")
        self.srv = server.make_server(self.data, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def get(self, path, headers=None):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), headers=headers or {})
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers
        return r.status, r.read(), r.headers

    def test_manifest(self):
        code, body, _ = self.get("/manifest.json?channel=stable")
        m = json.loads(body)
        self.assertEqual((code, m["version"], m["channel"]), (200, "1", "stable"))
        self.assertEqual(sorted(f["path"] for f in m["files"]), ["a.bin", "sub/b.txt"])   # log skipped
        f = m["files"][0]
        self.assertTrue(f["url"].endswith("/files/" + f["sha256"]))
        self.assertIsNone(m["launcher"])
        self.assertEqual(self.get("/manifest.json?channel=nope")[0], 404)

    def test_range(self):
        m = json.loads(self.get("/manifest.json")[1])
        a = [f for f in m["files"] if f["path"] == "a.bin"][0]
        u = "/files/" + a["sha256"]
        code, body, h = self.get(u)
        self.assertEqual((code, len(body), h["Accept-Ranges"]), (200, 1000, "bytes"))
        code, body, h = self.get(u, {"Range": "bytes=100-199"})
        self.assertEqual((code, len(body), h["Content-Range"]), (206, 100, "bytes 100-199/1000"))
        code, body, h = self.get(u, {"Range": "bytes=990-"})
        self.assertEqual((code, len(body)), (206, 10))
        code, body, h = self.get(u, {"Range": "bytes=-5"})
        self.assertEqual((code, len(body)), (206, 5))
        code, _, h = self.get(u, {"Range": "bytes=5000-"})
        self.assertEqual((code, h["Content-Range"]), (416, "bytes */1000"))
        self.assertEqual(self.get("/files/" + "0" * 64)[0], 404)
        self.assertEqual(self.get("/files/../channels.json")[0], 404)

    def test_dedupe_and_rollback(self):
        r = publish.publish(self.c2, self.data, "stable", "2")
        self.assertEqual((r["new_blobs"], r["reused_blobs"]), (1, 1))        # a.bin shared, b.txt new
        self.assertEqual(len([n for n in os.listdir(os.path.join(self.data, "blobs")) if len(n) == 64]), 3)   # raw blobs only
        self.assertEqual(json.loads(self.get("/manifest.json")[1])["version"], "2")
        self.assertEqual(json.loads(self.get("/manifest.json?version=1")[1])["version"], "1")
        publish.promote_version(self.data, "stable", "1")
        self.assertEqual(json.loads(self.get("/manifest.json")[1])["version"], "1")
        self.assertEqual(json.loads(self.get("/versions.json")[1])["current"], "1")

    def test_compressed_blobs(self):
        import gzip
        noise = os.urandom(5000)
        mkclient(self.c2, {"big.txt": b"hello world " * 20000, "noise.bin": noise})
        publish.publish(self.c2, self.data, "stable", "2", codec="gzip")
        m = json.loads(self.get("/manifest.json")[1])
        by = {f["path"]: f for f in m["files"]}
        z = by["big.txt"]
        self.assertEqual(z["enc"], "gzip")
        self.assertTrue(z["zurl"].endswith("/files/%s.gz" % z["sha256"]))
        self.assertTrue(z["url"].endswith("/files/" + z["sha256"]))            # raw fields unchanged
        self.assertLess(z["zsize"], z["size"] * 0.05)
        for k in ("zsize", "zurl", "enc"):                                        # incompressible: no compressed twin
            self.assertNotIn(k, by["noise.bin"])
        self.assertTrue(os.path.exists(os.path.join(self.data, "blobs", by["noise.bin"]["sha256"] + ".nz")))
        code, body, h = self.get("/files/%s.gz" % z["sha256"])
        self.assertEqual((code, len(body), h["Content-Type"], h["Content-Length"]), (200, z["zsize"], "application/octet-stream", str(z["zsize"])))
        self.assertIsNone(h["Content-Encoding"])
        self.assertEqual(gzip.decompress(body), b"hello world " * 20000)
        code, part, h = self.get("/files/%s.gz" % z["sha256"], {"Range": "bytes=10-49"})
        self.assertEqual((code, part, h["Content-Range"]), (206, body[10:50], "bytes 10-49/%d" % z["zsize"]))
        self.assertEqual(self.get("/files/%s.gz" % z["sha256"], {"Range": "bytes=%d-" % (z["zsize"] + 5)})[0], 416)
        # name validation
        for bad in ("%s.zip" % z["sha256"], "%s.gz.x" % z["sha256"], "../%s.gz" % z["sha256"], "%s.nz" % by["noise.bin"]["sha256"], "abc.gz"):
            self.assertEqual(self.get("/files/" + bad)[0], 404, bad)
        # a manifest entry whose compressed blob vanished loses its z* fields instead of pointing at a 404
        os.remove(os.path.join(self.data, "blobs", z["sha256"] + ".gz"))
        f2 = {f["path"]: f for f in json.loads(self.get("/manifest.json")[1])["files"]}["big.txt"]
        self.assertNotIn("zurl", f2)
        self.assertNotIn("zsize", f2)

    def test_recompress_old_version(self):
        c3 = os.path.join(self.tmp.name, "c3")
        mkclient(c3, {"x.bin": b"abc" * 100000})
        publish.publish(c3, self.data, "stable", "3", compress=False)
        self.assertNotIn("zsize", json.loads(self.get("/manifest.json?version=3")[1])["files"][0])
        publish.recompress(self.data, "gzip")
        f = json.loads(self.get("/manifest.json?version=3")[1])["files"][0]
        self.assertIn("zurl", f)
        self.assertEqual(f["enc"], "gzip")
        v1 = {x["path"]: x for x in json.loads(self.get("/manifest.json?version=1")[1])["files"]}
        self.assertIn("zsize", v1["a.bin"])                                       # the old published version got it too
        self.assertNotIn("zsize", v1["sub/b.txt"])                                # 5 bytes: not worth it
        self.assertEqual(publish.gc(self.data, 5), 0)                              # gc keeps compressed twins of used blobs

    def test_launcher_news_status(self):
        inst = os.path.join(self.tmp.name, "setup.exe")
        with open(inst, "wb") as f:
            f.write(b"EXE")
        publish.set_launcher(self.data, inst, "1.2.0")
        m = json.loads(self.get("/manifest.json")[1])
        self.assertEqual(m["launcher"]["version"], "1.2.0")
        self.assertEqual(self.get("/files/" + m["launcher"]["sha256"])[1], b"EXE")
        self.assertEqual(json.loads(self.get("/news.json")[1]), [])
        self.assertFalse(json.loads(self.get("/status.json")[1])["online"])

    def test_status_file(self):
        sf = os.path.join(self.tmp.name, "st.json")
        with open(sf, "w") as f:
            json.dump({"ts": time.time(), "server_version": "74", "matches": 2, "players_online": 5, "queue": 1,
                       "roster": [{"name": "Ann", "state": "match", "map": "Hillside", "party": False}], "live": {"players": [{"steamid": 7}]}}, f)
        srv = server.make_server(self.data, "127.0.0.1", 0, status_file=sf)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        s = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/status.json" % srv.server_address[1]).read())
        srv.shutdown()
        srv.server_close()
        self.assertEqual((s["online"], s["server_version"], s["matches"]), (True, "74", 2))
        self.assertEqual(s["roster"], [{"name": "Ann", "state": "match", "map": "Hillside", "party": False}])
        self.assertNotIn("steamid", json.dumps(s))      # the raw live snapshot (ids) never leaves the server


if __name__ == "__main__":
    unittest.main()
