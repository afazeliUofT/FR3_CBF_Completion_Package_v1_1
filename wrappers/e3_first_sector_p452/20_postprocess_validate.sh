#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
printf '\n=== STEP 20: validate P.452 export schema ===\n'
python3 scripts/20_validate_p452_export.py data/real/e3_first_sector_p452/p452_coupling_export.csv
printf '\n=== STEP 20: build external gain/power accounting ===\n'
PYTHONDONTWRITEBYTECODE=1 python3 scripts/24_3_build_e3_first_sector_gain_accounting.py --config config/e3_first_sector_p452.yaml
printf '\n=== STEP 20: strict validation ===\n'
PYTHONDONTWRITEBYTECODE=1 python3 scripts/24_4_validate_e3_first_sector_p452.py --config config/e3_first_sector_p452.yaml
echo 'WRAPPER 20 POSTPROCESS/VALIDATE: PASS'
