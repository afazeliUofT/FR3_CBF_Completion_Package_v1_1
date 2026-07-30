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
  config/constrained_pf_controller_milestone_v1.json
  src/fr3_cbf/constrained_pf_safety.py
  scripts/37_0_run_constrained_pf_controller_milestone.py
  scripts/37_1_validate_constrained_pf_controller_milestone.py
  scripts/37_2_sync_constrained_pf_controller_status.py
  scripts/37_3_build_constrained_pf_controller_review_bundle.py
  tests/test_constrained_pf_controller_milestone.py
  wrappers/constrained_pf_controller
  RUN_CONSTRAINED_PF_CONTROLLER_MILESTONE_DROPIN.sh
  README_CONSTRAINED_PF_CONTROLLER_MILESTONE.md
  CONSTRAINED_PF_CONTROLLER_MILESTONE_MANIFEST.sha256
  CONSTRAINED_PF_CONTROLLER_MILESTONE_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/constrained_pf_controller_milestone_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c \
  evidence/constrained_pf_controller_milestone_v1/EVIDENCE_MANIFEST.sha256

git commit -m \
  "Implement constrained proportional-fair safety controllers"
git push

COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/constrained_pf_controller_milestone_v1/FR3_CONSTRAINED_PF_CONTROLLER_MILESTONE_REVIEW_v1.zip"

echo "CONSTRAINED PF CONTROLLER PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: FORMALIZE_DELAYED_SAFETY_GUARANTEE_ADD_VIRTUAL_QUEUE_AND_UNCERTAINTY"
