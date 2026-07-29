#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/34_2_sync_full_topology_status.py \
  --config config/full_topology_ingest_v4.json

python3 scripts/34_3_build_full_topology_review_bundle.py \
  --config config/full_topology_ingest_v4.json

echo
python3 -m json.tool \
  evidence/full_topology_export_18696267_validated_v4/FULL_TOPOLOGY_GATE_DECISION.json
echo
python3 -m json.tool \
  evidence/full_topology_export_18696267_validated_v4/FULL_TOPOLOGY_SCIENTIFIC_METRICS.json \
  | tail -n 120

echo "FULL-TOPOLOGY STATUS/PACKAGE: PASS"
