#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/45_2_build_complete_phase1_candidate.py \
  --config config/protected_pass_records_phase1_v1.json

python3 scripts/45_3_sync_protected_pass_status.py \
  --config config/protected_pass_records_phase1_v1.json

python3 scripts/45_4_build_protected_pass_review_bundle.py \
  --config config/protected_pass_records_phase1_v1.json

set +e
bash campaign/phase1_candidate_v2/RUN_PHASE1_CAMPAIGN.sh
LOCK_EXIT=$?
set -e
[[ "$LOCK_EXIT" -eq 64 ]] || {
  echo "ERROR: execution lock returned $LOCK_EXIT instead of 64"
  exit 5
}
echo "COMPLETE PHASE-1 EXECUTION LOCK: PASS"
echo "PROTECTED-PASS CANDIDATE/STATUS PACKAGE: PASS"
