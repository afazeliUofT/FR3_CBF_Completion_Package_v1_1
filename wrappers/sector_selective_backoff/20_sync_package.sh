#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/43_2_sync_sector_selective_backoff_status.py \
  --config config/sector_selective_backoff_v1.json

python3 scripts/43_3_build_sector_selective_backoff_review_bundle.py \
  --config config/sector_selective_backoff_v1.json

echo
python3 -m json.tool \
  evidence/sector_selective_backoff_v1/SECTOR_BACKOFF_GATE_DECISION.json
echo
python3 -m json.tool \
  results/sector_selective_backoff_v1/SECTOR_BACKOFF_AUDIT.json \
  | tail -n 180

echo "DECLARED-ENVELOPE SECTOR BACKOFF STATUS/PACKAGE: PASS"
