#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

MATLAB_EXE="${MATLAB_EXE:-/mnt/c/Program Files/MATLAB/R2026a/bin/matlab.exe}"
P452_WINDOWS_ROOT="${P452_WINDOWS_ROOT:-/mnt/c/Users/alifa/FR3_P452_Validation_v18_R2026a}"

[[ -f "$MATLAB_EXE" ]] || { echo "MATLAB not found: $MATLAB_EXE"; exit 2; }
[[ -d "$P452_WINDOWS_ROOT/matlab" ]] || {
  echo "Validated P.452 folder missing: $P452_WINDOWS_ROOT/matlab"
  exit 3
}

rm -rf "$P452_WINDOWS_ROOT/e3_all_site_p452"
cp -a data/real/e3_all_site_p452 "$P452_WINDOWS_ROOT/e3_all_site_p452"
cp -p matlab/run_e3_all_site_p452.m \
  "$P452_WINDOWS_ROOT/matlab/run_e3_all_site_p452.m"

cmp -s \
  data/real/e3_all_site_p452/p452_all_site_profiles.csv \
  "$P452_WINDOWS_ROOT/e3_all_site_p452/p452_all_site_profiles.csv"
echo "MATLAB COPY PROFILES: MATCH"

cmp -s \
  data/real/e3_all_site_p452/p452_all_site_parameters.json \
  "$P452_WINDOWS_ROOT/e3_all_site_p452/p452_all_site_parameters.json"
echo "MATLAB COPY PARAMETERS: MATCH"

P452_MATLAB_WIN="$(wslpath -m "$P452_WINDOWS_ROOT/matlab")"
WORK_WIN="$(wslpath -m "$P452_WINDOWS_ROOT/e3_all_site_p452")"

"$MATLAB_EXE" -wait -batch \
  "cd('$P452_MATLAB_WIN'); run_e3_all_site_p452(string('$WORK_WIN'));"

for file in \
  p452_all_site_basic_loss.csv \
  p452_all_site_coupling_export.csv \
  P452_ALL_SITE_MATLAB_AUDIT.json
do
  [[ -f "$P452_WINDOWS_ROOT/e3_all_site_p452/$file" ]] || {
    echo "MISSING MATLAB OUTPUT: $file"
    exit 4
  }
  cp -p "$P452_WINDOWS_ROOT/e3_all_site_p452/$file" \
    "data/real/e3_all_site_p452/$file"
  echo "COPIED MATLAB OUTPUT: $file"
done

echo "WRAPPER 20 MATLAB: PASS"
