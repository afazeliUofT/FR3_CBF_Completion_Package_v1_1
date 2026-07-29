#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/34_0_ingest_full_topology_export_v4.py \
  --full-zip "$FR3_FULL_ZIP" \
  --review-zip "$FR3_REVIEW_ZIP" \
  --config config/full_topology_ingest_v4.json

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/34_1_validate_full_topology_ingestion.py \
  --config config/full_topology_ingest_v4.json

echo "FULL-TOPOLOGY INGEST/ANALYSIS: PASS"
