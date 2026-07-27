#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong branch"
  exit 2
}
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected origin: $ORIGIN"
  exit 2
}
git merge-base --is-ancestor 9d2a13a659b71708b1a590f876ae7e26985f350e HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 2
}

REQ=(
  data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_DECISION.json
  data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_VALIDATION.json
  data/real/e3_57_sector_reference_screen/sector_static_reference_accounting.csv
  data/real/e3_57_sector_reference_screen/earth_station_site_gain_timeseries.csv.gz
  data/real/bs_sectors.csv
)
for file in "${REQ[@]}"; do
  [[ -f "$file" ]] || { echo "MISSING $file"; exit 3; }
  echo "OK      $file"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_distributed_precoding.py

echo "WRAPPER 00 PREFLIGHT: PASS"
