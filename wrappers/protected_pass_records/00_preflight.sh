#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: expected branch e3-first-sector-p452"
  exit 2
}
git merge-base --is-ancestor \
  312f651fe271ca85e88f659eca3225f329f0d9c5 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

python3 - <<'PY'
import importlib.util
for name in ["skyfield", "sgp4", "numpy", "pandas"]:
    if importlib.util.find_spec(name) is None:
        raise SystemExit(f"ERROR: required module is missing: {name}")
print("ORBIT DEPENDENCY PREFLIGHT: PASS")
PY

for path in \
  data/external/tle/active_case.tle \
  data/external/tle/TLE_SOURCE_RECORD.json \
  data/real/e3_reference_case/e3_track_selected_pass_1s.csv \
  data/real/e3_57_sector_reference_screen/sector_static_reference_accounting.csv \
  data/real/full_topology_export_18696267_validated_v4/output/kappa_time_sector.npy \
  data/real/full_topology_export_18696267_validated_v4/output/nominal_mode_leakage_w.npy \
  campaign/phase1_candidate_v1/CAMPAIGN_METADATA.json
do
  [[ -f "$path" ]] || {
    echo "ERROR: required input is missing: $path"
    exit 4
  }
  echo "OK      $path"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_protected_pass_records_phase1.py

echo "PROTECTED-PASS RECORD PREFLIGHT: PASS"
