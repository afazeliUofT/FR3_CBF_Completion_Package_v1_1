#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong Git branch"
  exit 2
}
git merge-base --is-ancestor \
  41ec80f28f2b5a68fa32d09efc428a60c20b1a4f HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

DATA="data/real/full_topology_export_18696267_validated_v4/output"
[[ -f "$DATA/FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json" ]] || {
  echo "ERROR: validated full-topology data are missing"
  exit 4
}
[[ -f "$DATA/protected_amp_perpendicular.npy" ]]

python3 - <<'PY'
from pathlib import Path
import json

decision = json.loads(
    Path(
        "evidence/constrained_pf_controller_milestone_v1/"
        "CONSTRAINED_PF_CONTROLLER_GATE_DECISION.json"
    ).read_text(encoding="utf-8")
)
assert decision["status"] == (
    "PASS_CONSTRAINED_PF_CONTROLLER_MILESTONE_ONE_SEED"
)
assert decision["sum_rate_primary_objective"] is False
print("CONSTRAINED PF PREDECESSOR PRECHECK: PASS")
PY

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_robust_delayed_safety.py

echo "ROBUST DELAYED SAFETY PREFLIGHT: PASS"
