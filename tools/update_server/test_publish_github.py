import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import publish
import publish_github
import server

FAKE_GH = r'''
import json, os, sys
state = os.environ["FAKE_GH_STATE"]
try:
    with open(state) as f:
        st = json.load(f)
except (OSError, ValueError):
    st = {"calls": [], "assets": {}}
args = sys.argv[1:]
st["calls"].append(args)
if args[:2] == ["release", "upload"]:
    for p in args[2:]:
        if os.path.isfile(p):
            size = os.path.getsize(p)
            if os.environ.get("FAKE_GH_SHORT") and os.path.basename(p) != "manifest.json":
                size -= 1
            st["assets"][os.path.basename(p)] = size
if args[:2] == ["release", "view"]:
    print(json.dumps({"assets": [{"name": n, "size": s} for n, s in st["assets"].items()]}))
with open(state, "w") as f:
    json.dump(st, f)
'''


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write(root, files):
    for rel, data in files.items():
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = os.path.join(self.tmp.name, "client")
        self.data = os.path.join(self.tmp.name, "data")
        self.work = os.path.join(self.tmp.name, "work")
        write(self.client, {
            "winmm.dll": os.urandom(5000),
            "t2r-ext.dll": b"compressible " * 20000,
            "t2r-maps/main/t2r-data.slim": b"T2SLIM03" + b"x" * 3000,
            "copy/t2r-data.slim": b"T2SLIM03" + b"x" * 3000,
            "t2r-play.log": b"never published",
            "version.txt": b"198\n",
        })
        self.fake = os.path.join(self.tmp.name, "fake_gh.py")
        with open(self.fake, "w") as f:
            f.write(FAKE_GH)
        self.state = os.path.join(self.tmp.name, "gh.json")

    def tearDown(self):
        self.tmp.cleanup()

    def run_pub(self, *extra, short=False):
        env = dict(os.environ, T2R_GH_PY=self.fake, FAKE_GH_STATE=self.state)
        if short:
            env["FAKE_GH_SHORT"] = "1"
        return subprocess.run([sys.executable, os.path.join(HERE, "publish_github.py"), self.client, "--repo", "owner/releases", "--version", "198",
                               "--data", self.data, "--work", self.work] + list(extra), env=env, capture_output=True, text=True)

    def calls(self):
        return load(self.state)["calls"]

    def test_publish_draft_upload_verify_then_public_then_manifest(self):
        r = self.run_pub()
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertEqual(calls[0][:3], ["release", "create", "build-198"])
        self.assertIn("--draft", calls[0])
        self.assertEqual(calls[-1], ["release", "edit", "build-198", "--repo", "owner/releases", "--draft=false"])
        self.assertEqual(calls[-2][:2], ["release", "view"])
        uploaded = {os.path.basename(p) for c in calls if c[:2] == ["release", "upload"] for p in c if os.path.isabs(p)}
        m = load(os.path.join(self.data, "manifests", "stable", "198.json"))
        paths = sorted(f["path"] for f in m["files"])
        self.assertEqual(paths, ["copy/t2r-data.slim", "t2r-ext.dll", "t2r-maps/main/t2r-data.slim", "version.txt", "winmm.dll"])
        base = "https://github.com/owner/releases/releases/download/build-198/"
        for f in m["files"]:
            self.assertEqual(f["url"], base + f["sha256"])
            self.assertIn(f["sha256"], uploaded)
        ext = next(f for f in m["files"] if f["path"] == "t2r-ext.dll")
        self.assertEqual((ext["enc"], ext["zurl"]), ("gzip", base + ext["sha256"] + ".gz"))
        self.assertIn(ext["sha256"] + ".gz", uploaded)
        self.assertNotIn("zurl", next(f for f in m["files"] if f["path"] == "winmm.dll"))
        self.assertIn("manifest.json", uploaded)
        self.assertEqual(len([f for f in m["files"] if f["path"].endswith("t2r-data.slim")]), 2)
        self.assertEqual(load(os.path.join(self.data, "channels.json")), {"stable": "198"})

        srv = server.make_server(self.data, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/manifest.json?channel=stable" % srv.server_address[1]) as resp:
                got = json.load(resp)
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual({f["path"]: (f["url"], f.get("zurl")) for f in got["files"]}, {f["path"]: (f["url"], f.get("zurl")) for f in m["files"]})

    def test_wrong_upload_size_keeps_the_draft_and_writes_no_manifest(self):
        r = self.run_pub(short=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("wrong size", r.stderr)
        self.assertFalse(any(c[:2] == ["release", "edit"] for c in self.calls()))
        self.assertFalse(os.path.exists(os.path.join(self.data, "manifests", "stable", "198.json")))
        self.assertFalse(os.path.exists(os.path.join(self.data, "channels.json")))

    def test_dry_run_calls_nothing_and_writes_no_manifest(self):
        r = self.run_pub("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dry run: ", r.stdout)
        self.assertFalse(os.path.exists(self.state))
        self.assertFalse(os.path.exists(os.path.join(self.data, "manifests")))
        self.assertTrue(os.path.exists(os.path.join(self.work, "manifest.json")))

    def test_bad_version_and_oversized_assets_are_refused(self):
        r = self.run_pub("--version", "../x")
        self.assertNotEqual(r.returncode, 0)
        old = publish_github.ASSET_MAX
        publish_github.ASSET_MAX = 4000
        try:
            with self.assertRaises(SystemExit) as e:
                publish_github.collect(self.client, self.work)
            self.assertIn("2 GiB", str(e.exception))
        finally:
            publish_github.ASSET_MAX = old

    def serve_manifest(self):
        srv = server.make_server(self.data, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/manifest.json?channel=stable" % srv.server_address[1]) as resp:
                return json.load(resp)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_launcher_release_and_manifest_entries(self):
        self.assertEqual(self.run_pub().returncode, 0)
        os.remove(self.state)
        exe = os.path.join(self.tmp.name, "TwelveWeeks-Launcher-0.1.45.exe")
        app = os.path.join(self.tmp.name, "TwelveWeeks-Launcher-0.1.45.AppImage")
        write(self.tmp.name, {os.path.basename(exe): os.urandom(7000), os.path.basename(app): os.urandom(9000)})
        env = dict(os.environ, T2R_GH_PY=self.fake, FAKE_GH_STATE=self.state)
        r = subprocess.run([sys.executable, os.path.join(HERE, "publish_github.py"), "--repo", "owner/releases", "--launcher", exe, "--launcher-linux", app,
                            "--launcher-version", "0.1.45", "--data", self.data, "--work", self.work], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertEqual(calls[0][:3], ["release", "create", "launcher-0.1.45"])
        self.assertEqual(calls[-1], ["release", "edit", "launcher-0.1.45", "--repo", "owner/releases", "--draft=false"])
        base = "https://github.com/owner/releases/releases/download/launcher-0.1.45/"
        la = load(os.path.join(self.data, "launcher.json"))
        ll = load(os.path.join(self.data, "launcher-linux.json"))
        self.assertEqual((la["url"], la["sha256"], la["size"]), (base + os.path.basename(exe), publish.sha256_file(exe), 7000))
        self.assertEqual(ll["url"], base + os.path.basename(app))
        got = self.serve_manifest()
        self.assertEqual((got["launcher"]["url"], got["launcher"]["version"], got["launcher"]["sha256"]), (la["url"], "0.1.45", la["sha256"]))
        self.assertEqual(got["launcher_linux"]["url"], ll["url"])

    def test_local_launcher_is_still_served_from_here(self):
        publish.publish(self.client, self.data, "stable", "197")
        exe = os.path.join(self.tmp.name, "L.exe")
        write(self.tmp.name, {"L.exe": b"launcher"})
        publish.set_launcher(self.data, exe, "0.1.40")
        got = self.serve_manifest()
        self.assertTrue(got["launcher"]["url"].startswith("http://127.0.0.1:"))
        self.assertTrue(got["launcher"]["url"].endswith("/files/" + publish.sha256_file(exe)))
        self.assertIsNone(got["launcher_linux"])

    def test_launcher_bad_input_refused(self):
        env = dict(os.environ, T2R_GH_PY=self.fake, FAKE_GH_STATE=self.state)
        bad = os.path.join(self.tmp.name, "Twelve Weeks Launcher.exe")
        write(self.tmp.name, {"Twelve Weeks Launcher.exe": b"x", "ok.exe": b"y"})
        for args in (["--launcher", bad, "--launcher-version", "1"], ["--launcher", os.path.join(self.tmp.name, "ok.exe")], []):
            r = subprocess.run([sys.executable, os.path.join(HERE, "publish_github.py"), "--repo", "owner/releases"] + args + ["--data", self.data, "--work", self.work],
                               env=env, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, args)
        self.assertFalse(os.path.exists(self.state))
        self.assertFalse(os.path.exists(os.path.join(self.data, "launcher.json")))

    def test_local_entries_still_need_their_blobs(self):
        publish.publish(self.client, self.data, "stable", "197")
        os.remove(os.path.join(self.data, "blobs", publish.sha256_file(os.path.join(self.client, "winmm.dll"))))
        with self.assertRaises(SystemExit):
            publish.promote_version(self.data, "stable", "197")


if __name__ == "__main__":
    unittest.main()
