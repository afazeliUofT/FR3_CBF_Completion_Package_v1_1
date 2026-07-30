#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"; source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
python3 scripts/40_0_run_eess_dual_criterion_audit.py --config config/eess_dual_criterion_audit_v1.json
python3 scripts/40_1_validate_eess_dual_criterion_audit.py --config config/eess_dual_criterion_audit_v1.json
echo "EESS DUAL-CRITERION RUN/VALIDATION: PASS"
