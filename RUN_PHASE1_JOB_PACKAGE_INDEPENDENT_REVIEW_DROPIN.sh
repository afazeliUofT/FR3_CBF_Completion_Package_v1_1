#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/phase1_job_package_independent_review
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/phase1_job_package_independent_review/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "PHASE-1 JOB-PACKAGE INDEPENDENT REVIEW: FAIL"; echo "exit=$code command=${BASH_COMMAND:-unknown}"; tail -n 360 "$LOG" || true; exit $code' ERR

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1

echo "================================================================="
echo "PHASE-1 IMMUTABLE NIBI JOB-PACKAGE INDEPENDENT REVIEW"
echo "================================================================="
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, Narval, MATLAB, channel generation, or campaign run."
echo "Full campaign execution authorization: FALSE"
echo "Master log: $LOG"

for name in \
  00_preflight \
  10_verify_freeze \
  20_status_package \
  30_push
do
  wrapper="wrappers/phase1_job_package_independent_review/${name}.sh"
  wrapper_log="logs/phase1_job_package_independent_review/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/phase1_job_package_independent_review/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/phase1_nibi_job_package_independent_review_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_v1.zip"

echo
echo "================================================================="
echo "PHASE-1 JOB-PACKAGE INDEPENDENT REVIEW DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Verdict: PASS_FOR_NIBI_DEPLOYMENT_SMOKE_PREPARATION_NOT_FULL_CAMPAIGN_EXECUTION"
echo "Full campaign execution authorized: NO"
echo "Nibi submission performed: NO"
echo "Next gate: BUILD_REVIEW_AND_RUN_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
