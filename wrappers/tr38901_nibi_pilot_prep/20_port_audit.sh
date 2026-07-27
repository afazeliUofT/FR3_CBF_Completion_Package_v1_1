#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
VENV="/home/afazeli2006/.venvs/fr3-sionna2-2.0.1-cpu"

PYTHONPATH="$ROOT/scripts:$ROOT/src" \
PYTHONDONTWRITEBYTECODE=1 \
"$VENV/bin/python" \
  scripts/31_1_audit_sionna_dual_pol_port_order.py \
  --config config/tr38901_nibi_dlp_pilot_prep.json

echo
cat data/real/tr38901_nibi_dlp_pilot_prep/SIONNA_DUAL_POL_PORT_ORDER_AUDIT.md
echo "WRAPPER 20 SIONNA PORT AUDIT: PASS"
