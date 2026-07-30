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
  d9ebbebc9486ee6c4bb7fa3bdb3557415394f206 HEAD || {
  echo "ERROR: physical-impairment ancestor commit is missing"
  exit 3
}
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 4
}

REQUIRED=(
  data/real/full_topology_export_18696267_validated_v4/output/FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json
  data/real/full_topology_export_18696267_validated_v4/output/frequency_response.npy
  data/real/full_topology_export_18696267_validated_v4/output/USER_TOPOLOGY.csv
  data/real/eess_dual_criterion_audit_v1/kappa_long_p20_multiple.npy
  data/real/eess_dual_criterion_audit_v1/kappa_long_p20_single.npy
  data/real/eess_dual_criterion_audit_v1/kappa_short_p0005_multiple.npy
  data/real/eess_dual_criterion_audit_v1/kappa_short_p0005_single.npy
  data/real/eess_dual_criterion_audit_v1/allowance_long_exact_w.npy
  data/real/eess_dual_criterion_audit_v1/allowance_short_exact_w.npy
  evidence/physical_impairment_sensitivity_v1/PHYSICAL_IMPAIRMENT_GATE_DECISION.json
)
for path in "${REQUIRED[@]}"; do
  [[ -f "$path" ]] || {
    echo "ERROR: required predecessor data are missing: $path"
    exit 5
  }
  echo "OK      $path"
done

python3 - <<'PY'
from pathlib import Path
import json

validation = json.loads(
    Path(
        "data/real/full_topology_export_18696267_validated_v4/output/"
        "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json"
    ).read_text(encoding="utf-8")
)
physical = json.loads(
    Path(
        "evidence/physical_impairment_sensitivity_v1/"
        "PHYSICAL_IMPAIRMENT_GATE_DECISION.json"
    ).read_text(encoding="utf-8")
)
assert validation["status"] == (
    "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
)
assert physical["status"] == (
    "PASS_DETERMINISTIC_PHYSICAL_IMPAIRMENT_SENSITIVITY_CALIBRATION_DATA_REQUIRED"
)
assert physical["campaign_execution_authorized"] is False
print("PREDECESSOR SCIENTIFIC GATES: PASS")
PY

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_sector_selective_backoff.py

echo "DECLARED-ENVELOPE SECTOR BACKOFF PREFLIGHT: PASS"
