#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"; cd "$ROOT"
mkdir -p logs/physical_impairment_sensitivity
STAMP="$(date -u +%Y%m%d_%H%M%S)"; LOG="logs/physical_impairment_sensitivity/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1
trap 'code=$?; echo; echo "PHYSICAL IMPAIRMENT SENSITIVITY DROP-IN: FAIL"; echo "exit=$code command=${BASH_COMMAND:-unknown}"; tail -n 360 "$LOG" || true; exit $code' ERR
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1
echo "================================================================="
echo "PRACTICAL NULL-DEPTH / ARRAY-CSI SENSITIVITY AUDIT"
echo "================================================================="
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, or Narval command will be run."
echo "Expected runtime: several minutes on the reference PC."
for name in 00_preflight 10_run_validate 20_sync_package 30_push; do
  wrapper="wrappers/physical_impairment_sensitivity/${name}.sh"; wrapper_log="logs/physical_impairment_sensitivity/${name}.log"
  echo; echo "=== RUNNING $name ==="
  set +e; set -o pipefail; bash "$wrapper" 2>&1 | tee "$wrapper_log"; code=${PIPESTATUS[0]}; set +o pipefail; set -e
  printf '%s\n' "$code" > "logs/physical_impairment_sensitivity/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"; [[ "$code" -eq 0 ]] || exit "$code"
done
COMMIT="$(git rev-parse HEAD)"; REVIEW="$ROOT/evidence/physical_impairment_sensitivity_v1/FR3_PHYSICAL_IMPAIRMENT_SENSITIVITY_REVIEW_v1.zip"
echo "================================================================="
echo "PHYSICAL IMPAIRMENT SENSITIVITY DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Next gate: ACQUIRE_OR_DECLARE_ARRAY_CSI_CALIBRATION_ENVELOPE_AND_IMPLEMENT_NULL_FLOOR_AWARE_SECTOR_BACKOFF"
echo "================================================================="
if command -v explorer.exe >/dev/null 2>&1; then explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" >/dev/null 2>&1 || true; fi
