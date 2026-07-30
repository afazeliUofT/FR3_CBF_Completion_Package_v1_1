#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/41_2_sync_dual_criterion_controller_status.py \
  --config config/dual_criterion_controller_reevaluation_v1.json

python3 scripts/41_3_build_dual_criterion_controller_review_bundle.py \
  --config config/dual_criterion_controller_reevaluation_v1.json

echo
python3 -m json.tool \
  evidence/dual_criterion_controller_reevaluation_v1/DUAL_CRITERION_CONTROLLER_GATE_DECISION.json
echo
python3 -m json.tool \
  results/dual_criterion_controller_reevaluation_v1/DUAL_CRITERION_CONTROLLER_AUDIT.json \
  | tail -n 220

echo "CORRECTED DUAL-CRITERION STATUS/PACKAGE: PASS"
