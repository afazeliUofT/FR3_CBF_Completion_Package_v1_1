#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

find scripts tests src \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) \
  -delete 2>/dev/null || true
find scripts tests src \
  -type d -name '__pycache__' -prune \
  -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

STAGE=(
  config/phase1_campaign_contract_v3.json
  docs/PHASE1_INDEPENDENT_REVIEW_ROUND1.md
  docs/PHASE1_STATISTICAL_ANALYSIS_PLAN_V3.md
  docs/PHASE1_METHOD_INFORMATION_CONTRACT_V3.md
  scripts/46_0_build_phase1_candidate_v3.py
  scripts/46_1_validate_phase1_candidate_v3.py
  scripts/46_2_sync_phase1_candidate_review_status.py
  scripts/46_3_build_phase1_candidate_v3_review_bundle.py
  tests/test_phase1_candidate_v3_contract.py
  wrappers/phase1_candidate_v3
  RUN_PHASE1_CANDIDATE_V3_REPAIR_DROPIN.sh
  README_PHASE1_CANDIDATE_V3_REPAIR.md
  PHASE1_CANDIDATE_V3_REPAIR_MANIFEST.sha256
  PHASE1_CANDIDATE_V3_REPAIR_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  campaign/phase1_candidate_v3
  evidence/phase1_candidate_v3_review
)

git add -- "${STAGE[@]}"
git diff --cached --check

(
  cd campaign/phase1_candidate_v3
  sha256sum -c BUNDLE_MANIFEST.sha256
  sha256sum -c \
    FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip.sha256
  unzip -t \
    FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip \
    >/dev/null
)
(
  cd evidence/phase1_candidate_v3_review
  sha256sum -c EVIDENCE_MANIFEST.sha256
  sha256sum -c \
    FR3_PHASE1_CANDIDATE_V3_REVIEW_PREP_v1.zip.sha256
  unzip -t \
    FR3_PHASE1_CANDIDATE_V3_REVIEW_PREP_v1.zip \
    >/dev/null
)

mapfile -t LARGE_FILES < <(
  find \
    campaign/phase1_candidate_v3 \
    evidence/phase1_candidate_v3_review \
    -type f -size +95M -print
)
[[ "${#LARGE_FILES[@]}" -eq 0 ]] || {
  echo "ERROR: stage contains files over 95 MiB:"
  printf '  %s\n' "${LARGE_FILES[@]}"
  exit 6
}

git commit -m \
  "Repair phase1 campaign contract after independent review round1"
git push

COMMIT="$(git rev-parse HEAD)"
REMOTE="$(
  git ls-remote --heads origin e3-first-sector-p452 \
  | awk '{print $1}'
)"
[[ "$REMOTE" == "$COMMIT" ]] || {
  echo "ERROR: remote branch does not equal local commit"
  exit 7
}

CANDIDATE="campaign/phase1_candidate_v3/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip"
REVIEW="evidence/phase1_candidate_v3_review/FR3_PHASE1_CANDIDATE_V3_REVIEW_PREP_v1.zip"

echo "PHASE-1 CANDIDATE V3 PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Candidate: $ROOT/$CANDIDATE"
echo "Candidate SHA-256: $(sha256sum "$CANDIDATE" | awk '{print $1}')"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Round-1 verdict: REQUIRES_REVISION"
echo "Round-2 status: PENDING"
echo "Campaign execution authorized: NO"
echo "Next gate: INDEPENDENTLY_REVIEW_PHASE1_CAMPAIGN_CANDIDATE_V3"
