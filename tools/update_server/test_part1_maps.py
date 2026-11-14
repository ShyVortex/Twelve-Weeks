"""Part I file-set endpoints: python tools/update_server/test_part1_maps.py   (temp dirs only, no network beyond 127.0.0.1)."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish
import publish_part1
import server

FILES = {"pak68/hun-checkpoint-bookstore.pak": bytes(range(256)) * 40, "pak68/hun-checkpoint-bookstore-phys.pak": b"phys" * 50,
         "bin/dc1/render-settings/t1x.bin": b"t1x", "soundbank4/tarp.bnk": b"bnk"}


def get(url, headers=None):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}))


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.stage = os.path.join(self.tmp.name, "stage")
        for rel, b in FILES.items():
            p = os.path.join(self.stage, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b)
        open(os.path.join(self.stage, "unrelated.txt"), "w").write("not in the list")
        self.srv = server.make_server(self.data, "127.0.0.1", 0)
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def test_not_published(self):
        with self.assertRaises(urllib.error.HTTPError) as c:
            get(self.base + "/part1-maps.json")
        self.assertEqual(c.exception.code, 404)

    def test_publish_listed_files_and_download_with_range(self):
        publish_part1.publish(self.stage, self.data, list(FILES))        # the build's list, not the whole tree
        m = json.load(get(self.base + "/part1-maps.json"))
        self.assertEqual(sorted(f["path"] for f in m["files"]), sorted(FILES))
        self.assertEqual(m["pack"], "part1-a")
        self.assertEqual(m["total"], sum(len(b) for b in FILES.values()))
        f = next(x for x in m["files"] if x["path"].endswith("bookstore.pak"))
        self.assertEqual(get(f["url"]).read(), FILES[f["path"]])
        r = get(f["url"], {"Range": "bytes=100-199"})
        self.assertEqual(r.status, 206)
        self.assertEqual(r.read(), FILES[f["path"]][100:200])

    def test_folder_mode_publishes_every_file(self):
        m = publish_part1.publish(self.stage, self.data)
        self.assertIn("unrelated.txt", [f["path"] for f in m["files"]])

    def test_release_manifest_never_lists_it(self):
        c = os.path.join(self.tmp.name, "client")
        os.makedirs(c)
        open(os.path.join(c, "a.bin"), "wb").write(b"A" * 10)
        publish.publish(c, self.data, "stable", "1")
        publish_part1.publish(self.stage, self.data, list(FILES))
        man = json.load(get(self.base + "/manifest.json?channel=stable"))
        self.assertEqual([f["path"] for f in man["files"]], ["a.bin"])
        self.assertNotIn("part1", json.dumps(man).lower())
        publish.gc(self.data, 1, 0)                                      # release gc does not touch the Part I blobs
        self.assertIsNotNone(server.part1_maps.load(self.data))
        with self.assertRaises(urllib.error.HTTPError) as e:             # a release sha is not served as a Part I file
            get(self.base + "/part1-files/" + man["files"][0]["sha256"])
        self.assertEqual(e.exception.code, 404)

    def test_damaged_pack_is_not_offered(self):
        m = publish_part1.publish(self.stage, self.data, list(FILES))
        with open(server.part1_maps.blob_path(self.data, m["files"][0]["sha256"]), "ab") as f:
            f.write(b"x")
        with self.assertRaises(urllib.error.HTTPError) as c:
            get(self.base + "/part1-maps.json")
        self.assertEqual(c.exception.code, 404)

    def test_bad_paths_and_traversal(self):
        for bad in ("../x", "..%2f..%2fmanifests", "zz", "A" * 64):
            with self.assertRaises(urllib.error.HTTPError):
                get(self.base + "/part1-files/" + bad)
        publish_part1.publish(self.stage, self.data, list(FILES))
        mp = os.path.join(self.data, "part1", "manifest.json")
        for evil in ("..\\evil.pak", "../evil.pak", "/abs/x.pak", "a//b.pak", ".x/y"):
            m = json.load(open(mp))
            m["files"][1]["path"] = evil
            json.dump(m, open(mp, "w"))
            self.assertIsNone(server.part1_maps.load(self.data), evil)
        with self.assertRaises(SystemExit):
            publish_part1.publish(self.stage, self.data, ["../x.pak"])
        with self.assertRaises(SystemExit):
            publish_part1.publish(self.stage, self.data, ["pak68/missing.pak"])

    def test_remove_and_gc(self):
        publish_part1.publish(self.stage, self.data, list(FILES))
        publish_part1.remove(self.data)
        with self.assertRaises(urllib.error.HTTPError):
            get(self.base + "/part1-maps.json")
        self.assertEqual(publish_part1.gc(self.data), 0, "blobs younger than the grace period stay")
        self.assertEqual(publish_part1.gc(self.data, grace_hours=0), len(FILES))

    def test_gc_aborts_on_an_unreadable_manifest(self):
        publish_part1.publish(self.stage, self.data, list(FILES))
        with open(os.path.join(self.data, "part1", "manifest.json"), "w") as f:
            f.write("{ not json")
        with self.assertRaises(SystemExit):
            publish_part1.gc(self.data, grace_hours=0)
        self.assertEqual(len(os.listdir(os.path.join(self.data, "part1", "blobs"))), len(FILES))

    def test_publish_replaces_a_damaged_blob_of_the_same_size(self):
        m = publish_part1.publish(self.stage, self.data, list(FILES))
        blob = server.part1_maps.blob_path(self.data, m["files"][2]["sha256"])
        size = os.path.getsize(blob)
        with open(blob, "wb") as f:
            f.write(b"X" * size)
        publish_part1.publish(self.stage, self.data, list(FILES))
        self.assertIsNotNone(server.part1_maps.load(self.data))
        self.assertEqual(publish_part1.sha256_file(blob), m["files"][2]["sha256"])

    def test_patch_script(self):
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        src = subprocess.run(["git", "-C", here, "show", "3bcac02b~1:tools/update_server/server.py"], capture_output=True).stdout
        if not src:
            self.skipTest("no pre-patch server.py in git history")
        d = os.path.join(self.tmp.name, "pi")
        os.makedirs(d)
        shutil.copy(os.path.join(here, "part1_maps.py"), d)
        sp = os.path.join(d, "server.py")
        open(sp, "wb").write(src)
        run = lambda: subprocess.run([sys.executable, os.path.join(here, "patch_part1_server.py"), sp], capture_output=True, text=True)
        r = run()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertTrue(os.path.exists(sp + ".bak-part1"))
        self.assertEqual(open(sp + ".bak-part1", "rb").read(), src)
        import ast
        ast.parse(open(sp, encoding="utf-8").read())
        self.assertIn("already patched", run().stdout)
        # a server.py that does not fit: nothing changes, no backup
        odd = os.path.join(d, "odd.py")
        ODD = "import report_store" + chr(10) + "print(1)" + chr(10)
        open(odd, "w").write(ODD)
        r = subprocess.run([sys.executable, os.path.join(here, "patch_part1_server.py"), odd], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(odd + ".bak-part1"))
        self.assertEqual(open(odd).read(), ODD)


if __name__ == "__main__":
    unittest.main()
