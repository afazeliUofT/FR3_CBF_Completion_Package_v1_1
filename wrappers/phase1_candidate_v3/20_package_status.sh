#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/46_2_sync_phase1_candidate_review_status.py \
  --contract config/phase1_campaign_contract_v3.json

python3 scripts/46_3_build_phase1_candidate_v3_review_bundle.py \
  --contract config/phase1_campaign_contract_v3.json

if bash campaign/phase1_candidate_v3/RUN_PHASE1_CAMPAIGN.sh; then
  LOCK_EXIT=0
else
  LOCK_EXIT=$?
fi
[[ "$LOCK_EXIT" -eq 64 ]] || {
  echo "ERROR: candidate-v3 execution lock returned $LOCK_EXIT"
  exit 5
}
echo "PHASE-1 CANDIDATE V3 EXECUTION LOCK: PASS"
echo "PHASE-1 CANDIDATE V3 PACKAGE/STATUS: PASS"
