#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: expected branch e3-first-sector-p452"
  exit 2
}
git merge-base --is-ancestor \
  f26af9f3ff595f6b6ae9b468c79683e53bc8b450 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

for path in \
  campaign/phase1_candidate_v2/CAMPAIGN_METADATA.json \
  campaign/phase1_candidate_v2/BUNDLE_MANIFEST.sha256 \
  campaign/phase1_candidate_v2/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip \
  campaign/phase1_candidate_v2/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip.sha256 \
  campaign/protected_pass_records_v1/PASS_RECORD_INDEX.json \
  config/phase1_campaign_contract_v3.json
do
  [[ -f "$path" ]] || {
    echo "ERROR: required candidate-v2 input is missing: $path"
    exit 4
  }
  echo "OK      $path"
done

CANDIDATE_SHA="$(
  sha256sum \
    campaign/phase1_candidate_v2/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip \
  | awk '{print $1}'
)"
[[ "$CANDIDATE_SHA" == \
  "cb4d121372aa572e1163b92d013b87a66d2816180b071a941355c69553e80498" ]]
echo "CANDIDATE-V2 IMMUTABLE SHA PRECHECK: PASS"

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_phase1_candidate_v3_contract.py

echo "PHASE-1 CANDIDATE V3 PREFLIGHT: PASS"
