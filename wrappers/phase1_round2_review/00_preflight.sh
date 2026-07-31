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
  be9053dd18deaeef6ab87597e706ab45092ea8cf HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

for path in \
  campaign/phase1_candidate_v3/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip \
  campaign/phase1_candidate_v3/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip.sha256 \
  campaign/phase1_candidate_v3/BUNDLE_MANIFEST.sha256 \
  campaign/phase1_candidate_v3/PHASE1_CAMPAIGN_CONTRACT_V3.json \
  evidence/phase1_candidate_v3_review/FR3_PHASE1_CANDIDATE_V3_REVIEW_PREP_v1.zip
do
  [[ -f "$path" ]] || {
    echo "ERROR: required candidate-v3 review input is missing: $path"
    exit 4
  }
  echo "OK      $path"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_phase1_round2_review_freeze.py

echo "PHASE-1 ROUND-2 REVIEW PREFLIGHT: PASS"
