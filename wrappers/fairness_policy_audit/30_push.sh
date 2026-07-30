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
  config/fairness_policy_audit_v1.json
  scripts/36_0_run_fairness_policy_audit.py
  scripts/36_1_validate_fairness_policy_audit.py
  scripts/36_2_sync_fairness_policy_status.py
  scripts/36_3_build_fairness_review_bundle.py
  tests/test_fairness_policy_audit.py
  wrappers/fairness_policy_audit
  RUN_FAIRNESS_POLICY_AUDIT_DROPIN.sh
  README_FAIRNESS_POLICY_AUDIT.md
  FAIRNESS_POLICY_AUDIT_MANIFEST.sha256
  FAIRNESS_POLICY_AUDIT_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/fairness_policy_audit_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c \
  evidence/fairness_policy_audit_v1/EVIDENCE_MANIFEST.sha256

git commit -m \
  "Freeze constrained proportional-fairness policy"
git push

COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/fairness_policy_audit_v1/FR3_FAIRNESS_POLICY_AUDIT_REVIEW_v1.zip"

echo "FAIRNESS POLICY AUDIT PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: IMPLEMENT_CONSTRAINED_PROPORTIONAL_FAIR_STATIC_MYOPIC_AND_PREDICTIVE_CONTROLLERS"
