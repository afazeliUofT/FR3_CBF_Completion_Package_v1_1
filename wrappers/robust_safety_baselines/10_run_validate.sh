#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/38_0_run_robust_safety_baselines.py \
  --config config/robust_safety_baselines_v1.json

python3 scripts/38_1_validate_robust_safety_baselines.py \
  --config config/robust_safety_baselines_v1.json

echo "ROBUST DELAYED SAFETY RUN/VALIDATION: PASS"
