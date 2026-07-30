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
  config/robust_safety_baselines_v1.json
  docs/DELAYED_REACHABILITY_SAFETY_THEOREM.md
  src/fr3_cbf/robust_delayed_safety.py
  scripts/38_0_run_robust_safety_baselines.py
  scripts/38_1_validate_robust_safety_baselines.py
  scripts/38_2_sync_robust_safety_status.py
  scripts/38_3_build_robust_safety_review_bundle.py
  tests/test_robust_delayed_safety.py
  wrappers/robust_safety_baselines
  RUN_ROBUST_DELAYED_SAFETY_BASELINES_DROPIN.sh
  README_ROBUST_DELAYED_SAFETY_BASELINES.md
  ROBUST_DELAYED_SAFETY_BASELINES_MANIFEST.sha256
  ROBUST_DELAYED_SAFETY_BASELINES_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/robust_safety_baselines_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c \
  evidence/robust_safety_baselines_v1/EVIDENCE_MANIFEST.sha256

# Generated results remain intentionally ignored; concise copies and the
# complete review bundle are committed under evidence/.
if git diff --cached --name-only \
  | grep -q '^results/robust_safety_baselines_v1/'; then
  echo "ERROR: ignored generated results were unexpectedly staged"
  exit 2
fi

git commit -m \
  "Formalize robust delayed safety and add queue baselines"
git push

COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/robust_safety_baselines_v1/FR3_ROBUST_DELAYED_SAFETY_BASELINES_REVIEW_v1.zip"

echo "ROBUST DELAYED SAFETY PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: ONLINE_MOVING_AVERAGE_PF_LOAD_TRANSITIONS_AND_MULTI_SEED_PREP"
