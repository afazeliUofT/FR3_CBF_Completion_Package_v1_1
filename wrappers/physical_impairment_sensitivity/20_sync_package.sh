#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
python3 scripts/42_2_sync_physical_impairment_status.py --config config/physical_impairment_sensitivity_v1.json
python3 scripts/42_3_build_physical_impairment_review_bundle.py --config config/physical_impairment_sensitivity_v1.json
python3 -m json.tool evidence/physical_impairment_sensitivity_v1/PHYSICAL_IMPAIRMENT_GATE_DECISION.json
echo "PHYSICAL IMPAIRMENT STATUS/PACKAGE: PASS"
