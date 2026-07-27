#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong branch"
  exit 2
}
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected origin: $ORIGIN"
  exit 2
}
git merge-base --is-ancestor 16dfe8e267bc7ea8005da8f8cc03d4143519d7c8 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 2
}

REQ=(
  data/external/etsi/tr_138901v190400p.pdf
  evidence/sionna2_topology_readiness/SIONNA2_TOPOLOGY_READINESS_DECISION.json
  evidence/sionna2_topology_readiness/CUSTOM_57_SECTOR_SIONNA_PILOT_AUDIT.json
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
  tests/test_tr38901_nibi_pilot_prep.py

echo "WRAPPER 00 PREFLIGHT: PASS"
