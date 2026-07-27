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
  exit 3
}
git merge-base --is-ancestor 9d2a18bdaa9168844e279085a51eaad943feae0a HEAD
git diff --cached --quiet || {
  echo "ERROR: staged changes detected"
  git diff --cached --name-status
  exit 4
}

REQ=(
  data/real/e3_all_site_p452/ALL_SITE_TERRAIN_DECISION.json
  data/real/e3_all_site_p452/p452_all_site_profiles.csv
  data/real/e3_all_site_p452/p452_all_site_site_parameters.csv
  data/real/e3_all_site_p452/p452_all_site_parameters.json
  data/real/e3_all_site_p452/ALL_SITE_P452_PREP_AUDIT.json
  data/real/e3_first_sector_p452/p452_basic_loss.csv
)
for file in "${REQ[@]}"; do
  [[ -f "$file" ]] || { echo "MISSING $file"; exit 5; }
  echo "OK      $file"
done

python3 - <<'PY'
import json
from pathlib import Path
decision = json.loads(Path(
    "data/real/e3_all_site_p452/ALL_SITE_TERRAIN_DECISION.json"
).read_text(encoding="utf-8"))
prep = json.loads(Path(
    "data/real/e3_all_site_p452/ALL_SITE_P452_PREP_AUDIT.json"
).read_text(encoding="utf-8"))
params = json.loads(Path(
    "data/real/e3_all_site_p452/p452_all_site_parameters.json"
).read_text(encoding="utf-8"))
assert decision["status"] == "FROZEN_FOR_19_SITE_P452_BASIC_LOSS_AUDIT"
assert decision["reviewer"] == "Ali Fazeli"
assert decision["manual_confirmation"] == "I REVIEWED ALL 19 TERRAIN PROFILES"
assert decision["site_count"] == 19
assert prep["status"] == "MATLAB_READY_FROZEN"
assert prep["site_count"] == 19
assert prep["profile_sample_count"] == 1963
assert prep["expected_output_row_count"] == 798
assert params["expected_output_row_count"] == 798
print("RECOVERY STATE CHECK: PASS")
print("Terrain freeze reviewer:", decision["reviewer"])
print("Sites:", decision["site_count"])
print("Profile samples:", prep["profile_sample_count"])
print("Expected rows:", prep["expected_output_row_count"])
PY

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_e3_all_site_p452_dropin.py \
  tests/test_e3_all_site_p452_matlab_table_recovery.py

echo "WRAPPER 00 RECOVERY PREFLIGHT: PASS"
