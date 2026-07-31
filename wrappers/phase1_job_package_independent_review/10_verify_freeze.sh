#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/49_0_verify_freeze_phase1_job_package_review.py \
  --review config/phase1_nibi_job_package_independent_review_v1.json

python3 scripts/49_1_validate_phase1_job_package_independent_review.py \
  --review config/phase1_nibi_job_package_independent_review_v1.json

echo "PHASE-1 JOB-PACKAGE INDEPENDENT REVIEW VERIFY/FREEZE: PASS"
