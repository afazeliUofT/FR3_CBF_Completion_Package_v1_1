#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/49_2_sync_phase1_job_package_review_status.py \
  --review config/phase1_nibi_job_package_independent_review_v1.json

python3 scripts/49_3_build_phase1_job_package_review_freeze_bundle.py

echo
python3 -m json.tool \
  evidence/phase1_nibi_job_package_independent_review_v1/PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_VERDICT.json

echo "PHASE-1 JOB-PACKAGE INDEPENDENT REVIEW STATUS/PACKAGE: PASS"
