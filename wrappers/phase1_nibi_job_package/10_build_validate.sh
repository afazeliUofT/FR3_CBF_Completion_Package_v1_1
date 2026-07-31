#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/48_0_build_phase1_nibi_job_package.py \
  --config config/phase1_nibi_job_package_builder_v1.json

python3 scripts/48_1_validate_phase1_nibi_job_package.py \
  --config config/phase1_nibi_job_package_builder_v1.json

echo "PHASE-1 NIBI JOB-PACKAGE BUILD/VALIDATION: PASS"
