#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

WORK="data/real/tr38901_narval_dlp_pilot_prep"
mkdir -p "$WORK" results/tr38901_narval_dlp_pilot_prep/upload

VENV="/home/afazeli2006/.venvs/fr3-sionna2-2.0.1-cpu"
PYTHONPATH="$ROOT/scripts:$ROOT/src" \
PYTHONDONTWRITEBYTECODE=1 \
"$VENV/bin/python" \
  scripts/31_4_record_sionna_panelarray_api.py \
  --config config/tr38901_narval_dlp_pilot_prep.json

PYTHONPATH="$ROOT/scripts:$ROOT/src" \
PYTHONDONTWRITEBYTECODE=1 \
"$VENV/bin/python" \
  scripts/31_1_audit_sionna_dual_pol_port_order.py \
  --config config/tr38901_narval_dlp_pilot_prep.json

source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/31_5_audit_sionna_incumbent_local_frame.py \
  --config config/tr38901_narval_dlp_pilot_prep.json

echo "LOCAL STEERING/PORT AUDITS: PASS"
