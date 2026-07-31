#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/phase1_candidate_v3
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/phase1_candidate_v3/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "PHASE-1 CANDIDATE V3 REPAIR: FAIL"; echo "exit=$code command=${BASH_COMMAND:-unknown}"; tail -n 360 "$LOG" || true; exit $code' ERR

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

echo "================================================================="
echo "PHASE-1 CANDIDATE V3 — INDEPENDENT REVIEW ROUND-1 REPAIR"
echo "================================================================="
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, Narval, MATLAB, channel generation, or campaign run."
echo "Campaign execution authorization: FALSE"
echo "Master log: $LOG"

for name in \
  00_preflight \
  10_build_validate \
  20_package_status \
  30_push
do
  wrapper="wrappers/phase1_candidate_v3/${name}.sh"
  wrapper_log="logs/phase1_candidate_v3/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/phase1_candidate_v3/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
CANDIDATE="$ROOT/campaign/phase1_candidate_v3/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip"
REVIEW="$ROOT/evidence/phase1_candidate_v3_review/FR3_PHASE1_CANDIDATE_V3_REVIEW_PREP_v1.zip"

echo
echo "================================================================="
echo "PHASE-1 CANDIDATE V3 REPAIR DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Candidate: $CANDIDATE"
echo "Candidate SHA-256: $(sha256sum "$CANDIDATE" | awk '{print $1}')"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Round-1 verdict: REQUIRES_REVISION"
echo "Round-2 status: PENDING"
echo "Campaign execution authorized: NO"
echo "Nibi submission performed: NO"
echo "Next gate: INDEPENDENTLY_REVIEW_PHASE1_CAMPAIGN_CANDIDATE_V3"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
