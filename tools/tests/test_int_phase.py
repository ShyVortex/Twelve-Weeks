"""Interrogation lockbox-phase respawn selection (tools/ext/int_phase_spawn.h): compiles tools/tests/int_phase_harness.c with the repo gcc and runs it."""
import os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _gcc():
    for base in (ROOT, os.environ.get("T2R_MAIN_ROOT", ROOT)):
        g = os.path.join(base, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
        if os.path.exists(g):
            return g
    return "gcc"


class IntPhaseSpawn(unittest.TestCase):
    def test_selection(self):
        gcc = _gcc()
        out = os.path.join(tempfile.mkdtemp(), "ips.exe")
        env = dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ.get("PATH", ""))
        subprocess.check_call([gcc, "-O1", "-Wall", "-o", out, os.path.join(HERE, "int_phase_harness.c")], env=env)
        r = subprocess.run([out], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
