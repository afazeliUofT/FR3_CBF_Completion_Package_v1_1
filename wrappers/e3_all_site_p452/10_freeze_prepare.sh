#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

: "${REVIEWER_NAME:=Ali Fazeli}"
: "${E3_ALL_SITE_TERRAIN_CONFIRMATION:?Missing terrain confirmation}"

STAMP="$(date -u +%Y%m%d_%H%M%S)"
if [[ -d data/real/e3_all_site_p452 ]]; then
  mv data/real/e3_all_site_p452 \
    "data/real/e3_all_site_p452_before_${STAMP}"
fi
mkdir -p data/real/e3_all_site_p452

PYTHONDONTWRITEBYTECODE=1 python3 scripts/24_9_freeze_e3_all_site_terrain.py \
  --config config/e3_all_site_p452.yaml \
  --reviewer "$REVIEWER_NAME" \
  --confirmation "$E3_ALL_SITE_TERRAIN_CONFIRMATION"

PYTHONDONTWRITEBYTECODE=1 python3 scripts/25_0_prepare_e3_all_site_p452.py \
  --config config/e3_all_site_p452.yaml

PYTHONDONTWRITEBYTECODE=1 python3 scripts/25_1_preflight_e3_all_site_p452.py \
  --config config/e3_all_site_p452.yaml

echo "WRAPPER 10 TERRAIN FREEZE/PREPARE: PASS"
