#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/sector_selective_backoff
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/sector_selective_backoff/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "DECLARED-ENVELOPE SECTOR BACKOFF: FAIL"; echo "exit=$code command=${BASH_COMMAND:-unknown}"; echo "log=$MASTER_LOG"; tail -n 360 "$MASTER_LOG" || true; exit $code' ERR

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1

echo "================================================================="
echo "DECLARED ARRAY/CSI ENVELOPE + SECTOR-SELECTIVE FALLBACK"
echo "================================================================="
echo "Repository: $ROOT"
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, Narval, or MATLAB command will be run."
echo "Measured calibration claim: NONE"
echo "Campaign execution authorization: FALSE"
echo "Expected runtime: several minutes on the reference PC."
echo "Master log: $MASTER_LOG"

for name in 00_preflight 10_run_validate 20_sync_package 30_push; do
  wrapper="wrappers/sector_selective_backoff/${name}.sh"
  wrapper_log="logs/sector_selective_backoff/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/sector_selective_backoff/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/sector_selective_backoff_v1/FR3_SECTOR_SELECTIVE_BACKOFF_REVIEW_v1.zip"

echo
echo "================================================================="
echo "DECLARED-ENVELOPE SECTOR BACKOFF DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Campaign execution authorized: NO"
echo "Next gate: MAP_PRACTICAL_64T64R_OR_HYBRID_ARCHITECTURE_AND_INDEPENDENTLY_REVIEW_PHASE1_CAMPAIGN_BUNDLE"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
