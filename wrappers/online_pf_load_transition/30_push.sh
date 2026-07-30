#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Remove the two compiled artifacts accidentally committed by the predecessor,
# plus any newly generated local caches. The repository already ignores them.
git rm --cached --ignore-unmatch \
  src/fr3_cbf/__pycache__/robust_delayed_safety.cpython-313.pyc \
  tests/__pycache__/test_robust_delayed_safety.cpython-313-pytest-9.0.2.pyc
find scripts tests src \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) \
  -delete 2>/dev/null || true
find scripts tests src \
  -type d -name '__pycache__' -prune \
  -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

STAGE=(
  config/online_pf_load_transition_v1.json
  config/online_pf_load_transition_validated_state_v1.json
  config/multi_seed_campaign_spec_v1.json
  docs/DELAYED_REACHABILITY_SAFETY_THEOREM.md
  src/fr3_cbf/online_pf_load_transition.py
  scripts/39_0_run_online_pf_load_transition.py
  scripts/39_1_validate_online_pf_load_transition.py
  scripts/39_2_sync_online_pf_status.py
  scripts/39_3_build_online_pf_review_bundle.py
  tests/test_online_pf_load_transition.py
  wrappers/online_pf_load_transition
  RUN_ONLINE_PF_LOAD_TRANSITION_DROPIN.sh
  README_ONLINE_PF_LOAD_TRANSITION.md
  ONLINE_PF_LOAD_TRANSITION_MANIFEST.sha256
  ONLINE_PF_LOAD_TRANSITION_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/online_pf_load_transition_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c \
  evidence/online_pf_load_transition_v1/EVIDENCE_MANIFEST.sha256

if git ls-files | grep -Eq '(^|/)(__pycache__/|.*\.py[co]$)'; then
  echo "ERROR: tracked compiled artifacts remain"
  git ls-files | grep -E '(^|/)(__pycache__/|.*\.py[co]$)'
  exit 8
fi
echo "TRACKED COMPILED-ARTIFACT CLEANUP: PASS"

# results/ remains intentionally ignored. Its complete action/average record is
# embedded in the committed review ZIP.
if git diff --cached --name-only | grep -q '^results/online_pf_load_transition_v1/'; then
  echo "ERROR: ignored generated results were unexpectedly staged"
  exit 9
fi

git commit -m \
  "Implement online PF load transitions and repair safety theorem"
git push

COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/online_pf_load_transition_v1/FR3_ONLINE_PF_LOAD_TRANSITION_REVIEW_v1.zip"

echo "ONLINE PF LOAD-TRANSITION PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: CALIBRATE_UNCERTAINTY_AND_PREPARE_MULTI_SEED_MULTI_PASS_CAMPAIGN"
