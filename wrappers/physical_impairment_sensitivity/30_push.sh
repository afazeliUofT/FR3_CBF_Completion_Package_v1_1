#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
find scripts tests src -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests src -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache
STAGE=(
  config/physical_impairment_sensitivity_v1.json
  config/phased_campaign_spec_v2.json
  data/templates/ARRAY_CSI_CALIBRATION_TEMPLATE.csv
  docs/PHYSICAL_CALIBRATION_REQUIREMENTS.md
  source_inputs/physical_impairment_sensitivity_v1
  src/fr3_cbf/physical_impairment_sensitivity.py
  scripts/42_0_run_physical_impairment_sensitivity.py
  scripts/42_1_validate_physical_impairment_sensitivity.py
  scripts/42_2_sync_physical_impairment_status.py
  scripts/42_3_build_physical_impairment_review_bundle.py
  tests/test_physical_impairment_sensitivity.py
  wrappers/physical_impairment_sensitivity
  RUN_PHYSICAL_IMPAIRMENT_SENSITIVITY_DROPIN.sh
  README_PHYSICAL_IMPAIRMENT_SENSITIVITY.md
  PHYSICAL_IMPAIRMENT_SENSITIVITY_MANIFEST.sha256
  PHYSICAL_IMPAIRMENT_SENSITIVITY_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/physical_impairment_sensitivity_v1
)
git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c evidence/physical_impairment_sensitivity_v1/EVIDENCE_MANIFEST.sha256
git commit -m "Audit practical null depth and freeze calibration gate"
git push
COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/physical_impairment_sensitivity_v1/FR3_PHYSICAL_IMPAIRMENT_SENSITIVITY_REVIEW_v1.zip"
echo "PHYSICAL IMPAIRMENT SENSITIVITY PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: ACQUIRE_OR_DECLARE_ARRAY_CSI_CALIBRATION_ENVELOPE_AND_IMPLEMENT_NULL_FLOOR_AWARE_SECTOR_BACKOFF"
