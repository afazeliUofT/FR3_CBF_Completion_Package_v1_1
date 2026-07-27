#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/31_2_build_narval_dlp_pilot_bundle.py \
  --config config/tr38901_narval_dlp_pilot_prep.json

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/31_6_validate_narval_bundle_source.py \
  --config config/tr38901_narval_dlp_pilot_prep.json

echo "NARVAL BUNDLE BUILD/VALIDATION: PASS"
