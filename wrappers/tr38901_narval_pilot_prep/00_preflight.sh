#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong Git branch"
  exit 2
}
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected Git origin: $ORIGIN"
  exit 2
}
git merge-base --is-ancestor e1a5d0c41b2a676aa05680ab558a2995eecda6e6 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 2
}

REQ=(
  data/real/tr38901_nibi_dlp_pilot_prep/TR38901_USED_SUBSET_MAPPING_DECISION.json
  data/real/tr38901_nibi_dlp_pilot_prep/SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json
  data/real/bs_sites.csv
  data/real/bs_sectors.csv
  data/real/e3_57_sector_reference_screen/sector_static_reference_accounting.csv
  data/real/e3_57_sector_reference_screen/earth_station_site_gain_timeseries.csv.gz
  /home/afazeli2006/.venvs/fr3-sionna2-2.0.1-cpu/bin/python
)
for path in "${REQ[@]}"; do
  [[ -e "$path" ]] || { echo "MISSING $path"; exit 3; }
  echo "OK      $path"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_tr38901_narval_pilot_prep.py

echo "LOCAL/NARVAL PREP PREFLIGHT: PASS"
