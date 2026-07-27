#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
mkdir -p logs/e3_all_site_p452_recovery
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/e3_all_site_p452_recovery/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "RECOVERY DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 180 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/e3_all_site_p452_recovery")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "E3 ALL-SITE P.452 MATLAB TABLE-CONSTRUCTION RECOVERY DROP-IN"
echo "================================================================="
echo "Repository: $REPO_ROOT"
echo "Log: $MASTER_LOG"

WRAPPERS=(
  00_preflight
  10_matlab_retry
  20_validate
  30_package_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/e3_all_site_p452_recovery/${name}.sh"
  log="logs/e3_all_site_p452_recovery/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > "logs/e3_all_site_p452_recovery/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
echo
echo "================================================================="
echo "E3 ALL-SITE P.452 MATLAB RECOVERY DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Branch URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/tree/e3-first-sector-p452"
echo "Next gate: HUMAN_REVIEW_OF_19_SITE_P452_BASIC_LOSS_BEFORE_57_SECTOR_EXPANSION"
echo "Review files:"
echo "  evidence/e3_all_site_p452_basic_loss/work/ALL_SITE_P452_VALIDATION.json"
echo "  evidence/e3_all_site_p452_basic_loss/work/ALL_SITE_P452_INDEPENDENT_REVIEW.json"
echo "  evidence/e3_all_site_p452_basic_loss/work/all_site_loss_summary.csv"
echo "  evidence/e3_all_site_p452_basic_loss/work/p452_all_site_basic_loss.csv"
echo "  evidence/e3_all_site_p452_basic_loss/review/"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/e3_all_site_p452_basic_loss")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/logs/e3_all_site_p452_recovery")" >/dev/null 2>&1 || true
fi
if command -v cmd.exe >/dev/null 2>&1; then
  cmd.exe /c start "" "https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT" >/dev/null 2>&1 || true
fi
