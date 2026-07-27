#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
MATLAB_EXE="${MATLAB_EXE:-/mnt/c/Program Files/MATLAB/R2026a/bin/matlab.exe}"
P452_WINDOWS_ROOT="${P452_WINDOWS_ROOT:-/mnt/c/Users/alifa/FR3_P452_Validation_v18_R2026a}"
WORK_REL='data/real/e3_first_sector_p452'; WORK="$ROOT/$WORK_REL"; WIN_WORK="$P452_WINDOWS_ROOT/e3_first_sector_p452"; WIN_MATLAB="$P452_WINDOWS_ROOT/matlab"
echo "MATLAB_EXE: $MATLAB_EXE"
echo "P452_WINDOWS_ROOT: $P452_WINDOWS_ROOT"
for p in "$MATLAB_EXE" "$WIN_MATLAB/tl_p452.m" "$WORK/p452_profile.csv" "$WORK/p452_parameters.json" "$WORK/FIRST_SECTOR_P452_PREP_AUDIT.json"; do [[ -f "$p" ]] || { echo "FAIL missing: $p"; exit 3; }; done
rm -rf "$WIN_WORK"; mkdir -p "$WIN_WORK"; cp -a "$WORK/." "$WIN_WORK/"; cp -p matlab/run_e3_first_sector_p452.m "$WIN_MATLAB/run_e3_first_sector_p452.m"
cmp -s "$WORK/p452_profile.csv" "$WIN_WORK/p452_profile.csv" && echo 'MATLAB COPY PROFILE: MATCH'
cmp -s "$WORK/p452_parameters.json" "$WIN_WORK/p452_parameters.json" && echo 'MATLAB COPY PARAMETERS: MATCH'
MATLAB_DIR_WIN="$(wslpath -m "$WIN_MATLAB")"; WORK_WIN="$(wslpath -m "$WIN_WORK")"
echo "MATLAB folder (Windows): $MATLAB_DIR_WIN"
echo "Work folder (Windows): $WORK_WIN"
printf '\n=== STEP 10: MATLAB R2026a / validated P.452 v18.0 ===\n'
"$MATLAB_EXE" -wait -batch "cd('$MATLAB_DIR_WIN'); run_e3_first_sector_p452(string('$WORK_WIN'));"
for f in p452_basic_loss.csv p452_coupling_export.csv P452_FIRST_SECTOR_MATLAB_AUDIT.json; do [[ -f "$WIN_WORK/$f" ]] || { echo "FAIL missing MATLAB output: $f"; exit 4; }; cp -p "$WIN_WORK/$f" "$WORK/$f"; echo "COPIED MATLAB OUTPUT: $f"; done
echo 'WRAPPER 10 MATLAB: PASS'
