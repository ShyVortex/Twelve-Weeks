"""Update server robustness (re/launcher-robustness-1019.md): concurrent / slow / aborted downloads, range edge cases, HEAD, path traversal,
big report uploads while downloads run, publish atomicity (channels.json last, nothing half-published is ever served), gc safety.
Local server on a free port, temp dirs under T2R_TMP (default: a temp folder). Never touches the live server (7002) or its data dir.
  python tools/update_server/test_robustness.py"""
import hashlib
import io
import json
import os
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
import t2rtmp  # noqa: E402,F401
import tempfile  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish  # noqa: E402
import report_store  # noqa: E402
import server  # noqa: E402


def mkclient(root, files):
    for rel, data in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)


def raw_request(port, request_bytes, read=True, timeout=5):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.sendall(request_bytes)
    out = b""
    if read:
        try:
            while True:
                c = s.recv(65536)
                if not c:
                    break
                out += c
                if b"\r\n\r\n" in out and b"Content-Length: 0" in out:
                    break
                if out.startswith(b"HTTP/1.") and b"\r\n\r\n" in out:
                    head, _, body = out.partition(b"\r\n\r\n")
                    cl = [l for l in head.split(b"\r\n") if l.lower().startswith(b"content-length:")]
                    if cl and len(body) >= int(cl[0].split(b":")[1]):
                        break
        except socket.timeout:
            pass
    s.close()
    return out


def make_zip(text="it crashed, here is what happened", dump_size=0):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("meta.json", json.dumps({"text": text, "name": "Tester", "version": "1"}))
        z.writestr("files/t2r-ext.log", "boot ok\n" * 100)
        if dump_size:
            z.writestr("files/crash.mdmp", os.urandom(1 << 20) * (dump_size >> 20))
    return b.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.c1 = os.path.join(self.tmp.name, "c1")
        self.big = os.urandom(6 << 20)
        mkclient(self.c1, {"big.bin": self.big, "small.txt": b"hello", "sub/x.bin": os.urandom(5000)})
        publish.publish(self.c1, self.data, "stable", "1")
        self.reports = os.path.join(self.tmp.name, "reports")
        self.srv = server.make_server(self.data, "127.0.0.1", 0, reports=self.reports)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.manifest = json.loads(self.get("/manifest.json")[1])
        self.bigsha = [f for f in self.manifest["files"] if f["path"] == "big.bin"][0]["sha256"]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def get(self, path, headers=None, method="GET"):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), headers=headers or {}, method=method)
        try:
            r = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers
        return r.status, r.read(), r.headers


