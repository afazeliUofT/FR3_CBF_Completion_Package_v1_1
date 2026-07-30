#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/online_pf_load_transition
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/online_pf_load_transition/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "ONLINE PF LOAD-TRANSITION MILESTONE: FAIL"; echo "exit=$code command=$BASH_COMMAND"; tail -n 360 "$LOG" || true; exit $code' ERR

echo "================================================================="
echo "ONLINE MOVING-AVERAGE PF + USER ARRIVALS/DEPARTURES"
echo "================================================================="
echo "Repository: $ROOT"
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, or Narval command will be run."
echo "Network sum rate remains secondary."
echo "Master log: $LOG"

for name in 00_preflight 10_run_validate 20_sync_package 30_push; do
  wrapper="wrappers/online_pf_load_transition/${name}.sh"
  wrapper_log="logs/online_pf_load_transition/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/online_pf_load_transition/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/online_pf_load_transition_v1/FR3_ONLINE_PF_LOAD_TRANSITION_REVIEW_v1.zip"

echo
echo "================================================================="
echo "ONLINE PF LOAD-TRANSITION DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Next gate: CALIBRATE_UNCERTAINTY_AND_PREPARE_MULTI_SEED_MULTI_PASS_CAMPAIGN"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
