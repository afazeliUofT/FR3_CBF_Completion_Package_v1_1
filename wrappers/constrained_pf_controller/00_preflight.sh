#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong branch"
  exit 2
}
git merge-base --is-ancestor \
  2ca450fe3a5029b9101890bcde2dac032650a3b9 HEAD
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
[[ -f \
  "evidence/fairness_policy_audit_v1/FAIRNESS_POLICY_DECISION.json" ]] || {
  echo "ERROR: frozen fairness-policy evidence is missing"
  exit 5
}
python3 - <<'PY'
from pathlib import Path
import json
decision = json.loads(
    Path(
        "evidence/fairness_policy_audit_v1/"
        "FAIRNESS_POLICY_DECISION.json"
    ).read_text(encoding="utf-8")
)
assert decision["status"] == (
    "PASS_CONSTRAINED_PF_POLICY_FROZEN_FOR_ONE_SEED_CONTROLLER_MILESTONE"
)
assert decision["sum_rate_primary_objective"] is False
assert decision["explicit_service_floor"] is True
print("FROZEN FAIRNESS POLICY PRECHECK: PASS")
PY

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_constrained_pf_controller_milestone.py

echo "CONSTRAINED PF CONTROLLER PREFLIGHT: PASS"
