#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)";cd "$ROOT";source .venv/bin/activate;export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
python3 scripts/44_2_build_phase1_campaign_candidate.py --config config/practical_architecture_mapping_v1.json
python3 scripts/44_3_sync_practical_architecture_status.py --config config/practical_architecture_mapping_v1.json
python3 scripts/44_4_build_practical_architecture_review_bundle.py --config config/practical_architecture_mapping_v1.json
bash campaign/phase1_candidate_v1/RUN_PHASE1_CAMPAIGN.sh && { echo 'ERROR: blocked campaign unexpectedly ran';exit 4; } || [[ $? -eq 64 ]]
echo 'PHASE-1 REVIEW CANDIDATE/STATUS: PASS'
