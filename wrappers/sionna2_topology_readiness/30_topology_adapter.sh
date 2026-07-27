#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/30_1_prepare_custom_57_sector_topology.py \
  --config config/sionna2_topology_readiness.json

if [[ -f data/real/sionna2_topology_readiness/CUSTOM_TOPOLOGY_ADAPTER_SKIPPED.json ]]; then
  echo "CUSTOM TOPOLOGY PILOT: SKIPPED DUE TO DELAY SCIENTIFIC STOP"
else
  VENV="$HOME/.venvs/fr3-sionna2-2.0.1-cpu"
  PYTHONPATH="$ROOT/scripts:$ROOT/src" \
  PYTHONDONTWRITEBYTECODE=1 \
  "$VENV/bin/python" \
    scripts/30_2_run_custom_57_sector_sionna_pilot.py \
    --config config/sionna2_topology_readiness.json
fi

echo "WRAPPER 30 TOPOLOGY ADAPTER: PASS"
