"""python test_rankbadge.py - the rank table wire format and the name key."""
import unittest
import rankbadge as R


class T(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(R.norm("[ABC] Jo e!"), "abcjoe")
        self.assertEqual(R.norm("_ABC__Jo_e_"), "abcjoe")
        self.assertEqual(R.norm("***"), "")

    def test_key_stable(self):
        self.assertEqual(R.key("[X] Ann"), R.key("_X__ann"))
        self.assertEqual(R.key("a"), (2166136261 ^ 97) * 16777619 & 0xFFFFFFFF)
        self.assertEqual(R.key("---"), 0)

    def test_wire(self):
        t = R.wire([("Ann", 1, 12), ("ANN", 3, 4), ("---", 0, 0), ("Bo", 99, 5000)])
        p = t.split()
        self.assertEqual(p[0], "n=2")
        self.assertEqual(p[1], "%08x:1:12" % R.key("Ann"))
        self.assertEqual(p[2], "%08x:9:999" % R.key("Bo"))


if __name__ == "__main__":
    unittest.main()
