#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/dual_criterion_controller
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/dual_criterion_controller/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "DUAL-CRITERION CONTROLLER DROP-IN: FAIL"; echo "exit=$code command=${BASH_COMMAND:-unknown}"; echo "log=$MASTER_LOG"; tail -n 360 "$MASTER_LOG" || true; exit $code' ERR

# Deterministic single-threaded BLAS avoids severe oversubscription on WSL and
# makes the exact-data runtime reproducible.
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1

echo "================================================================="
echo "CORRECTED EESS DUAL-CRITERION CONTROLLER REEVALUATION"
echo "================================================================="
echo "Repository: $ROOT"
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, or Narval command will be run."
echo "Expected runtime: approximately 3-5 minutes on the reference PC."
echo "Master log: $MASTER_LOG"

for name in 00_preflight 10_run_validate 20_sync_package 30_push; do
  wrapper="wrappers/dual_criterion_controller/${name}.sh"
  wrapper_log="logs/dual_criterion_controller/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/dual_criterion_controller/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/dual_criterion_controller_reevaluation_v1/FR3_DUAL_CRITERION_CONTROLLER_REEVALUATION_REVIEW_v1.zip"

echo
echo "================================================================="
echo "DUAL-CRITERION CONTROLLER REEVALUATION DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Next gate: CALIBRATE_ARRAY_CSI_NULL_DEPTH_AND_PHYSICAL_UNCERTAINTY_THEN_FREEZE_PHASED_CAMPAIGN"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
