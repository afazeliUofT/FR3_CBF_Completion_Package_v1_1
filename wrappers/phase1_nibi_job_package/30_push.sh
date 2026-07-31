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
  config/phase1_nibi_job_package_builder_v1.json
  docs/PHASE1_NIBI_JOB_PACKAGE_DESIGN.md
  src/fr3_cbf/phase1_job_runtime.py
  scripts/48_0_build_phase1_nibi_job_package.py
  scripts/48_1_validate_phase1_nibi_job_package.py
  scripts/48_2_run_phase1_exact_local_smoke.py
  scripts/48_3_sync_phase1_nibi_job_package_status.py
  scripts/48_4_build_phase1_nibi_job_package_review_bundle.py
  tests/test_phase1_nibi_job_package_builder.py
  wrappers/phase1_nibi_job_package
  job_templates/phase1_nibi_v1
  RUN_PHASE1_NIBI_JOB_PACKAGE_BUILDER_DROPIN.sh
  README_PHASE1_NIBI_JOB_PACKAGE_BUILDER.md
  PHASE1_NIBI_JOB_PACKAGE_BUILDER_MANIFEST.sha256
  PHASE1_NIBI_JOB_PACKAGE_BUILDER_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  campaign/phase1_nibi_job_package_v1
  evidence/phase1_nibi_job_package_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check

(
  cd campaign/phase1_nibi_job_package_v1
  sha256sum -c PACKAGE_MANIFEST.sha256
  sha256sum -c FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip.sha256
  unzip -t FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip >/dev/null
)
(
  cd evidence/phase1_nibi_job_package_v1
  sha256sum -c EVIDENCE_MANIFEST.sha256
  sha256sum -c FR3_PHASE1_NIBI_JOB_PACKAGE_REVIEW_v1.zip.sha256
  unzip -t FR3_PHASE1_NIBI_JOB_PACKAGE_REVIEW_v1.zip >/dev/null
)

mapfile -t LARGE_FILES < <(
  find \
    campaign/phase1_nibi_job_package_v1 \
    evidence/phase1_nibi_job_package_v1 \
    -type f -size +95M -print
)
[[ "${#LARGE_FILES[@]}" -eq 0 ]] || {
  echo "ERROR: job-package stage contains files over 95 MiB:"
  printf '  %s\n' "${LARGE_FILES[@]}"
  exit 7
}

git commit -m \
  "Build immutable locked phase1 Nibi job package"
git push

COMMIT="$(git rev-parse HEAD)"
REMOTE="$(
  git ls-remote --heads origin e3-first-sector-p452 \
  | awk '{print $1}'
)"
[[ "$REMOTE" == "$COMMIT" ]] || {
  echo "ERROR: remote branch does not equal local commit"
  exit 8
}

PACKAGE="campaign/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip"
REVIEW="evidence/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_REVIEW_v1.zip"

echo "PHASE-1 NIBI JOB-PACKAGE PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Package ID: $(cat campaign/phase1_nibi_job_package_v1/PACKAGE_ID.txt)"
echo "Job package: $ROOT/$PACKAGE"
echo "Job package SHA-256: $(sha256sum "$PACKAGE" | awk '{print $1}')"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Campaign execution authorized: NO"
echo "Nibi submission performed: NO"
echo "Next gate: INDEPENDENTLY_REVIEW_IMMUTABLE_PHASE1_NIBI_JOB_PACKAGE"
