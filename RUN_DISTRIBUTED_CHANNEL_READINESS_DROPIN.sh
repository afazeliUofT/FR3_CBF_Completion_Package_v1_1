#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p logs/distributed_channel_readiness
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/distributed_channel_readiness/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 220 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/distributed_channel_readiness")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "DISTRIBUTED ARCHITECTURE REVIEW + FR3 CHANNEL READINESS DROP-IN"
echo "================================================================="
echo "Repository: $REPO_ROOT"
echo "Log: $MASTER_LOG"
echo "Channel source root: ${FR3_CHANNEL_SOURCE_ROOT:-default from config}"

WRAPPERS=(
  00_preflight
  10_review_repair
  20_collect_snapshot
  25_freeze_experiment
  30_package_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/distributed_channel_readiness/${name}.sh"
  log="logs/distributed_channel_readiness/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > "logs/distributed_channel_readiness/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
echo
echo "================================================================="
echo "DISTRIBUTED CHANNEL READINESS DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Branch URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/tree/e3-first-sector-p452"
echo "Next gate: CODE_LEVEL_REVIEW_OF_EXISTING_CHANNEL_BASELINE"
echo "Review files:"
echo "  evidence/distributed_channel_readiness/"
echo "  evidence/fr3_channel_baseline_snapshot/"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/distributed_channel_readiness")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/fr3_channel_baseline_snapshot")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/logs/distributed_channel_readiness")" >/dev/null 2>&1 || true
fi
if command -v cmd.exe >/dev/null 2>&1; then
  cmd.exe /c start "" "https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT" >/dev/null 2>&1 || true
fi
