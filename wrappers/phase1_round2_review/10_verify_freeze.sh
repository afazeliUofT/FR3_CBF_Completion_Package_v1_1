#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/47_0_verify_freeze_round2_review.py \
  --review config/phase1_candidate_v3_round2_review_v1.json

python3 scripts/47_1_validate_round2_review_freeze.py \
  --review config/phase1_candidate_v3_round2_review_v1.json

echo "PHASE-1 ROUND-2 REVIEW VERIFY/FREEZE: PASS"
