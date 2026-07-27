#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]]
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]]
git merge-base --is-ancestor 7eb23f2cb2c0769572b66242566e29603a5fb31e HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 2
}

REQ=(
  data/real/e3_all_site_p452/p452_all_site_basic_loss.csv
  data/real/e3_all_site_p452/p452_all_site_profiles.csv
  data/real/e3_all_site_p452/p452_all_site_site_parameters.csv
  data/real/e3_all_site_p452/ALL_SITE_P452_VALIDATION.json
  data/real/e3_all_site_p452/ALL_SITE_P452_INDEPENDENT_REVIEW.json
  data/real/bs_sites.csv
  data/real/bs_sectors.csv
  data/real/earth_station.csv
  data/real/e3_reference_case/e3_track_selected_pass_1s.csv
)
for file in "${REQ[@]}"; do
  [[ -f "$file" ]] || { echo "MISSING $file"; exit 3; }
  echo "OK      $file"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_e3_57_sector_reference_screen.py

STAMP="$(date -u +%Y%m%d_%H%M%S)"
if [[ -d data/real/e3_57_sector_reference_screen ]]; then
  mv data/real/e3_57_sector_reference_screen \
    "data/real/e3_57_sector_reference_screen_before_${STAMP}"
fi
mkdir -p data/real/e3_57_sector_reference_screen results/e3_57_sector_reference_screen

PYTHONDONTWRITEBYTECODE=1 python3 scripts/25_4_human_review_e3_all_site_p452.py \
  --config config/e3_57_sector_reference_screen.yaml

echo "WRAPPER 00 PREFLIGHT/HUMAN REVIEW: PASS"
