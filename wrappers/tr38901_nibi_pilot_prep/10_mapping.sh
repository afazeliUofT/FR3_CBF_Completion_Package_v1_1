#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

STAMP="$(date -u +%Y%m%d_%H%M%S)"
if [[ -d data/real/tr38901_nibi_dlp_pilot_prep ]]; then
  mv data/real/tr38901_nibi_dlp_pilot_prep \
    "data/real/tr38901_nibi_dlp_pilot_prep_before_${STAMP}"
fi
mkdir -p data/real/tr38901_nibi_dlp_pilot_prep \
  results/tr38901_nibi_dlp_pilot_prep/upload

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/31_0_freeze_tr38901_used_subset_mapping.py \
  --config config/tr38901_nibi_dlp_pilot_prep.json

echo
cat data/real/tr38901_nibi_dlp_pilot_prep/TR38901_USED_SUBSET_MAPPING_DECISION.md
echo "WRAPPER 10 USED-SUBSET MAPPING: PASS"
