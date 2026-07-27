#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
  cat <<'USAGE'
Usage:
  REVIEWER_NAME="Ali Fazeli" \
    bash RUN_E3_FIRST_SECTOR_P452_DROPIN.sh --confirm-terrain-reviewed

Optional environment overrides:
  MATLAB_EXE=/mnt/c/Program\ Files/MATLAB/R2026a/bin/matlab.exe
  P452_WINDOWS_ROOT=/mnt/c/Users/alifa/FR3_P452_Validation_v18_R2026a
USAGE
}

if [[ "${1:-}" != "--confirm-terrain-reviewed" ]]; then
  usage
  exit 2
fi

: "${REVIEWER_NAME:?Set REVIEWER_NAME, e.g. REVIEWER_NAME='Ali Fazeli'}"

if [[ -z "${VIRTUAL_ENV:-}" || "$VIRTUAL_ENV" != "$ROOT/.venv" ]]; then
  echo "FAIL: activate this repository's virtual environment first:"
  echo "  source .venv/bin/activate"
  exit 2
fi

export CONFIRM_TERRAIN_REVIEWED=1
STAMP="$(date -u +%Y%m%d_%H%M%S)"

# Preserve every prior run before creating the current output folders.
for dir in \
  data/real/e3_first_sector_p452 \
  results/e3_first_sector_p452_review \
  logs/e3_first_sector_p452
do
  if [[ -d "$dir" ]]; then
    mv "$dir" "${dir}_before_${STAMP}"
    echo "Archived prior run: ${dir}_before_${STAMP}"
  fi
done

LOG_DIR="$ROOT/logs/e3_first_sector_p452"
mkdir -p "$LOG_DIR"

{
  echo "RUN_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "REPOSITORY_ROOT=$ROOT"
  echo "GIT_BRANCH=$(git branch --show-current 2>/dev/null || true)"
  echo "GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || true)"
  echo "PYTHON=$(python3 --version 2>&1)"
  echo "PYTHON_EXECUTABLE=$(command -v python3)"
  echo "VIRTUAL_ENV=$VIRTUAL_ENV"
  echo "MATLAB_EXE=${MATLAB_EXE:-/mnt/c/Program Files/MATLAB/R2026a/bin/matlab.exe}"
  echo "P452_WINDOWS_ROOT=${P452_WINDOWS_ROOT:-/mnt/c/Users/alifa/FR3_P452_Validation_v18_R2026a}"
  echo
  git status -sb 2>/dev/null || true
} | tee "$LOG_DIR/RUN_CONTEXT.txt"

python3 -m pip freeze > "$LOG_DIR/python_environment.txt"

run_step() {
  local name="$1"
  local script="$2"
  local log="$LOG_DIR/${name}.log"

  echo
  echo "########################################################################"
  echo "RUNNING $name -> $script"
  echo "LOG: $log"
  echo "########################################################################"

  set +e
  bash "$script" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  set -e

  printf '%s\n' "$code" > "$LOG_DIR/${name}.exitcode"

  if [[ $code -ne 0 ]]; then
    echo
    echo "DROP-IN FAILED AT $name (exit $code)"
    echo "LAST 160 LOG LINES:"
    tail -n 160 "$log"
    echo
    echo "FAILURE EVIDENCE FOLDER: $LOG_DIR"
    if command -v explorer.exe >/dev/null 2>&1; then
      explorer.exe "$(wslpath -w "$LOG_DIR")" >/dev/null 2>&1 || true
    fi
    exit "$code"
  fi

  echo "$name: PASS"
}

set -e
run_step 00_prepare wrappers/e3_first_sector_p452/00_prepare.sh
run_step 10_matlab wrappers/e3_first_sector_p452/10_matlab.sh
run_step 20_postprocess_validate wrappers/e3_first_sector_p452/20_postprocess_validate.sh
run_step 30_package_review wrappers/e3_first_sector_p452/30_package_review.sh

find scripts tests src -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests src -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

printf '\n=======================================================================\n'
printf 'E3 FIRST-SECTOR P.452 DROP-IN: PASS\n'
printf '=======================================================================\n'
cat results/e3_first_sector_p452_review/RUN_SUMMARY.txt

echo
echo "WRAPPER EXIT CODES:"
for code_file in "$LOG_DIR"/*.exitcode; do
  [[ -f "$code_file" ]] || continue
  printf '  %-34s %s\n' "$(basename "$code_file")" "$(cat "$code_file")"
done

echo
echo "UPLOAD THESE TWO FILES:"
find results/e3_first_sector_p452_review/review_upload \
  -maxdepth 1 -type f -printf '  %p\n' | sort

echo
echo "ALSO PASTE THIS FINAL CONSOLE OUTPUT."
echo "All human-review files are listed in:"
echo "  results/e3_first_sector_p452_review/REVIEW_FILES.txt"
echo "All folders and the HTML review index were opened automatically when Windows Explorer was available."
