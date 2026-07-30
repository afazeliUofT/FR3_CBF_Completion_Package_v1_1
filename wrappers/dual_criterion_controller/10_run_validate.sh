#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/41_0_run_dual_criterion_controller_reevaluation.py \
  --config config/dual_criterion_controller_reevaluation_v1.json

python3 scripts/41_1_validate_dual_criterion_controller_reevaluation.py \
  --config config/dual_criterion_controller_reevaluation_v1.json

echo "CORRECTED DUAL-CRITERION CONTROLLER RUN/VALIDATION: PASS"
