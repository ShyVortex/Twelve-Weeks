"""tools/ext/dcnames.h (the table t2r-ext's dc_audit_tick checks against the engine's record table) must match the sources: every literal native /
script-function name the ext calls is listed. Regenerate with python tools/ext/gen_dcnames.py.
Run: python tools/tests/test_dcnames.py"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "..", "ext", "gen_dcnames.py")
r = subprocess.run([sys.executable, GEN, "--check"], capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
sys.exit(r.returncode)
