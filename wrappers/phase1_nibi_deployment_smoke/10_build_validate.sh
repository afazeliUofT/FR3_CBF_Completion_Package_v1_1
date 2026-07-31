#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/50_0_build_phase1_nibi_deployment_smoke.py \
  --config config/phase1_nibi_deployment_smoke_v1.json

python3 scripts/50_1_validate_phase1_nibi_deployment_smoke.py \
  --config config/phase1_nibi_deployment_smoke_v1.json

echo "NONCAMPAIGN NIBI DEPLOYMENT SMOKE BUILD/VALIDATION: PASS"
