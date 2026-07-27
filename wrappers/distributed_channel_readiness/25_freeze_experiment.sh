#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/28_3_freeze_standards_experiment.py \
  --config config/distributed_channel_readiness.yaml

echo
cat data/real/distributed_channel_readiness/STANDARDS_ALIGNED_DLP_RZF_EXPERIMENT_SPEC.md
echo "WRAPPER 25 EXPERIMENT FREEZE: PASS"
