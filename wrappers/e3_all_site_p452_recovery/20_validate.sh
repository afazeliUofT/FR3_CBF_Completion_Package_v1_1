#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

python3 scripts/20_validate_p452_export.py \
  data/real/e3_all_site_p452/p452_all_site_coupling_export.csv

PYTHONDONTWRITEBYTECODE=1 python3 scripts/25_2_validate_e3_all_site_p452.py \
  --config config/e3_all_site_p452.yaml

PYTHONDONTWRITEBYTECODE=1 python3 scripts/25_3_independent_review_e3_all_site_p452.py \
  --config config/e3_all_site_p452.yaml

echo
cat data/real/e3_all_site_p452/ALL_SITE_P452_VALIDATION.md
echo
cat data/real/e3_all_site_p452/ALL_SITE_P452_INDEPENDENT_REVIEW.md
echo "WRAPPER 20 VALIDATION: PASS"
