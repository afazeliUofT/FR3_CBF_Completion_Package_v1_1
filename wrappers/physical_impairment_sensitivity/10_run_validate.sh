#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
python3 scripts/42_0_run_physical_impairment_sensitivity.py --config config/physical_impairment_sensitivity_v1.json
python3 scripts/42_1_validate_physical_impairment_sensitivity.py --config config/physical_impairment_sensitivity_v1.json
echo "PHYSICAL IMPAIRMENT SENSITIVITY RUN/VALIDATION: PASS"
