#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"; source .venv/bin/activate
python3 scripts/40_2_sync_eess_dual_criterion_status.py --config config/eess_dual_criterion_audit_v1.json
python3 scripts/40_3_build_eess_dual_criterion_review_bundle.py --config config/eess_dual_criterion_audit_v1.json
echo "EESS DUAL-CRITERION STATUS/PACKAGE: PASS"
