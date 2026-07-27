#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]]
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected Git origin: $ORIGIN"
  exit 2
}
git merge-base --is-ancestor 9d2a18bdaa9168844e279085a51eaad943feae0a HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes detected. Commit or unstage them before this drop-in."
  git diff --cached --name-status
  exit 2
}

REQ=(
  data/real/e3_all_site_terrain_review/terrain_review/terrain_summary.csv
  data/real/e3_all_site_terrain_review/terrain_review/terrain_profile_samples.csv.gz
  data/real/e3_all_site_terrain_review/terrain_review/TERRAIN_AUDIT.json
  data/real/e3_all_site_terrain_review/ALL_SITE_TERRAIN_REVIEW_AUDIT.json
  data/real/e3_all_site_terrain_review/terrain_review/all_19_site_profiles_review.pdf
  data/real/earth_station.csv
  data/real/bs_sites.csv
  data/external/p452/reference_v18_commit.txt
)
for file in "${REQ[@]}"; do
  [[ -f "$file" ]] || { echo "MISSING $file"; exit 2; }
  echo "OK      $file"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_e3_all_site_p452_dropin.py

echo
echo "ALL-SITE TERRAIN NUMERICAL SUMMARY"
python3 - <<'PY'
import json
import pandas as pd
summary = pd.read_csv(
    "data/real/e3_all_site_terrain_review/terrain_review/terrain_summary.csv"
)
audit = json.load(open(
    "data/real/e3_all_site_terrain_review/ALL_SITE_TERRAIN_REVIEW_AUDIT.json",
    encoding="utf-8",
))
print(summary[[
    "link_id", "distance_km_wgs84", "total_sample_count",
    "min_profile_terrain_m_asl", "max_profile_terrain_m_asl",
    "tx_implied_antenna_height_agl_m",
    "rx_implied_antenna_height_agl_m",
    "inclusive_minus_interior_m", "qc_flags",
]].to_string(index=False))
print()
print("Blocking flags:", audit["blocking_flags"])
print("Nonblocking flag count:", len(audit["nonblocking_flags"]))
print("Maximum adjacent terrain step (m):", audit["maximum_absolute_adjacent_step_m"])
print("Maximum segment slope:", audit["maximum_absolute_segment_slope"])
PY

PDF="$ROOT/data/real/e3_all_site_terrain_review/terrain_review/all_19_site_profiles_review.pdf"
if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$PDF")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$ROOT/data/real/e3_all_site_terrain_review")" >/dev/null 2>&1 || true
fi

echo
echo "MANUAL REVIEW REQUIRED"
echo "Review every page of:"
echo "  $PDF"
echo "Check all 19 profiles for DEM voids, isolated spikes, tile seams,"
echo "misplaced endpoints, implausible discontinuities, and incorrect phase-centre heights."
echo
read -r -p "After reviewing every page, type exactly 'I REVIEWED ALL 19 TERRAIN PROFILES': " CONFIRMATION
[[ "$CONFIRMATION" == "I REVIEWED ALL 19 TERRAIN PROFILES" ]] || {
  echo "Confirmation not accepted. No freeze or P.452 run was performed."
  exit 3
}
export E3_ALL_SITE_TERRAIN_CONFIRMATION="$CONFIRMATION"
echo "WRAPPER 00 PREFLIGHT/MANUAL REVIEW: PASS"
