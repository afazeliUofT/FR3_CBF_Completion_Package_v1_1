#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

: "${FR3_REVIEW_ZIP:?FR3_REVIEW_ZIP is required}"

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/32_0_freeze_nibi_one_seed_18658301.py \
  --review-zip "$FR3_REVIEW_ZIP" \
  --config config/one_seed_18658301_freeze.json

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/32_1_validate_one_seed_18658301_freeze.py \
  --config config/one_seed_18658301_freeze.json

echo "ONE-SEED EVIDENCE FREEZE/VALIDATION: PASS"
