#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/48_2_run_phase1_exact_local_smoke.py \
  --config config/phase1_nibi_job_package_builder_v1.json

python3 scripts/48_3_sync_phase1_nibi_job_package_status.py \
  --config config/phase1_nibi_job_package_builder_v1.json

python3 scripts/48_4_build_phase1_nibi_job_package_review_bundle.py \
  --config config/phase1_nibi_job_package_builder_v1.json

for lock in \
  campaign/phase1_nibi_job_package_v1/RUN_PHASE1_NIBI_CAMPAIGN.sh \
  campaign/phase1_nibi_job_package_v1/SUBMIT_PHASE1_LOCKED.sh \
  campaign/phase1_nibi_job_package_v1/MERGE_PHASE1_LOCKED.sh
 do
  if bash "$lock"; then
    LOCK_EXIT=0
  else
    LOCK_EXIT=$?
  fi
  [[ "$LOCK_EXIT" -eq 64 ]] || {
    echo "ERROR: execution lock $lock returned $LOCK_EXIT"
    exit 6
  }
done

echo "PHASE-1 NIBI JOB-PACKAGE EXECUTION LOCKS: PASS"
echo "PHASE-1 NIBI JOB-PACKAGE SMOKE/STATUS/PACKAGE: PASS"
