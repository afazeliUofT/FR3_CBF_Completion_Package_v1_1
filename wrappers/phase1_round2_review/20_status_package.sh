#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/47_2_sync_round2_review_status.py \
  --review config/phase1_candidate_v3_round2_review_v1.json

python3 scripts/47_3_build_round2_review_bundle.py

echo
python3 -m json.tool \
  evidence/phase1_candidate_v3_round2_review/PHASE1_ROUND2_REVIEW_VERDICT.json

echo "PHASE-1 ROUND-2 REVIEW STATUS/PACKAGE: PASS"
