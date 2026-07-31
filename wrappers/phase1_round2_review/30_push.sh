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
  config/phase1_candidate_v3_round2_review_v1.json
  docs/PHASE1_INDEPENDENT_REVIEW_ROUND2.md
  scripts/47_0_verify_freeze_round2_review.py
  scripts/47_1_validate_round2_review_freeze.py
  scripts/47_2_sync_round2_review_status.py
  scripts/47_3_build_round2_review_bundle.py
  tests/test_phase1_round2_review_freeze.py
  wrappers/phase1_round2_review
  RUN_PHASE1_ROUND2_REVIEW_FREEZE_DROPIN.sh
  README_PHASE1_ROUND2_REVIEW_FREEZE.md
  PHASE1_ROUND2_REVIEW_FREEZE_MANIFEST.sha256
  PHASE1_ROUND2_REVIEW_FREEZE_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/phase1_candidate_v3_round2_review
)

git add -- "${STAGE[@]}"
git diff --cached --check

(
  cd evidence/phase1_candidate_v3_round2_review
  sha256sum -c EVIDENCE_MANIFEST.sha256
  sha256sum -c \
    FR3_PHASE1_CANDIDATE_V3_ROUND2_REVIEW_v1.zip.sha256
  unzip -t \
    FR3_PHASE1_CANDIDATE_V3_ROUND2_REVIEW_v1.zip \
    >/dev/null
)

git commit -m \
  "Record phase1 candidate v3 independent review round2 pass"
git push

COMMIT="$(git rev-parse HEAD)"
REMOTE="$(
  git ls-remote --heads origin e3-first-sector-p452 \
  | awk '{print $1}'
)"
[[ "$REMOTE" == "$COMMIT" ]] || {
  echo "ERROR: remote branch does not equal local commit"
  exit 6
}

REVIEW="evidence/phase1_candidate_v3_round2_review/FR3_PHASE1_CANDIDATE_V3_ROUND2_REVIEW_v1.zip"

echo "PHASE-1 ROUND-2 REVIEW PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Verdict: PASS_FOR_IMMUTABLE_JOB_PACKAGE_PREPARATION_NOT_EXECUTION"
echo "Campaign execution authorized: NO"
echo "Next gate: BUILD_AND_INDEPENDENTLY_REVIEW_IMMUTABLE_PHASE1_NIBI_JOB_PACKAGE"
