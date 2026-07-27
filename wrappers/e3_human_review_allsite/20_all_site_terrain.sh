#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

STAMP="$(date -u +%Y%m%d_%H%M%S)"
if [[ -d data/real/e3_all_site_terrain_review ]]; then
  mv data/real/e3_all_site_terrain_review \
    "data/real/e3_all_site_terrain_review_before_${STAMP}"
fi

PYTHONDONTWRITEBYTECODE=1 python3 scripts/24_7_prepare_e3_all_site_links.py \
  --config config/e3_all_site_terrain_review.yaml

PYTHONDONTWRITEBYTECODE=1 python3 scripts/03_4_add_mrdem_terrain_profiles.py \
  --links data/real/e3_all_site_terrain_review/site_links_input.csv \
  --dem data/external/mrdem_e3_layout/mrdem_dtm_study_subset.tif \
  --output data/real/e3_all_site_terrain_review/site_links_with_terrain.csv \
  --out-dir data/real/e3_all_site_terrain_review/terrain_review \
  --spacing-m 30 \
  --mean-convention inclusive \
  --expected-links 19

PYTHONDONTWRITEBYTECODE=1 python3 scripts/03_5_plot_mrdem_terrain_profiles.py \
  --profiles data/real/e3_all_site_terrain_review/terrain_review/terrain_profile_samples.csv.gz \
  --summary data/real/e3_all_site_terrain_review/terrain_review/terrain_summary.csv \
  --output data/real/e3_all_site_terrain_review/terrain_review/all_19_site_profiles_review.pdf

PYTHONDONTWRITEBYTECODE=1 python3 scripts/24_8_validate_e3_all_site_terrain.py \
  --config config/e3_all_site_terrain_review.yaml

echo
cat data/real/e3_all_site_terrain_review/ALL_SITE_TERRAIN_REVIEW_AUDIT.md
echo
echo "REVIEW REQUIRED:"
echo "  data/real/e3_all_site_terrain_review/terrain_review/all_19_site_profiles_review.pdf"
echo "  data/real/e3_all_site_terrain_review/terrain_review/terrain_summary.csv"
echo "  data/real/e3_all_site_terrain_review/ALL_SITE_TERRAIN_REVIEW_AUDIT.json"
echo "WRAPPER 20 ALL-SITE TERRAIN PREPARATION: PASS"
