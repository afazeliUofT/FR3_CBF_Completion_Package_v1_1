#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
VENV="$HOME/.venvs/fr3-sionna2-2.0.1-cpu"
mkdir -p data/real/sionna2_topology_readiness

PYTHONPATH="$ROOT/scripts:$ROOT/src" \
PYTHONDONTWRITEBYTECODE=1 \
"$VENV/bin/python" \
  scripts/30_0_audit_sionna2_delay_and_source.py \
  --config config/sionna2_topology_readiness.json

echo
python3 -m json.tool \
  data/real/sionna2_topology_readiness/SIONNA2_DELAY_AND_SOURCE_AUDIT.json
echo "WRAPPER 10 DELAY/SOURCE AUDIT: PASS"
