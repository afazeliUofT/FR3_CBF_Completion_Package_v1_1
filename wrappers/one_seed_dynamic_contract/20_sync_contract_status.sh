#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/32_2_sync_status_and_contract.py \
  --config config/one_seed_18658301_freeze.json

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/32_3_build_one_seed_review_bundle.py \
  --config config/one_seed_18658301_freeze.json

echo
cat evidence/nibi_one_seed_18658301/ONE_SEED_GATE_DECISION.md
echo
cat evidence/nibi_one_seed_18658301/COMMON_SCALE_DEGENERACY_AUDIT.md
echo "DYNAMIC CONTRACT/STATUS SYNC: PASS"
