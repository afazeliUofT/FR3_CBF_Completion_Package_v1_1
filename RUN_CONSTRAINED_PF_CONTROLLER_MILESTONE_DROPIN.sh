#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/constrained_pf_controller
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/constrained_pf_controller/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "CONSTRAINED PF CONTROLLER MILESTONE: FAIL"; echo "exit=$code command=$BASH_COMMAND"; tail -n 360 "$LOG" || true; exit $code' ERR

echo "================================================================="
echo "CONSTRAINED PROPORTIONAL-FAIR SAFETY CONTROLLER MILESTONE"
echo "================================================================="
echo "Repository: $ROOT"
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, or Narval command will be run."
echo "Network sum rate is secondary, not the primary objective."
echo "Master log: $LOG"

for name in 00_preflight 10_run_validate 20_sync_package 30_push; do
  wrapper="wrappers/constrained_pf_controller/${name}.sh"
  wrapper_log="logs/constrained_pf_controller/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/constrained_pf_controller/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/constrained_pf_controller_milestone_v1/FR3_CONSTRAINED_PF_CONTROLLER_MILESTONE_REVIEW_v1.zip"

echo
echo "================================================================="
echo "CONSTRAINED PF CONTROLLER MILESTONE DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Next gate: FORMALIZE_DELAYED_SAFETY_GUARANTEE_ADD_VIRTUAL_QUEUE_AND_UNCERTAINTY"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
