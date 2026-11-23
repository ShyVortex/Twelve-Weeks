"""daemon_lines: per-report daemon log snapshot + rotated log archive."""
import gzip
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daemon_lines  # noqa: E402


LIVE = """[01:58:15] BRIDGE ('10.1.2.3', 50000) steamid 76561198000000001 token PlayerOne
[01:59:01] MATCHMAKE ('10.1.2.3', 50000) refused (no Steam helper) 95dacea5
[01:59:02] PING ('10.1.2.3', 50000) 40 ms
[01:59:03] TCP ('10.1.2.3', 50000) 0f 00 01 02
[01:59:04] MATCHMAKE ('10.9.9.9', 41000) ok match 1a2b3c4d
[01:59:05] host migration match 1a2b3c4d slot 1 -> slot 2
[01:59:06] MATCHMAKE ('10.1.2.3', 50000) ok match 1a2b3c4d
[01:59:07] PlayerOnex joined (another player, longer name)
[01:59:08] unrelated line match ffffffff
"""


class DaemonLines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "host186")
        os.makedirs(self.log)
        with open(os.path.join(self.log, "daemon.log"), "w") as f:
            f.write(LIVE)
        self.rep = os.path.join(self.tmp.name, "rep")
        os.makedirs(self.rep)

    def tearDown(self):
        self.tmp.cleanup()

    def out(self):
        with open(os.path.join(self.rep, "files", "daemon-lines.txt"), encoding="utf-8") as f:
            return f.read()

    def test_snapshot_follows_session_and_match(self):
        n = daemon_lines.snapshot(self.rep, {"name": "PlayerOne", "steamId": "76561198000000001"}, log_dir=self.log)
        t = self.out()
        self.assertIn("refused (no Steam helper) 95dacea5", t)      # nameless line, same (ip, port)
        self.assertIn("host migration match 1a2b3c4d", t)           # same match id
        self.assertIn("('IP', 41000) ok match 1a2b3c4d", t)         # the other player's side of the match, IP masked
        self.assertNotIn("10.", t)
        self.assertNotIn("PING", t)
        self.assertNotIn("TCP (", t)
        self.assertNotIn("PlayerOnex", t)                             # whole-word name only
        self.assertNotIn("ffffffff", t)
        self.assertEqual(n, 5)

    def test_no_name_no_snapshot(self):
        self.assertEqual(daemon_lines.snapshot(self.rep, {"name": "", "steamId": ""}, log_dir=self.log), 0)

    def test_archive_once_and_read_from_archive(self):
        rot = os.path.join(self.log, "daemon.log.1")
        with open(rot, "w") as f:
            f.write("[01:00:00] BRIDGE ('10.1.2.3', 49000) token PlayerOne\n[01:00:01] MATCHMAKE ('10.1.2.3', 49000) refused (no Steam helper) aa\n")
        old = time.time() - 600
        os.utime(rot, (old, old))
        self.assertEqual(daemon_lines.archive_rotated(self.log), 1)
        self.assertEqual(daemon_lines.archive_rotated(self.log), 0)  # same mtime: archived once
        os.remove(rot)                                              # rotated away; the archive keeps it
        daemon_lines.snapshot(self.rep, {"name": "PlayerOne"}, log_dir=self.log)
        self.assertIn("refused (no Steam helper) aa", self.out())
        arch = os.listdir(os.path.join(self.log, "log-archive"))
        with gzip.open(os.path.join(self.log, "log-archive", arch[0]), "rt") as f:
            self.assertIn("token PlayerOne", f.read())

    def test_prune_old_archives(self):
        ad = os.path.join(self.log, "log-archive")
        os.makedirs(ad)
        p = os.path.join(ad, "daemon-20000101-000000.log.gz")
        with gzip.open(p, "wt") as f:
            f.write("x\n")
        old = time.time() - (daemon_lines.ARCHIVE_DAYS + 1) * 86400
        os.utime(p, (old, old))
        daemon_lines.archive_rotated(self.log)
        self.assertFalse(os.path.exists(p))


if __name__ == "__main__":
    unittest.main()
