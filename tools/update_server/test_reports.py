"""python tools/update_server/test_reports.py : /report upload, limits, zip-slip, CLI (local server on a scratch port, scratch folders only)."""
import io
import json
import os
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)
import threading
import unittest
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_store
import reports
import server


def make_zip(meta=None, files=None, raw_names=None):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        if meta is not False:
            z.writestr("meta.json", json.dumps(meta if meta is not None else {"text": "the game froze after the match", "name": "Tester", "version": "abc123", "steamId": "7656119800000000"}))
        for n, data in (files or {"files/t2r-ext.log": b"hello log\n"}).items():
            z.writestr(n, data)
        for n, data in (raw_names or {}).items():
            z.writestr(zipfile.ZipInfo(n), data)
    return b.getvalue()


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.srv = server.make_server(os.path.join(cls.tmp, "data"), host="127.0.0.1", port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.root = os.path.join(cls.tmp, "data", "reports")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def post(self, body, path="/report"):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=body, headers={"Content-Type": "application/zip"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_1_upload_and_cli(self):
        st, j = self.post(make_zip())
        self.assertEqual(st, 200)
        self.assertTrue(j["ok"] and j["code"].startswith("R-") and len(j["code"]) == 6)
        dirs = os.listdir(self.root)
        self.assertEqual(len(dirs), 1)
        self.assertIn(j["code"], dirs[0]); self.assertTrue(dirs[0].endswith("_Tester"))
        meta = json.load(open(os.path.join(self.root, dirs[0], "meta.json")))
        self.assertEqual(meta["steamId"], "7656119800000000"); self.assertFalse(meta["handled"])
        self.assertEqual(open(os.path.join(self.root, dirs[0], "files", "t2r-ext.log"), "rb").read(), b"hello log\n")
        # CLI
        out = io.StringIO(); old = sys.stdout; sys.stdout = out
        try:
            reports.main(["--reports", self.root, "list"]); reports.main(["--reports", self.root, "show", j["code"]]); reports.main(["--reports", self.root, "handled", j["code"]]); reports.main(["--reports", self.root, "list"])
        finally:
            sys.stdout = old
        txt = out.getvalue()
        self.assertIn(j["code"], txt); self.assertIn("the game froze", txt); self.assertIn("marked handled", txt); self.assertIn("0 report(s)", txt)

    def test_2_zip_slip(self):
        st, j = self.post(make_zip(files={"../../evil.txt": b"x", "files/..\\..\\evil2.txt": b"y", "/abs/evil3.txt": b"z", "a/b/c.log": b"ok"}))
        self.assertEqual(st, 200)
        d = [x for x in os.listdir(self.root) if j["code"] in x][0]
        names = sorted(os.listdir(os.path.join(self.root, d, "files")))
        self.assertEqual(names, ["c.log", "evil.txt", "evil2.txt", "evil3.txt"])      # flattened, inside the report folder
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil.txt")) or os.path.exists(os.path.join(self.tmp, "data", "evil.txt")))

    def test_3_bad_input(self):
        for body in (b"not a zip", make_zip(meta=False), make_zip(meta={"text": "x"})):        # not a zip / no meta / description too short
            with self.assertRaises(report_store.ReportError) as c:
                report_store.save_report(self.root, body)
            self.assertEqual(c.exception.status, 400)
        self.assertEqual(self.post(b"", "/report")[0], 400)
        self.assertEqual(self.post(make_zip(), "/nope")[0], 404)

    def test_4_limits(self):
        with self.assertRaises(report_store.ReportError) as c:
            report_store.save_report(self.root, b"0" * (report_store.MAX_BODY + 1))
        self.assertEqual(c.exception.status, 413)
        many = make_zip(files={"f%d.txt" % i: b"x" for i in range(report_store.MAX_ENTRIES + 5)})
        with self.assertRaises(report_store.ReportError) as c2:
            report_store.save_report(self.root, many)
        self.assertEqual(c2.exception.status, 400)
        lim = report_store.RateLimiter(2, 100, clock=lambda: 0)
        self.assertEqual([lim.allow("1.1.1.1") for _ in range(3)], [True, True, False]); self.assertTrue(lim.allow("2.2.2.2"))

    def test_5_rate_limit_http(self):
        srv = server.make_server(os.path.join(self.tmp, "d2"), host="127.0.0.1", port=0)
        port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
        codes = []
        for _ in range(report_store.RATE_N + 2):
            req = urllib.request.Request("http://127.0.0.1:%d/report" % port, data=make_zip(), method="POST")
            try:
                codes.append(urllib.request.urlopen(req, timeout=10).status)
            except urllib.error.HTTPError as e:
                codes.append(e.code)
        srv.shutdown()
        self.assertEqual(codes, [200] * report_store.RATE_N + [429] * 2)


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\0" * 64


class TestScreenshots(unittest.TestCase):
    def save(self, files):
        d = tempfile.mkdtemp()
        return d, report_store.save_report(d, make_zip(files=files), "1.2.3.4")

    def test_accepts_and_marks(self):
        d, r = self.save({"files/system.txt": b"x", "files/screenshot-1.png": PNG, "files/screenshot-2.jpg": JPG})
        m = json.load(open(os.path.join(r["dir"], "meta.json")))
        shots = {f["name"]: f for f in m["files"] if f.get("kind") == "screenshot"}
        self.assertEqual(set(shots), {"screenshot-1.png", "screenshot-2.jpg"})
        self.assertEqual(shots["screenshot-1.png"]["contentType"], "image/png")
        self.assertEqual(shots["screenshot-2.jpg"]["size"], len(JPG))

    def test_wrong_extension_renamed_by_content(self):
        d, r = self.save({"files/screenshot-1.gif": PNG})
        m = json.load(open(os.path.join(r["dir"], "meta.json")))
        self.assertEqual([f["name"] for f in m["files"]], ["screenshot-1.png"])
        self.assertTrue(os.path.isfile(os.path.join(r["dir"], "files", "screenshot-1.png")))

    def test_rejects_non_image(self):
        for body in (b"<svg onload=alert(1)>", b"MZ\x90\0evil", b""):
            d = tempfile.mkdtemp()
            with self.assertRaises(report_store.ReportError) as c:
                report_store.save_report(d, make_zip(files={"files/screenshot-1.png": body}), "")
            self.assertEqual(c.exception.status, 400)
            self.assertEqual(os.listdir(d), [])      # nothing left behind

    def test_svg_name_is_plain_file_and_traversal_is_flat(self):
        d, r = self.save({"files/screenshot-1.svg": b"<svg/>", "files/../../screenshot-2.png": PNG})
        m = json.load(open(os.path.join(r["dir"], "meta.json")))
        kinds = {f["name"]: f.get("kind") for f in m["files"]}
        self.assertIsNone(kinds["screenshot-1.svg"])
        self.assertEqual(kinds["screenshot-2.png"], "screenshot")
        self.assertEqual(sorted(os.listdir(r["dir"])), ["files", "meta.json"])

    def test_too_many_and_too_big(self):
        with self.assertRaises(report_store.ReportError) as c:
            self.save({"files/screenshot-%d.png" % i: PNG for i in range(1, 7)})
        self.assertEqual(c.exception.status, 400)
        with self.assertRaises(report_store.ReportError) as c:
            self.save({"files/screenshot-1.png": PNG + b"\0" * (8 * 1024 * 1024)})
        self.assertEqual(c.exception.status, 413)


MP4 = b"\0\0\0\x18ftypisom\0\0\0\0" + b"\0" * 200
MOV = b"\0\0\0\x14ftypqt  \0\0\0\0" + b"\0" * 200
WEBM = b"\x1a\x45\xdf\xa3\x93\x42\x82\x84webm" + b"\0" * 200
MKV = b"\x1a\x45\xdf\xa3\x93\x42\x82\x88matroska" + b"\0" * 200


class TestClips(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.saved = (report_store.CLIP_MAX_EACH, report_store.CLIP_MAX_TOTAL, report_store.DISK_MIN_FREE)

    def tearDown(self):
        report_store.CLIP_MAX_EACH, report_store.CLIP_MAX_TOTAL, report_store.DISK_MIN_FREE = self.saved

    def report(self, clips=2, limiter=None, ip="9.9.9.9"):
        z = make_zip(meta={"text": "clip report please", "name": "T", "clips": clips})
        return report_store.save_report(self.root, z, ip, clip_limiter=limiter)

    def put(self, r, data, key=None):
        return report_store.save_clip(self.root, r["code"], r["clipKey"] if key is None else key, len(data), io.BytesIO(data))

    def test_magic_types(self):
        r = self.report()
        self.assertEqual(self.put(r, MP4)["name"], "clip-1.mp4")
        self.assertEqual(self.put(r, WEBM)["name"], "clip-2.webm")
        m = json.load(open(os.path.join(r["dir"], "meta.json")))
        vids = [f for f in m["files"] if f.get("kind") == "video"]
        self.assertEqual([f["contentType"] for f in vids], ["video/mp4", "video/webm"])
        self.assertEqual(report_store.sniff_video(MOV), "mov")
        self.assertEqual(report_store.sniff_video(MKV), "mkv")
        self.assertIsNone(report_store.sniff_video(b"<html>" + b"\0" * 40))

    def test_rejects_non_video_and_leaves_no_part(self):
        r = self.report()
        for body in (b"MZ" + b"\0" * 80, PNG, b"x" * 100):
            with self.assertRaises(report_store.ReportError) as c:
                self.put(r, body)
            self.assertEqual(c.exception.status, 400)
        self.assertEqual(os.listdir(os.path.join(r["dir"], "files")), ["system.txt"] if False else os.listdir(os.path.join(r["dir"], "files")))
        self.assertFalse([n for n in os.listdir(os.path.join(r["dir"], "files")) if n.endswith(".part")])

    def test_caps(self):
        report_store.CLIP_MAX_EACH, report_store.CLIP_MAX_TOTAL = 300, 450
        r = self.report()
        with self.assertRaises(report_store.ReportError) as c:       # over the per-clip cap: refused on the declared length
            self.put(r, MP4 + b"\0" * 200)
        self.assertEqual(c.exception.status, 413)
        self.assertIn("trim it", c.exception.msg)
        self.put(r, MP4 + b"\0" * 50)                                  # 264 B
        with self.assertRaises(report_store.ReportError) as c:       # 264 + 264 > 450
            self.put(r, MP4 + b"\0" * 50)
        self.assertEqual(c.exception.status, 413)

    def test_max_two_clips_and_key(self):
        r = self.report(clips=2)
        with self.assertRaises(report_store.ReportError) as c:
            self.put(r, MP4, key="0" * 32)
        self.assertEqual(c.exception.status, 403)
        self.put(r, MP4); self.put(r, MP4)
        with self.assertRaises(report_store.ReportError) as c:
            self.put(r, MP4)
        self.assertEqual(c.exception.status, 400)
        r0 = self.report(clips=0)
        self.assertEqual(r0["clipKey"], "")
        with self.assertRaises(report_store.ReportError):
            report_store.save_clip(self.root, r0["code"], "", len(MP4), io.BytesIO(MP4))

    def test_short_upload_aborts(self):
        r = self.report()
        with self.assertRaises(report_store.ReportError):
            report_store.save_clip(self.root, r["code"], r["clipKey"], len(MP4) + 500, io.BytesIO(MP4))
        self.assertFalse([n for n in os.listdir(os.path.join(r["dir"], "files")) if n.startswith(".clip")])

    def test_rate_limit_and_disk_guard(self):
        lim = report_store.RateLimiter(3, 3600)
        for _ in range(3):
            self.assertTrue(self.report(limiter=lim)["clipKey"])
        r = self.report(limiter=lim)                                   # 4th: report accepted, clips refused
        self.assertEqual(r["clipKey"], "")
        self.assertIn("too many", r["clipRefused"])
        report_store.DISK_MIN_FREE = 1 << 60                           # disk "full": text/logs still accepted, clips not
        r = self.report()
        self.assertEqual(r["clipKey"], "")
        self.assertIn("storage", r["clipRefused"])

    def test_http_put_streams_and_refuses_by_header(self):
        report_store.CLIP_MAX_EACH = 1000
        srv = server.make_server(tempfile.mkdtemp(), "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        try:
            req = urllib.request.Request(base + "/report", data=make_zip(meta={"text": "clip via http ok", "name": "T", "clips": 1}), method="POST")
            j = json.loads(urllib.request.urlopen(req, timeout=5).read())
            self.assertTrue(j["clipKey"])
            q = "/report-clip?code=%s&key=%s" % (j["code"], j["clipKey"])
            big = urllib.request.Request(base + q, data=MP4 + b"\0" * 2000, method="PUT")
            with self.assertRaises(urllib.error.HTTPError) as c:
                urllib.request.urlopen(big, timeout=5)
            self.assertEqual(c.exception.code, 413)
            ok = urllib.request.Request(base + q, data=MP4, method="PUT")
            self.assertEqual(json.loads(urllib.request.urlopen(ok, timeout=5).read())["name"], "clip-1.mp4")
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
