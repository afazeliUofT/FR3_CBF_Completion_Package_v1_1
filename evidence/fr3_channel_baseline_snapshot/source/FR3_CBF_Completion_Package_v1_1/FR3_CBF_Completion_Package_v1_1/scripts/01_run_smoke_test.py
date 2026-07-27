from __future__ import annotations

import subprocess
import sys

from _bootstrap import ROOT

COMMANDS = [
    [sys.executable, "scripts/04_run_s1_adequacy.py", "--config", "config/s1_adequacy.yaml", "--mode", "demo"],
    [sys.executable, "scripts/08_export_bundle_template.py"],
    [sys.executable, "scripts/09_validate_experiment_bundle.py", "data/demo/experiment_bundle_template.npz"],
    [sys.executable, "scripts/10_run_e1_static_fs.py", "--config", "config/e1_static_fs.yaml", "--mode", "demo"],
    [sys.executable, "scripts/11_run_e2_dynamic_fs.py", "--config", "config/e2_dynamic_fs.yaml", "--mode", "demo"],
    [sys.executable, "scripts/12_run_e3_tracking_eess.py", "--config", "config/e3_tracking_eess.yaml", "--mode", "demo"],
    [sys.executable, "scripts/07_run_calibration.py", "--config", "config/calibration.yaml", "--mode", "demo"],
]


def main() -> int:
    for command in COMMANDS:
        print("+", " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
    print("SMOKE TEST: PASS (demo evidence only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