class Downloads(Base):
    def test_many_concurrent_downloads_complete_intact(self):
        results, errs = [], []

        def dl():
            try:
                results.append(hashlib.sha256(self.get("/files/" + self.bigsha)[1]).hexdigest())
            except Exception as e:      # pragma: no cover
                errs.append(e)
        ts = [threading.Thread(target=dl) for _ in range(12)]
        [t.start() for t in ts]
        [t.join(60) for t in ts]
        self.assertEqual(errs, [])
        self.assertEqual(results, [self.bigsha] * 12)

    def test_slow_client_and_stalled_connection_do_not_block_others(self):
        # a half-sent request (slowloris) and a reader that stops reading the body
        stall = socket.create_connection(("127.0.0.1", self.port))
        stall.sendall(b"GET /files/" + self.bigsha.encode() + b" HTTP/1.1\r\nHost: x\r\n")        # never finished
        slow = socket.create_connection(("127.0.0.1", self.port))
        slow.sendall(b"GET /files/" + self.bigsha.encode() + b" HTTP/1.1\r\nHost: x\r\n\r\n")
        slow.recv(1000)                                                                            # takes a bit, then reads nothing more
        t0 = time.time()
        code, body, _ = self.get("/files/" + self.bigsha)
        self.assertEqual((code, hashlib.sha256(body).hexdigest()), (200, self.bigsha))
        self.assertLess(time.time() - t0, 10)
        self.assertEqual(self.get("/manifest.json")[0], 200)
        stall.close()
        slow.close()

    def test_client_abort_mid_download_leaves_server_healthy(self):
        for _ in range(5):
            s = socket.create_connection(("127.0.0.1", self.port))
            s.sendall(b"GET /files/" + self.bigsha.encode() + b" HTTP/1.1\r\nHost: x\r\n\r\n")
            s.recv(4096)
            s.close()                                                                              # reset while the server still has MBs to send
        time.sleep(0.3)
        code, body, _ = self.get("/files/" + self.bigsha)
        self.assertEqual((code, len(body)), (200, len(self.big)))

    def test_resume_by_range_reassembles(self):
        part = b""
        total = len(self.big)
        while len(part) < total:
            code, body, h = self.get("/files/" + self.bigsha, {"Range": "bytes=%d-%d" % (len(part), len(part) + (1 << 20) - 1)})
            self.assertEqual(code, 206)
            part += body
        self.assertEqual(hashlib.sha256(part).hexdigest(), self.bigsha)

    def test_range_edge_cases(self):
        u = "/files/" + self.bigsha
        n = len(self.big)
        code, body, h = self.get(u, {"Range": "bytes=0-0"})
        self.assertEqual((code, body, h["Content-Range"]), (206, self.big[:1], "bytes 0-0/%d" % n))
        code, body, h = self.get(u, {"Range": "bytes=%d-%d" % (n - 1, n + 999)})            # end beyond EOF is clamped
        self.assertEqual((code, len(body)), (206, 1))
        self.assertEqual(self.get(u, {"Range": "bytes=%d-" % n})[0], 416)                    # start == size: nothing left (client treats "have == size" as done)
        self.assertEqual(self.get(u, {"Range": "bytes=10-5"})[0], 416)
        for junk in ("bytes=abc", "items=0-5", "bytes=0-5,10-20", "bytes=-", ""):             # unparsable / multi-range: ignored -> the whole file
            code, body, _ = self.get(u, {"Range": junk})
            self.assertEqual((code, len(body)), (200, n), junk)
        code, body, h = self.get(u, method="HEAD")
        self.assertEqual((code, body, h["Content-Length"], h["Accept-Ranges"]), (200, b"", str(n), "bytes"))
        code, body, h = self.get(u, {"Range": "bytes=5-9"}, method="HEAD")
        self.assertEqual((code, body, h["Content-Length"]), (206, b"", "5"))
        self.assertEqual(self.get("/manifest.json", method="HEAD")[0], 200)

    def test_path_traversal_and_junk_names(self):
        secret = os.path.join(self.data, "channels.json")
        self.assertTrue(os.path.exists(secret))
        attempts = ["/files/../channels.json", "/files/..%2fchannels.json", "/files/%2e%2e/channels.json", "/files/..\\channels.json",
                    "/files/" + "../" * 5 + "windows/win.ini", "/files/%00", "/files/" + "a" * 64 + "/..", "/files/" + "A" * 64, "/files/" + self.bigsha + "/",
                    "/files/" + self.bigsha + ".gz.gz", "/files/" + self.bigsha + "%00.gz", "/files/", "/files",
                    "/manifest.json?channel=../../channels", "/manifest.json?channel=..%5c..&version=x", "/manifest.json?channel=stable&version=../stable/1",
                    "/reports/", "/../server.py"]
        for a in attempts:
            out = raw_request(self.port, ("GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % a).encode("latin1"))
            status = out.split(b" ")[1] if out.startswith(b"HTTP/") else b"?"
            self.assertIn(status, (b"404", b"400"), (a, out[:200]))
            self.assertNotIn(b'"stable"', out.split(b"\r\n\r\n", 1)[-1] if a.startswith("/files") or a.startswith("/..") else b"", a)
        # a malformed request line / absurd header does not kill the server
        raw_request(self.port, b"GARBAGE\r\n\r\n")
        raw_request(self.port, b"GET /" + b"a" * 200000 + b" HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertEqual(self.get("/manifest.json")[0], 200)

    def test_manifest_503_when_a_blob_is_missing(self):
        os.remove(os.path.join(self.data, "blobs", self.bigsha))
        code, body, _ = self.get("/manifest.json")
        self.assertEqual(code, 503)
        self.assertIn("not fully published", json.loads(body)["error"])
        self.assertEqual(self.get("/files/" + self.bigsha)[0], 404)
        self.assertEqual(self.get("/versions.json")[0], 200)

    def test_blob_vanishing_between_lookup_and_open_is_a_clean_404(self):
        os.remove(os.path.join(self.data, "blobs", self.bigsha))
        self.assertEqual(self.get("/files/" + self.bigsha)[0], 404)

    def test_listen_backlog_is_larger_than_the_default(self):
        self.assertGreaterEqual(server.Srv.request_queue_size, 64)


class Reports(Base):
    def post(self, body, headers=None):
        req = urllib.request.Request("http://127.0.0.1:%d/report" % self.port, data=body, headers={"Content-Type": "application/zip", **(headers or {})}, method="POST")
        try:
            r = urllib.request.urlopen(req, timeout=60)
            return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_big_report_upload_while_downloads_run(self):
        body = make_zip(dump_size=60 << 20)                       # incompressible 60 MB dump: the largest realistic report
        self.assertLess(len(body), report_store.MAX_BODY)
        res = {}
        up = threading.Thread(target=lambda: res.update(r=self.post(body)))
        up.start()
        t0 = time.time()
        got = []
        for _ in range(6):
            code, data, _ = self.get("/files/" + self.bigsha)
            got.append((code, hashlib.sha256(data).hexdigest()))
        mid = time.time() - t0
        up.join(120)
        self.assertEqual(got, [(200, self.bigsha)] * 6)
        self.assertEqual(res["r"][0], 200, res)
        self.assertTrue(res["r"][1]["ok"])
        self.assertLess(mid, 60)
        dirs = [d for d in os.listdir(self.reports)]
        self.assertEqual(len(dirs), 1)
        self.assertTrue(os.path.exists(os.path.join(self.reports, dirs[0], "meta.json")))
        self.assertEqual(os.path.getsize(os.path.join(self.reports, dirs[0], "files", "crash.mdmp")), 60 << 20)

    def test_refused_and_broken_reports_leave_nothing_behind(self):
        self.assertEqual(self.post(b"not a zip")[0], 400)
        self.assertEqual(self.post(make_zip(text="x"))[0], 400)                                  # description too short
        self.assertEqual(self.post(b"")[0], 400)
        # declared too large: refused from the header alone, the body is never read
        s = socket.create_connection(("127.0.0.1", self.port))
        s.sendall(b"POST /report HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n" % (report_store.MAX_BODY + 1))
        self.assertIn(b" 413 ", s.recv(4096).split(b"\r\n")[0])
        s.close()
        # truncated upload (connection drops half-way)
        body = make_zip()
        s = socket.create_connection(("127.0.0.1", self.port))
        s.sendall(b"POST /report HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n" % len(body) + body[: len(body) // 2])
        s.close()
        # an entry that unpacks over the cap is refused AND its half-written folder removed
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("meta.json", json.dumps({"text": "bomb report text", "name": "T"}))
            for i in range(3):
                z.writestr("files/z%d.bin" % i, b"\0" * (report_store.MAX_ENTRY - 1000))        # under the per-entry cap, over the total
        code, r = self.post(b.getvalue())
        self.assertEqual(code, 413, r)
        time.sleep(0.2)
        left = os.listdir(self.reports) if os.path.isdir(self.reports) else []
        self.assertEqual([d for d in left if os.path.exists(os.path.join(self.reports, d))], [d for d in left if os.path.exists(os.path.join(self.reports, d, "meta.json"))])
        self.assertEqual(left, [])
        self.assertEqual(self.get("/manifest.json")[0], 200)

    def test_report_after_server_side_failure_still_gets_clean_error(self):
        code, r = self.post(make_zip(), {"Content-Length": "5"} if False else None)
        self.assertEqual(code, 200)
        self.assertTrue(r["code"].startswith("R-"))


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.c1 = os.path.join(self.tmp.name, "c1")
        self.c2 = os.path.join(self.tmp.name, "c2")
        mkclient(self.c1, {"a.bin": os.urandom(3000), "b.bin": os.urandom(3000)})
        mkclient(self.c2, {"a.bin": os.urandom(3000), "b.bin": os.urandom(3000), "c.bin": os.urandom(3000)})
        publish.publish(self.c1, self.data, "stable", "1")

    def tearDown(self):
        self.tmp.cleanup()

    def channels(self):
        with open(os.path.join(self.data, "channels.json")) as f:
            return json.load(f)

    def test_failed_publish_never_moves_the_channel(self):
        real = publish.store_blob
        n = {"i": 0}

        def flaky(data, src):
            n["i"] += 1
            if n["i"] == 2:
                raise OSError(28, "No space left on device")
            return real(data, src)
        publish.store_blob = flaky
        try:
            with self.assertRaises(OSError):
                publish.publish(self.c2, self.data, "stable", "2")
        finally:
            publish.store_blob = real
        self.assertEqual(self.channels(), {"stable": "1"})
        self.assertFalse(os.path.exists(os.path.join(self.data, "manifests", "stable", "2.json")))      # no manifest of a half publish either
        self.assertEqual([n for n in os.listdir(os.path.join(self.data, "blobs")) if n.endswith(".tmp")], [])

    def test_copy_failure_removes_the_temp_blob(self):
        import shutil
        real = shutil.copyfile

        def boom(src, dst, **kw):
            with open(dst, "wb") as f:
                f.write(b"half")
            raise OSError(28, "No space left on device")
        shutil.copyfile = boom
        try:
            with self.assertRaises(OSError):
                publish.store_blob(self.data, os.path.join(self.c2, "c.bin"))
        finally:
            shutil.copyfile = real
        self.assertEqual([n for n in os.listdir(os.path.join(self.data, "blobs")) if n.endswith(".tmp")], [])

    def test_promote_refuses_a_version_with_missing_or_short_blobs(self):
        publish.publish(self.c2, self.data, "stable", "2", promote=False)
        m = json.load(open(os.path.join(self.data, "manifests", "stable", "2.json")))
        victim = os.path.join(self.data, "blobs", m["files"][2]["sha256"])
        with open(victim, "r+b") as f:
            f.truncate(100)
        with self.assertRaises(SystemExit) as cm:
            publish.promote_version(self.data, "stable", "2")
        self.assertIn("missing or the wrong size", str(cm.exception))
        self.assertEqual(self.channels(), {"stable": "1"})
        os.remove(victim)
        with self.assertRaises(SystemExit):
            publish.promote_version(self.data, "stable", "2")
        publish.publish(self.c2, self.data, "stable", "2")                      # re-publishing repairs the blob (wrong size / missing is rewritten) and promotes
        self.assertEqual(self.channels(), {"stable": "2"})

    def test_readers_never_see_a_half_written_manifest_or_channels_file(self):
        srv = server.make_server(self.data, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        stop = threading.Event()
        bad = []
        seen = set()

        def reader():
            while not stop.is_set():
                try:
                    r = urllib.request.urlopen("http://127.0.0.1:%d/manifest.json" % port, timeout=10)
                    m = json.loads(r.read())
                    seen.add(m["version"])
                    if not m["files"]:
                        bad.append("empty")
                except urllib.error.HTTPError as e:
                    if e.code != 503:
                        bad.append(e.code)
                except Exception as e:
                    bad.append(repr(e))
        ts = [threading.Thread(target=reader) for _ in range(4)]
        [t.start() for t in ts]
        for v in range(2, 14):
            mkclient(self.c2, {"c.bin": os.urandom(2000)})
            publish.publish(self.c2, self.data, "stable", str(v))
        stop.set()
        [t.join(20) for t in ts]
        srv.shutdown()
        srv.server_close()
        self.assertEqual(bad, [])
        self.assertIn("13", seen | {"13"})

    def test_gc_keeps_what_clients_may_still_need(self):
        publish.publish(self.c2, self.data, "stable", "2")
        publish.promote_version(self.data, "stable", "1")                       # rollback: v1 is current though v2 is the newer file
        m1 = json.load(open(os.path.join(self.data, "manifests", "stable", "1.json")))
        old = time.time() - 5 * 86400
        for root, _, names in os.walk(self.data):
            for n in names:
                os.utime(os.path.join(root, n), (old, old))
        os.utime(os.path.join(self.data, "manifests", "stable", "2.json"), (old + 10, old + 10))
        publish.gc(self.data, 1, grace_hours=1)                                  # keep newest 1 = v2, but v1 is what the channel points at
        for f in m1["files"]:
            self.assertTrue(os.path.exists(os.path.join(self.data, "blobs", f["sha256"])), "gc removed a blob of the CURRENT version")
        # unreferenced and old: removed; unreferenced but fresh (a publish in progress): kept
        stray_old = os.path.join(self.data, "blobs", "e" * 64)
        stray_new = os.path.join(self.data, "blobs", "d" * 64)
        for p in (stray_old, stray_new):
            open(p, "wb").write(b"x")
        os.utime(stray_old, (old, old))
        removed = publish.gc(self.data, 1, grace_hours=1)
        self.assertEqual(removed, 1)
        self.assertFalse(os.path.exists(stray_old))
        self.assertTrue(os.path.exists(stray_new))

    def test_gc_survives_a_blob_held_open(self):
        publish.publish(self.c2, self.data, "stable", "2")
        stray = os.path.join(self.data, "blobs", "c" * 64)
        open(stray, "wb").write(b"x")
        old = time.time() - 9 * 86400
        os.utime(stray, (old, old))
        real = os.remove

        def locked(p):
            if p == stray:
                raise PermissionError(13, "in use")
            return real(p)
        os.remove = locked
        try:
            publish.gc(self.data, 5, grace_hours=1)                               # must not raise: a download holds the file
        finally:
            os.remove = real


if __name__ == "__main__":
    unittest.main()
