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
  config/dual_criterion_controller_reevaluation_v1.json
  config/dual_criterion_controller_validated_state_v1.json
  src/fr3_cbf/dual_criterion_controller.py
  scripts/41_0_run_dual_criterion_controller_reevaluation.py
  scripts/41_1_validate_dual_criterion_controller_reevaluation.py
  scripts/41_2_sync_dual_criterion_controller_status.py
  scripts/41_3_build_dual_criterion_controller_review_bundle.py
  tests/test_dual_criterion_controller_reevaluation.py
  wrappers/dual_criterion_controller
  RUN_DUAL_CRITERION_CONTROLLER_REEVALUATION_DROPIN.sh
  README_DUAL_CRITERION_CONTROLLER_REEVALUATION.md
  DUAL_CRITERION_CONTROLLER_REEVALUATION_MANIFEST.sha256
  DUAL_CRITERION_CONTROLLER_REEVALUATION_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/dual_criterion_controller_reevaluation_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c \
  evidence/dual_criterion_controller_reevaluation_v1/EVIDENCE_MANIFEST.sha256

REVIEW="evidence/dual_criterion_controller_reevaluation_v1/FR3_DUAL_CRITERION_CONTROLLER_REEVALUATION_REVIEW_v1.zip"
(
  cd "$(dirname "$REVIEW")"
  sha256sum -c "$(basename "$REVIEW").sha256"
  unzip -t "$(basename "$REVIEW")" >/dev/null
)

# Generated detailed results remain intentionally ignored. Their concise
# scientific records and complete review bundle are committed under evidence/.
if git diff --cached --name-only | grep -q '^results/dual_criterion_controller_reevaluation_v1/'; then
  echo "ERROR: ignored results were unexpectedly staged"
  exit 4
fi

git commit -m \
  "Rerun controllers under corrected EESS dual criteria"
git push

COMMIT="$(git rev-parse HEAD)"
echo "CORRECTED DUAL-CRITERION CONTROLLER PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: CALIBRATE_ARRAY_CSI_NULL_DEPTH_AND_PHYSICAL_UNCERTAINTY_THEN_FREEZE_PHASED_CAMPAIGN"
