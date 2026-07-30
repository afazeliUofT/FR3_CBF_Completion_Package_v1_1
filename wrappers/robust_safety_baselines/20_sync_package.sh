#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/38_2_sync_robust_safety_status.py \
  --config config/robust_safety_baselines_v1.json

python3 scripts/38_3_build_robust_safety_review_bundle.py \
  --config config/robust_safety_baselines_v1.json

echo
python3 -m json.tool \
  evidence/robust_safety_baselines_v1/ROBUST_SAFETY_GATE_DECISION.json
echo
python3 -m json.tool \
  results/robust_safety_baselines_v1/ROBUST_SAFETY_BASELINES_AUDIT.json \
  | tail -n 180

echo "ROBUST DELAYED SAFETY STATUS/PACKAGE: PASS"
