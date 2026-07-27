#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -x ".venv/bin/python3" ]]; then
    echo "ERROR: .venv/bin/python3 is missing. Activate/create the project environment first."
    exit 2
fi
PYTHON=".venv/bin/python3"

required=(
  "data/real/earth_station.csv"
  "data/real/bs_sites.csv"
  "data/real/bs_sectors.csv"
  "data/real/e3_reference_case/e3_track_selected_pass_1s.csv"
  "data/real/e3_pattern_layout_review/earth_station_pattern_parameters.csv"
  "data/real/e3_pattern_layout_review/selected_pass_off_axis_summary.csv"
  "data/real/E3_PATTERN_LAYOUT_DECISION.json"
  "scripts/23_2_prepare_e3_pattern_layout.py"
)
missing=0
for path in "${required[@]}"; do
  if [[ -f "$path" ]]; then
    echo "OK      $path"
  else
    echo "MISSING $path"
    missing=$((missing + 1))
  fi
done
if [[ "$missing" -ne 0 ]]; then
  echo "ERROR: required input count missing: $missing"
  exit 3
fi

echo
echo "=== Focused tests ==="
PYTHONDONTWRITEBYTECODE=1 \
"$PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_e3_protected_window_correction.py \
  tests/test_e3_protected_window_recovery.py

echo
echo "=== Ensure future pattern/layout reruns use the protected window ==="
PYTHONDONTWRITEBYTECODE=1 \
"$PYTHON" scripts/23_2_apply_protected_window_patch.py

echo
echo "=== Recover and stabilize superseded historical inputs ==="
mkdir -p logs
PYTHONDONTWRITEBYTECODE=1 \
"$PYTHON" -X faulthandler -u \
  scripts/23_4_recover_protected_window_history.py \
  --config config/e3_protected_window_correction.yaml \
  2>&1 | tee logs/23_4_recover_protected_window_history.log

ACTIVE_DIR="data/real/e3_first_sector_audit"
STAMP="$(date -u +%Y%m%d_%H%M%S)"

if [[ -f "$ACTIVE_DIR/selected_sector.json" ]]; then
  ACTIVE_SECTOR="$($PYTHON - <<'PY'
import json
from pathlib import Path
path = Path("data/real/e3_first_sector_audit/selected_sector.json")
print(json.loads(path.read_text(encoding="utf-8")).get("sector_id", "UNKNOWN"))
PY
)"
  if [[ "$ACTIVE_SECTOR" == "E3_SITE_11_SEC_1" ]]; then
    ARCHIVE_DIR="data/real/e3_first_sector_audit_superseded_unprotected_window_${STAMP}"
    mv "$ACTIVE_DIR" "$ARCHIVE_DIR"
    echo "Archived historical first-sector directory: $ARCHIVE_DIR"
  elif [[ "$ACTIVE_SECTOR" == "E3_SITE_18_SEC_1" ]]; then
    echo "Corrected selection already exists; it will be regenerated and revalidated."
  else
    echo "ERROR: refusing to operate on unexpected active sector: $ACTIVE_SECTOR"
    exit 4
  fi
elif [[ -d "$ACTIVE_DIR" ]]; then
  if find "$ACTIVE_DIR" -mindepth 1 -print -quit | grep -q .; then
    PARTIAL_DIR="data/real/e3_first_sector_audit_partial_before_recovery_${STAMP}"
    mv "$ACTIVE_DIR" "$PARTIAL_DIR"
    echo "Archived partial active directory: $PARTIAL_DIR"
  fi
fi
mkdir -p "$ACTIVE_DIR"

echo
echo "=== Rebuild protected-window off-axis summary ==="
PYTHONDONTWRITEBYTECODE=1 \
"$PYTHON" -X faulthandler -u \
  scripts/23_3_rebuild_e3_protected_off_axis.py \
  --config config/e3_protected_window_correction.yaml \
  2>&1 | tee logs/23_3_rebuild_e3_protected_off_axis.log

echo
echo "=== Select corrected first sector ==="
PYTHONDONTWRITEBYTECODE=1 \
"$PYTHON" -X faulthandler -u \
  scripts/24_0_select_e3_first_sector.py \
  --config config/e3_protected_window_correction.yaml \
  2>&1 | tee logs/24_0_select_e3_first_sector_protected.log

echo
echo "=== Validate corrected selection ==="
PYTHONDONTWRITEBYTECODE=1 \
"$PYTHON" -X faulthandler -u \
  scripts/24_0_validate_e3_protected_selection.py \
  --config config/e3_protected_window_correction.yaml \
  2>&1 | tee logs/24_0_validate_e3_protected_selection.log

"$PYTHON" - <<'PY'
import json
from pathlib import Path
selected = json.loads(
    Path("data/real/e3_first_sector_audit/selected_sector.json").read_text(
        encoding="utf-8"
    )
)
assert selected["sector_id"] == "E3_SITE_18_SEC_1"
assert selected["site_id"] == "E3_SITE_18"
assert selected["supersedes_sector_id"] == "E3_SITE_11_SEC_1"
assert selected["protected_window_sample_count"] == 587
print("E3 PROTECTED-WINDOW WRAPPER FINAL RECORD CHECK: PASS")
PY

find scripts tests -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

echo
echo "E3 PROTECTED-WINDOW SELECTION CORRECTION: PASS"
echo "Corrected sector: E3_SITE_18_SEC_1"
echo "Next gate: build and review the corrected first-sector terrain profile."
