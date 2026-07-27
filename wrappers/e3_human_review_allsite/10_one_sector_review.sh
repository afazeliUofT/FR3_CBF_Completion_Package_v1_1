#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 python3 scripts/24_6_independent_review_e3_first_sector.py \
  --config config/e3_all_site_terrain_review.yaml
echo
cat data/real/e3_first_sector_human_review/ONE_SECTOR_HUMAN_REVIEW_DECISION.md
echo "WRAPPER 10 ONE-SECTOR HUMAN REVIEW: PASS"
