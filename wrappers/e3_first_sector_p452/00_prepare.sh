#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
: "${REVIEWER_NAME:?Set REVIEWER_NAME, e.g. REVIEWER_NAME='Ali Fazeli'}"
CONFIRM="${CONFIRM_TERRAIN_REVIEWED:-0}"
if [[ "$CONFIRM" != "1" ]]; then echo "FAIL: set CONFIRM_TERRAIN_REVIEWED=1 only after visual review"; exit 2; fi
printf '\n=== STEP 00: focused tests ===\n'
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_e3_first_sector_p452_dropin.py
printf '\n=== STEP 00: prepare/freeze inputs ===\n'
PYTHONDONTWRITEBYTECODE=1 python3 scripts/24_1_prepare_e3_first_sector_p452.py --config config/e3_first_sector_p452.yaml --reviewer "$REVIEWER_NAME" --confirm-terrain-reviewed
PYTHONDONTWRITEBYTECODE=1 python3 scripts/24_2_preflight_e3_first_sector_p452.py --config config/e3_first_sector_p452.yaml
echo 'WRAPPER 00 PREPARE: PASS'
