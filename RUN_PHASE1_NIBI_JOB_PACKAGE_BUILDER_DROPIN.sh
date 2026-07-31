#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/phase1_nibi_job_package
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/phase1_nibi_job_package/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "PHASE-1 NIBI JOB-PACKAGE BUILDER: FAIL"; echo "exit=$code command=${BASH_COMMAND:-unknown}"; tail -n 420 "$LOG" || true; exit $code' ERR

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
export MKL_NUM_THREADS=8
export NUMEXPR_NUM_THREADS=8

echo "================================================================="
echo "IMMUTABLE PHASE-1 NIBI JOB-ARRAY PACKAGE BUILDER"
echo "================================================================="
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, Narval, MATLAB, or new channel generation."
echo "An exact local slot-0 all-eight-method smoke will run."
echo "Campaign execution authorization: FALSE"
echo "Master log: $LOG"

for name in \
  00_preflight \
  10_build_validate \
  20_smoke_status_package \
  30_push
 do
  wrapper="wrappers/phase1_nibi_job_package/${name}.sh"
  wrapper_log="logs/phase1_nibi_job_package/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/phase1_nibi_job_package/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
PACKAGE="$ROOT/campaign/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip"
REVIEW="$ROOT/evidence/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_REVIEW_v1.zip"

echo
echo "================================================================="
echo "PHASE-1 NIBI JOB-PACKAGE BUILDER DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Package ID: $(cat "$ROOT/campaign/phase1_nibi_job_package_v1/PACKAGE_ID.txt")"
echo "Job package: $PACKAGE"
echo "Job package SHA-256: $(sha256sum "$PACKAGE" | awk '{print $1}')"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Campaign execution authorized: NO"
echo "Nibi submission performed: NO"
echo "Next gate: INDEPENDENTLY_REVIEW_IMMUTABLE_PHASE1_NIBI_JOB_PACKAGE"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
