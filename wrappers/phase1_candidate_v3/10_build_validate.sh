#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/46_0_build_phase1_candidate_v3.py \
  --contract config/phase1_campaign_contract_v3.json

python3 scripts/46_1_validate_phase1_candidate_v3.py \
  --contract config/phase1_campaign_contract_v3.json

echo "PHASE-1 CANDIDATE V3 BUILD/VALIDATION: PASS"
