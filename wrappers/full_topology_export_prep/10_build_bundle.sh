#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src:$ROOT/scripts" \
python3 scripts/33_0_build_full_topology_export_bundle.py \
  --review-zip "$FR3_REVIEW_ZIP" \
  --config config/full_topology_export_prep.json

echo "FULL-TOPOLOGY EXPORT PREP BUILD: PASS"
