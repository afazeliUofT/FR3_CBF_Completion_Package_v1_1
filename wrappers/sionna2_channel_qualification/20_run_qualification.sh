#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

WORK="data/real/sionna2_channel_qualification"
VENV="$(cat "$WORK/VENV_PATH.txt")"
[[ -x "$VENV/bin/python" ]] || {
  echo "ERROR: qualified virtual environment is missing"
  exit 2
}

PYTHONPATH="$ROOT/scripts:$ROOT/src" \
PYTHONDONTWRITEBYTECODE=1 \
"$VENV/bin/python" \
  scripts/29_1_run_sionna2_api_qualification.py \
  --config config/sionna2_channel_qualification.json

PYTHONPATH="$ROOT/scripts:$ROOT/src" \
PYTHONDONTWRITEBYTECODE=1 \
"$VENV/bin/python" \
  scripts/29_2_validate_sionna2_qualification.py \
  --config config/sionna2_channel_qualification.json

source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/29_3_freeze_channel_implementation_decision.py \
  --config config/sionna2_channel_qualification.json

echo
cat "$WORK/SIONNA2_CHANNEL_QUALIFICATION_VALIDATION.md"
echo
cat "$WORK/CHANNEL_IMPLEMENTATION_DECISION.md"
echo "WRAPPER 20 API QUALIFICATION/DECISION: PASS"
