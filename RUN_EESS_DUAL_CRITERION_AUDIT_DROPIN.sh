#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"; cd "$ROOT"
mkdir -p logs/eess_dual_criterion
STAMP="$(date -u +%Y%m%d_%H%M%S)"; LOG="logs/eess_dual_criterion/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1
trap 'code=$?; echo; echo "EESS DUAL-CRITERION DROP-IN: FAIL"; echo "exit=$code command=$BASH_COMMAND"; tail -n 300 "$LOG" || true; exit $code' ERR
echo "================================================================="
echo "EESS LONG/SHORT-TERM CRITERION CORRECTION AUDIT"
echo "================================================================="
echo "Execution: LOCAL WSL ONLY"; echo "No cluster job will be run."
for name in 00_preflight 10_run_validate 20_sync_package 30_push; do
 echo; echo "=== RUNNING $name ==="
 bash "wrappers/eess_dual_criterion/${name}.sh"
done
COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/eess_dual_criterion_audit_v1/FR3_EESS_DUAL_CRITERION_AUDIT_REVIEW_v1.zip"
echo "================================================================="
echo "EESS DUAL-CRITERION AUDIT DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Next gate: RERUN_LOCAL_CONTROLLERS_WITH_CORRECTED_DUAL_CRITERIA_QMAX70_AND_PATTERN_SENSITIVITY"
echo "================================================================="
if command -v explorer.exe >/dev/null 2>&1; then explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" >/dev/null 2>&1 || true; fi
