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
  config/phase1_nibi_job_package_independent_review_v1.json
  docs/PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_V1.md
  scripts/49_0_verify_freeze_phase1_job_package_review.py
  scripts/49_1_validate_phase1_job_package_independent_review.py
  scripts/49_2_sync_phase1_job_package_review_status.py
  scripts/49_3_build_phase1_job_package_review_freeze_bundle.py
  tests/test_phase1_job_package_independent_review.py
  wrappers/phase1_job_package_independent_review
  RUN_PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_DROPIN.sh
  README_PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW.md
  PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_MANIFEST.sha256
  PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/phase1_nibi_job_package_independent_review_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check

(
  cd evidence/phase1_nibi_job_package_independent_review_v1
  sha256sum -c EVIDENCE_MANIFEST.sha256
  sha256sum -c \
    FR3_PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_v1.zip.sha256
  unzip -t \
    FR3_PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_v1.zip \
    >/dev/null
)

git commit -m \
  "Record independent review of immutable phase1 Nibi job package"
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

REVIEW="evidence/phase1_nibi_job_package_independent_review_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_v1.zip"

echo "PHASE-1 JOB-PACKAGE INDEPENDENT REVIEW PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Verdict: PASS_FOR_NIBI_DEPLOYMENT_SMOKE_PREPARATION_NOT_FULL_CAMPAIGN_EXECUTION"
echo "Full campaign execution authorized: NO"
echo "Next gate: BUILD_REVIEW_AND_RUN_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE"
