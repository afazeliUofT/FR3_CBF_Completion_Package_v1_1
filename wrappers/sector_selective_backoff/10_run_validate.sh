#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/43_0_run_sector_selective_backoff.py \
  --config config/sector_selective_backoff_v1.json

python3 scripts/43_1_validate_sector_selective_backoff.py \
  --config config/sector_selective_backoff_v1.json

echo "DECLARED-ENVELOPE SECTOR BACKOFF RUN/VALIDATION: PASS"
