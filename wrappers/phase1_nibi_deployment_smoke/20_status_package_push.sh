#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/50_2_sync_phase1_nibi_deployment_smoke_status.py \
  --config config/phase1_nibi_deployment_smoke_v1.json

python3 scripts/50_3_build_phase1_nibi_deployment_smoke_review_bundle.py \
  --config config/phase1_nibi_deployment_smoke_v1.json

find scripts tests src smoke_templates \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) \
  -delete 2>/dev/null || true
find scripts tests src smoke_templates \
  -type d -name '__pycache__' -prune \
  -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

STAGE=(
  config/phase1_nibi_deployment_smoke_v1.json
  docs/PHASE1_NIBI_DEPLOYMENT_SMOKE_INDEPENDENT_REVIEW.md
  scripts/50_0_build_phase1_nibi_deployment_smoke.py
  scripts/50_1_validate_phase1_nibi_deployment_smoke.py
  scripts/50_2_sync_phase1_nibi_deployment_smoke_status.py
  scripts/50_3_build_phase1_nibi_deployment_smoke_review_bundle.py
  smoke_templates/phase1_nibi_deployment_smoke_v1
  tests/test_phase1_nibi_deployment_smoke.py
  wrappers/phase1_nibi_deployment_smoke
  RUN_PHASE1_NIBI_DEPLOYMENT_SMOKE_DROPIN.sh
  README_PHASE1_NIBI_DEPLOYMENT_SMOKE.md
  PHASE1_NIBI_DEPLOYMENT_SMOKE_MANIFEST.sha256
  PHASE1_NIBI_DEPLOYMENT_SMOKE_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  campaign/phase1_nibi_deployment_smoke_v1
  evidence/phase1_nibi_deployment_smoke_prep_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check

(
  cd campaign/phase1_nibi_deployment_smoke_v1
  sha256sum -c SMOKE_SOURCE_MANIFEST.sha256
  sha256sum -c \
    FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1.zip.sha256
  unzip -t FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1.zip >/dev/null
)
(
  cd evidence/phase1_nibi_deployment_smoke_prep_v1
  sha256sum -c EVIDENCE_MANIFEST.sha256
  sha256sum -c \
    FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_PREP_REVIEW_v1.zip.sha256
  unzip -t \
    FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_PREP_REVIEW_v1.zip \
    >/dev/null
)

if git diff --cached --quiet; then
  echo "SMOKE PREPARATION COMMIT: already present; reusing HEAD"
else
  git commit -m \
    "Add reviewed noncampaign phase1 Nibi deployment smoke"
fi
git push

COMMIT="$(git rev-parse HEAD)"
REMOTE="$(
  git ls-remote --heads origin e3-first-sector-p452 \
  | awk '{print $1}'
)"
[[ "$REMOTE" == "$COMMIT" ]] || {
  echo "ERROR: remote branch does not equal local commit"
  exit 5
}

SMOKE="campaign/phase1_nibi_deployment_smoke_v1/FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1.zip"
REVIEW="evidence/phase1_nibi_deployment_smoke_prep_v1/FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_PREP_REVIEW_v1.zip"

echo "NONCAMPAIGN NIBI DEPLOYMENT SMOKE PREP PUSH: PASS"
echo "Commit: $COMMIT"
echo "Smoke ZIP: $ROOT/$SMOKE"
echo "Smoke ZIP SHA-256: $(sha256sum "$SMOKE" | awk '{print $1}')"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Full campaign execution authorized: NO"
