#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/protected_pass_records_phase1
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/protected_pass_records_phase1/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "PROTECTED-PASS RECORD DROP-IN: FAIL"; echo "exit=$code command=${BASH_COMMAND:-unknown}"; tail -n 360 "$LOG" || true; exit $code' ERR

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

echo "================================================================="
echo "FIVE IMMUTABLE PROTECTED-PASS RECORDS + PHASE1 CANDIDATE V2"
echo "================================================================="
echo "Repository: $ROOT"
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, Narval, or MATLAB command will be run."
echo "Campaign execution authorization: FALSE"
echo "Expected runtime: usually under several minutes."
echo "Master log: $LOG"

for name in \
  00_preflight \
  10_generate_validate \
  20_candidate_package \
  30_push
do
  wrapper="wrappers/protected_pass_records/${name}.sh"
  wrapper_log="logs/protected_pass_records_phase1/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/protected_pass_records_phase1/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/protected_pass_records_phase1_v1/FR3_PROTECTED_PASS_RECORDS_PHASE1_REVIEW_v1.zip"
CANDIDATE="$ROOT/campaign/phase1_candidate_v2/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip"

echo
echo "================================================================="
echo "PROTECTED-PASS RECORDS + PHASE1 CANDIDATE DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Candidate: $CANDIDATE"
echo "Candidate SHA-256: $(sha256sum "$CANDIDATE" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Campaign execution authorized: NO"
echo "Next gate: INDEPENDENTLY_REVIEW_COMPLETE_PHASE1_CAMPAIGN_CANDIDATE"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
