"""run_all entry for warn_check.py (one -O2 compile of the unity build, ~1 min)."""
import os
import subprocess
import sys

sys.exit(subprocess.call([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "warn_check.py")]))
