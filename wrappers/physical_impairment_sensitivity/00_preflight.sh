#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]]
git merge-base --is-ancestor 6515d52b7c80d2cfe186be530cdbfe36f928179a HEAD
git diff --cached --quiet || { echo "ERROR: pre-existing staged changes"; git diff --cached --name-status; exit 2; }
for path in \
  data/real/full_topology_export_18696267_validated_v4/output/frequency_response.npy \
  data/real/eess_dual_criterion_audit_v1/kappa_long_p20_multiple.npy \
  data/real/eess_dual_criterion_audit_v1/kappa_long_p20_single.npy \
  config/dual_criterion_controller_reevaluation_v1.json; do
  [[ -f "$path" ]] || { echo "ERROR: missing $path"; exit 3; }
done
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_physical_impairment_sensitivity.py
echo "PHYSICAL IMPAIRMENT SENSITIVITY PREFLIGHT: PASS"
