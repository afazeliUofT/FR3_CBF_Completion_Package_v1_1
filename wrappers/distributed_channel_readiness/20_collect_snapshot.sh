#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

ARGS=(--config config/distributed_channel_readiness.yaml)
if [[ -n "${FR3_CHANNEL_SOURCE_ROOT:-}" ]]; then
  ARGS+=(--source-root "$FR3_CHANNEL_SOURCE_ROOT")
fi

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/28_2_collect_fr3_channel_snapshot.py \
  "${ARGS[@]}"

echo
cat evidence/fr3_channel_baseline_snapshot/REVIEW_PRIORITY.md
echo
echo "MANUAL REVIEW REQUIRED BEFORE PUBLIC GITHUB PUSH"
echo "Inspect:"
echo "  evidence/fr3_channel_baseline_snapshot/SNAPSHOT_METADATA.json"
echo "  evidence/fr3_channel_baseline_snapshot/SOURCE_INVENTORY.csv"
echo "  evidence/fr3_channel_baseline_snapshot/BINARY_CANDIDATES.csv"
echo "  evidence/fr3_channel_baseline_snapshot/REJECTED_FILES.csv"
echo "  evidence/fr3_channel_baseline_snapshot/source/"
if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$ROOT/evidence/fr3_channel_baseline_snapshot")" \
    >/dev/null 2>&1 || true
fi
read -r -p "After reviewing the snapshot, type exactly 'I REVIEWED THE FR3 CHANNEL SOURCE SNAPSHOT': " CONFIRM
[[ "$CONFIRM" == "I REVIEWED THE FR3 CHANNEL SOURCE SNAPSHOT" ]] || {
  echo "Confirmation not accepted. Nothing was pushed."
  exit 7
}
echo "FR3 CHANNEL SOURCE SNAPSHOT HUMAN CONFIRMATION: PASS"
echo "WRAPPER 20 CHANNEL SOURCE SNAPSHOT: PASS"
