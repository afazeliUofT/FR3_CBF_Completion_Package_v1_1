#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/phase1_nibi_deployment_smoke
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/phase1_nibi_deployment_smoke/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "PHASE-1 NIBI DEPLOYMENT SMOKE DROP-IN: FAIL"; echo "exit=$code command=${BASH_COMMAND:-unknown}"; tail -n 420 "$LOG" || true; exit $code' ERR

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
export MKL_NUM_THREADS=8
export NUMEXPR_NUM_THREADS=8

echo "================================================================="
echo "REVIEWED NONCAMPAIGN PHASE-1 NIBI DEPLOYMENT SMOKE"
echo "================================================================="
echo "Local stages: build, validate, commit, push."
echo "Remote stage: exactly one excluded Nibi H100 job, seed 43999."
echo "Confirmatory seeds 44000--44029: NOT USED."
echo "Full campaign and merge authorization: FALSE."
echo "Master log: $LOG"

for name in \
  00_preflight \
  10_build_validate \
  20_status_package_push \
  30_execute_nibi_smoke
do
  wrapper="wrappers/phase1_nibi_deployment_smoke/${name}.sh"
  wrapper_log="logs/phase1_nibi_deployment_smoke/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/phase1_nibi_deployment_smoke/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
SMOKE="campaign/phase1_nibi_deployment_smoke_v1/FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1.zip"
REVIEW="evidence/phase1_nibi_deployment_smoke_prep_v1/FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_PREP_REVIEW_v1.zip"

echo
echo "================================================================="
echo "PHASE-1 NIBI DEPLOYMENT SMOKE DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Smoke ZIP SHA-256: $(sha256sum "$SMOKE" | awk '{print $1}')"
echo "Smoke-prep review SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Smoke seed: 43999"
echo "Confirmatory analysis included: NO"
echo "Full campaign execution authorized: NO"
echo "Next gate: INDEPENDENTLY_REVIEW_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_RETURN"
echo "================================================================="
