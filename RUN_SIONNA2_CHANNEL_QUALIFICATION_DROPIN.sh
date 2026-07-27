#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
mkdir -p logs/sionna2_channel_qualification
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/sionna2_channel_qualification/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 240 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/sionna2_channel_qualification")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "CLEAN SIONNA 2.0.1 CHANNEL IMPLEMENTATION QUALIFICATION"
echo "================================================================="
echo "Repository: $REPO_ROOT"
echo "Log: $MASTER_LOG"

WRAPPERS=(
  00_preflight_snapshot
  10_create_environment
  20_run_qualification
  30_package_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/sionna2_channel_qualification/${name}.sh"
  log="logs/sionna2_channel_qualification/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > "logs/sionna2_channel_qualification/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
echo
echo "================================================================="
echo "SIONNA 2.0.1 CHANNEL QUALIFICATION DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Branch URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/tree/e3-first-sector-p452"
echo "Next gate: FROZEN_57_SECTOR_SIONNA2_DLP_RZF_PILOT"
echo "Review files:"
echo "  evidence/sionna2_channel_qualification/"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/sionna2_channel_qualification")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/logs/sionna2_channel_qualification")" >/dev/null 2>&1 || true
fi
if command -v cmd.exe >/dev/null 2>&1; then
  cmd.exe /c start "" "https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT" >/dev/null 2>&1 || true
fi
