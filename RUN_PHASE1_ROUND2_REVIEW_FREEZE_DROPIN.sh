#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/phase1_round2_review
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/phase1_round2_review/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "PHASE-1 ROUND-2 REVIEW FREEZE: FAIL"; echo "exit=$code command=${BASH_COMMAND:-unknown}"; tail -n 320 "$LOG" || true; exit $code' ERR

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1

echo "================================================================="
echo "PHASE-1 CANDIDATE V3 — INDEPENDENT REVIEW ROUND-2 FREEZE"
echo "================================================================="
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, Narval, MATLAB, channel generation, or campaign run."
echo "Campaign execution authorization: FALSE"
echo "Master log: $LOG"

for name in \
  00_preflight \
  10_verify_freeze \
  20_status_package \
  30_push
do
  wrapper="wrappers/phase1_round2_review/${name}.sh"
  wrapper_log="logs/phase1_round2_review/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/phase1_round2_review/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/phase1_candidate_v3_round2_review/FR3_PHASE1_CANDIDATE_V3_ROUND2_REVIEW_v1.zip"

echo
echo "================================================================="
echo "PHASE-1 ROUND-2 REVIEW FREEZE DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Verdict: PASS_FOR_IMMUTABLE_JOB_PACKAGE_PREPARATION_NOT_EXECUTION"
echo "Campaign execution authorized: NO"
echo "Nibi submission performed: NO"
echo "Next gate: BUILD_AND_INDEPENDENTLY_REVIEW_IMMUTABLE_PHASE1_NIBI_JOB_PACKAGE"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
