#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 \
  scripts/37_0_run_constrained_pf_controller_milestone.py \
  --config config/constrained_pf_controller_milestone_v1.json

python3 \
  scripts/37_1_validate_constrained_pf_controller_milestone.py \
  --config config/constrained_pf_controller_milestone_v1.json

echo "CONSTRAINED PF CONTROLLER RUN/VALIDATION: PASS"
