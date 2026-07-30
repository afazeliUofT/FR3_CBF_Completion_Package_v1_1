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
  config/sector_selective_backoff_v1.json
  config/sector_selective_backoff_state_v1.json
  config/phased_campaign_spec_v3.json
  docs/DECLARED_ARRAY_CSI_ENGINEERING_ENVELOPE_V1.md
  docs/SECTOR_SELECTIVE_BACKOFF_CERTIFICATE.md
  src/fr3_cbf/null_floor_aware_sector_backoff.py
  scripts/43_0_run_sector_selective_backoff.py
  scripts/43_1_validate_sector_selective_backoff.py
  scripts/43_2_sync_sector_selective_backoff_status.py
  scripts/43_3_build_sector_selective_backoff_review_bundle.py
  tests/test_sector_selective_backoff.py
  wrappers/sector_selective_backoff
  RUN_DECLARED_ENVELOPE_SECTOR_BACKOFF_DROPIN.sh
  README_DECLARED_ENVELOPE_SECTOR_BACKOFF.md
  DECLARED_ENVELOPE_SECTOR_BACKOFF_MANIFEST.sha256
  DECLARED_ENVELOPE_SECTOR_BACKOFF_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/sector_selective_backoff_v1
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c \
  evidence/sector_selective_backoff_v1/EVIDENCE_MANIFEST.sha256
(
  cd evidence/sector_selective_backoff_v1
  sha256sum -c FR3_SECTOR_SELECTIVE_BACKOFF_REVIEW_v1.zip.sha256
  unzip -t FR3_SECTOR_SELECTIVE_BACKOFF_REVIEW_v1.zip >/dev/null
)

if git diff --cached --name-only | grep -q '^results/sector_selective_backoff_v1/'; then
  echo "ERROR: ignored generated results were unexpectedly staged"
  exit 6
fi
echo "IGNORED RESULTS POLICY: PASS"

git commit -m \
  "Implement declared-envelope sector-selective fallback"
git push

COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/sector_selective_backoff_v1/FR3_SECTOR_SELECTIVE_BACKOFF_REVIEW_v1.zip"

echo "DECLARED-ENVELOPE SECTOR BACKOFF PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: MAP_PRACTICAL_64T64R_OR_HYBRID_ARCHITECTURE_AND_INDEPENDENTLY_REVIEW_PHASE1_CAMPAIGN_BUNDLE"
