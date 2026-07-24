"""
run_all.py
----------
Runs Stage 1 and Stage 2 end-to-end and regenerates every figure/CSV in
results/. Convenience wrapper — see the two run_stage*.py scripts for
scenario-specific detail and commentary.
"""

import subprocess
import sys

for script in ["run_stage1_independent.py", "run_stage2_correlated.py"]:
    print(f"\n{'#' * 70}\n# Running {script}\n{'#' * 70}")
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        sys.exit(result.returncode)
