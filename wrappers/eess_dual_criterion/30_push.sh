#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
find scripts tests src -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests src -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache
STAGE=(
 config/eess_dual_criterion_audit_v1.json
 scripts/40_0_run_eess_dual_criterion_audit.py
 scripts/40_1_validate_eess_dual_criterion_audit.py
 scripts/40_2_sync_eess_dual_criterion_status.py
 scripts/40_3_build_eess_dual_criterion_review_bundle.py
 tests/test_eess_dual_criterion_audit.py
 wrappers/eess_dual_criterion
 RUN_EESS_DUAL_CRITERION_AUDIT_DROPIN.sh
 README_EESS_DUAL_CRITERION_AUDIT.md
 EESS_DUAL_CRITERION_AUDIT_MANIFEST.sha256
 EESS_DUAL_CRITERION_AUDIT_TEST_REPORT.txt
 PROJECT_STATUS.md
 NEXT_IMMEDIATE_STEP.md
 evidence/eess_dual_criterion_audit_v1
)
git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c evidence/eess_dual_criterion_audit_v1/EVIDENCE_MANIFEST.sha256
git commit -m "Correct EESS long and short term criterion pairing"
git push
COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/eess_dual_criterion_audit_v1/FR3_EESS_DUAL_CRITERION_AUDIT_REVIEW_v1.zip"
echo "EESS DUAL-CRITERION PUSH: PASS"
echo "Commit: $COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: RERUN_LOCAL_CONTROLLERS_WITH_CORRECTED_DUAL_CRITERIA_QMAX70_AND_PATTERN_SENSITIVITY"
