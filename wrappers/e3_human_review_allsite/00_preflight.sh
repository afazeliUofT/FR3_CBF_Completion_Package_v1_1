#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

BRANCH="$(git branch --show-current)"
[[ "$BRANCH" == "e3-first-sector-p452" ]] || {
  echo "ERROR: expected e3-first-sector-p452, found $BRANCH"
  exit 2
}
git merge-base --is-ancestor ca8d9784d38eea7b6334377f5cd5161b4f5de11b HEAD

REQ=(
  data/real/e3_first_sector_p452/gain_accounting_timeseries.csv.gz
  data/real/e3_first_sector_p452/p452_basic_loss.csv
  data/real/e3_first_sector_p452/earth_station_gain_timeseries.csv
  data/real/earth_station.csv
  data/real/bs_sites.csv
  data/external/mrdem_e3_layout/mrdem_dtm_study_subset.tif
)
for f in "${REQ[@]}"; do
  [[ -f "$f" ]] || { echo "MISSING $f"; exit 3; }
  echo "OK      $f"
done

for w in 00_prepare 10_matlab 20_postprocess_validate 30_package_review; do
  v="$(tr -d '[:space:]' < "logs/e3_first_sector_p452/${w}.exitcode")"
  [[ "$v" == "0" ]] || { echo "BAD EXITCODE $w=$v"; exit 4; }
  echo "EXITCODE PASS: $w=0"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_e3_first_sector_p452_dropin.py \
  tests/test_e3_human_review_allsite_dropin.py

echo "WRAPPER 00 PREFLIGHT: PASS"
