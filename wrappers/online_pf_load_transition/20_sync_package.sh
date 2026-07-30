#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/39_2_sync_online_pf_status.py \
  --config config/online_pf_load_transition_v1.json

python3 scripts/39_3_build_online_pf_review_bundle.py \
  --config config/online_pf_load_transition_v1.json

echo
python3 -m json.tool \
  evidence/online_pf_load_transition_v1/ONLINE_PF_LOAD_TRANSITION_GATE_DECISION.json
echo
python3 -m json.tool \
  results/online_pf_load_transition_v1/ONLINE_PF_LOAD_TRANSITION_AUDIT.json \
  | tail -n 180

echo "ONLINE PF LOAD-TRANSITION STATUS/PACKAGE: PASS"
