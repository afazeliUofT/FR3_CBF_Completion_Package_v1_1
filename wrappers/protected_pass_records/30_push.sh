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
  config/protected_pass_records_phase1_v1.json
  src/fr3_cbf/protected_pass_records.py
  scripts/45_0_generate_protected_pass_records.py
  scripts/45_1_validate_protected_pass_records.py
  scripts/45_2_build_complete_phase1_candidate.py
  scripts/45_3_sync_protected_pass_status.py
  scripts/45_4_build_protected_pass_review_bundle.py
  docs/PROTECTED_PASS_RECORD_POLICY.md
  tests/test_protected_pass_records_phase1.py
  wrappers/protected_pass_records
  RUN_PROTECTED_PASS_RECORDS_PHASE1_DROPIN.sh
  README_PROTECTED_PASS_RECORDS_PHASE1.md
  PROTECTED_PASS_RECORDS_PHASE1_MANIFEST.sha256
  PROTECTED_PASS_RECORDS_PHASE1_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  campaign/protected_pass_records_v1
  campaign/phase1_candidate_v2
  evidence/protected_pass_records_phase1_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check
(
  cd evidence/protected_pass_records_phase1_v1
  sha256sum -c EVIDENCE_MANIFEST.sha256
)

git commit -m \
  "Acquire four protected passes and complete phase1 review candidate"
git push

COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/protected_pass_records_phase1_v1/FR3_PROTECTED_PASS_RECORDS_PHASE1_REVIEW_v1.zip"
CANDIDATE="campaign/phase1_candidate_v2/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip"

echo "PROTECTED-PASS RECORD PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Candidate: $ROOT/$CANDIDATE"
echo "Candidate SHA-256: $(sha256sum "$CANDIDATE" | awk '{print $1}')"
echo "Campaign execution authorized: NO"
echo "Next gate: INDEPENDENTLY_REVIEW_COMPLETE_PHASE1_CAMPAIGN_CANDIDATE"
