#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

MATLAB_EXE="${MATLAB_EXE:-/mnt/c/Program Files/MATLAB/R2026a/bin/matlab.exe}"
P452_WINDOWS_ROOT="${P452_WINDOWS_ROOT:-/mnt/c/Users/alifa/FR3_P452_Validation_v18_R2026a}"
PROBE_GAIN="${P452_MECHANISM_PROBE_GAIN_DBI:-100}"

[[ -f "$MATLAB_EXE" ]]
[[ -d "$P452_WINDOWS_ROOT/matlab" ]]

rm -rf "$P452_WINDOWS_ROOT/e3_57_sector_reference_screen"
mkdir -p "$P452_WINDOWS_ROOT/e3_57_sector_reference_screen"

cp -a data/real/e3_all_site_p452/. \
  "$P452_WINDOWS_ROOT/e3_57_sector_reference_screen/"
cp -p matlab/run_e3_all_site_p452_mechanism_probe.m \
  "$P452_WINDOWS_ROOT/matlab/run_e3_all_site_p452_mechanism_probe.m"

MATLAB_DIR_WIN="$(wslpath -m "$P452_WINDOWS_ROOT/matlab")"
WORK_WIN="$(wslpath -m "$P452_WINDOWS_ROOT/e3_57_sector_reference_screen")"

"$MATLAB_EXE" -wait -batch \
  "cd('$MATLAB_DIR_WIN'); run_e3_all_site_p452_mechanism_probe(string('$WORK_WIN'), string('$WORK_WIN'), $PROBE_GAIN);"

for file in \
  p452_troposcatter_suppressed_probe.csv \
  P452_MECHANISM_PROBE_MATLAB_AUDIT.json
do
  [[ -f "$P452_WINDOWS_ROOT/e3_57_sector_reference_screen/$file" ]] || {
    echo "MISSING MECHANISM OUTPUT: $file"
    exit 4
  }
  cp -p "$P452_WINDOWS_ROOT/e3_57_sector_reference_screen/$file" \
    "data/real/e3_57_sector_reference_screen/$file"
  echo "COPIED MECHANISM OUTPUT: $file"
done

PYTHONDONTWRITEBYTECODE=1 python3 scripts/25_5_validate_e3_p452_mechanism_probe.py \
  --config config/e3_57_sector_reference_screen.yaml

echo "WRAPPER 10 MECHANISM PROBE: PASS"
