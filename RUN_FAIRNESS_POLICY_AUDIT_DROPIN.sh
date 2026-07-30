#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/fairness_policy_audit
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/fairness_policy_audit/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "FAIRNESS POLICY AUDIT: FAIL"; echo "exit=$code command=$BASH_COMMAND"; tail -n 300 "$LOG" || true; exit $code' ERR

echo "================================================================="
echo "FR3 FAIRNESS POLICY AUDIT BEFORE CONTROLLER IMPLEMENTATION"
echo "================================================================="
echo "Repository: $ROOT"
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, or Narval command will be run."
echo "The previous local-controller v1 package must not be run."

for name in 00_preflight 10_run_validate 20_sync_package 30_push; do
  wrapper="wrappers/fairness_policy_audit/${name}.sh"
  wrapper_log="logs/fairness_policy_audit/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > \
    "logs/fairness_policy_audit/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/fairness_policy_audit_v1/FR3_FAIRNESS_POLICY_AUDIT_REVIEW_v1.zip"

echo
echo "================================================================="
echo "FAIRNESS POLICY AUDIT DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Next gate: IMPLEMENT_CONSTRAINED_PROPORTIONAL_FAIR_STATIC_MYOPIC_AND_PREDICTIVE_CONTROLLERS"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" \
    >/dev/null 2>&1 || true
fi
