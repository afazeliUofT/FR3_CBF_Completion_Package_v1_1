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
  2d4e21099fbdc1e083b46dfbf4ce8e7f9cd1fb45 HEAD

git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

python3 - <<'PY'
from pathlib import Path
import hashlib
import json

root = Path.cwd()
cfg = json.loads(
    (root / "config/dual_criterion_controller_reevaluation_v1.json")
    .read_text(encoding="utf-8")
)
for relative, expected in cfg["dependency_sha256"].items():
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"Dependency SHA-256 mismatch for {relative}: {actual} != {expected}"
        )

for relative in [
    "data/real/full_topology_export_18696267_validated_v4/output/"
    "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json",
    "data/real/full_topology_export_18696267_validated_v4/output/"
    "frequency_response.npy",
    "evidence/eess_dual_criterion_audit_v1/"
    "EESS_DUAL_CRITERION_GATE_DECISION.json",
    "data/real/eess_dual_criterion_audit_v1/"
    "kappa_short_p0005_multiple.npy",
    "data/real/eess_dual_criterion_audit_v1/"
    "kappa_long_p20_multiple.npy",
    "data/real/eess_dual_criterion_audit_v1/"
    "kappa_short_p0005_single.npy",
    "data/real/eess_dual_criterion_audit_v1/"
    "kappa_long_p20_single.npy",
    "data/real/eess_dual_criterion_audit_v1/"
    "allowance_short_exact_w.npy",
    "data/real/eess_dual_criterion_audit_v1/"
    "allowance_long_exact_w.npy",
]:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(path)

validation = json.loads(
    (
        root
        / "data/real/full_topology_export_18696267_validated_v4/output/"
        "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json"
    ).read_text(encoding="utf-8")
)
assert validation["status"] == (
    "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
)
gate = json.loads(
    (
        root
        / "evidence/eess_dual_criterion_audit_v1/"
        "EESS_DUAL_CRITERION_GATE_DECISION.json"
    ).read_text(encoding="utf-8")
)
assert gate["status"] == (
    "PASS_REGULATORY_DIAGNOSIS_CONTROLLER_REEVALUATION_REQUIRED"
)
assert gate["recommended_provisional_action_grid_max_db"] == 70
assert gate["hard_null_endpoint_required"] is True
print("DUAL-CRITERION INPUT/DEPENDENCY PRECHECK: PASS")
PY

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_dual_criterion_controller_reevaluation.py

echo "CORRECTED DUAL-CRITERION CONTROLLER PREFLIGHT: PASS"
