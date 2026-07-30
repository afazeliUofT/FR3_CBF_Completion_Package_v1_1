#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/39_0_run_online_pf_load_transition.py \
  --config config/online_pf_load_transition_v1.json

python3 scripts/39_1_validate_online_pf_load_transition.py \
  --config config/online_pf_load_transition_v1.json

echo "ONLINE PF LOAD-TRANSITION RUN/VALIDATION: PASS"
