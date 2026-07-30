#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 \
  scripts/37_2_sync_constrained_pf_controller_status.py \
  --config config/constrained_pf_controller_milestone_v1.json

python3 \
  scripts/37_3_build_constrained_pf_controller_review_bundle.py \
  --config config/constrained_pf_controller_milestone_v1.json

echo
python3 -m json.tool \
  evidence/constrained_pf_controller_milestone_v1/CONSTRAINED_PF_CONTROLLER_GATE_DECISION.json
echo
python3 -m json.tool \
  results/constrained_pf_controller_milestone_v1/CONSTRAINED_PF_CONTROLLER_AUDIT.json \
  | tail -n 200

echo "CONSTRAINED PF CONTROLLER STATUS/PACKAGE: PASS"
