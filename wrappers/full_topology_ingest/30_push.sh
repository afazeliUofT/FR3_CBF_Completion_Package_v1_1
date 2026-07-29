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
  config/full_topology_ingest_v4.json
  config/full_topology_validated_state_v4.json
  src/fr3_cbf/dynamic_readiness.py
  scripts/34_0_ingest_full_topology_export_v4.py
  scripts/34_1_validate_full_topology_ingestion.py
  scripts/34_2_sync_full_topology_status.py
  scripts/34_3_build_full_topology_review_bundle.py
  tests/test_full_topology_dynamic_readiness.py
  wrappers/full_topology_ingest
  RUN_FULL_TOPOLOGY_INGEST_DYNAMIC_READINESS_DROPIN.sh
  README_FULL_TOPOLOGY_INGEST_DYNAMIC_READINESS.md
  FULL_TOPOLOGY_INGEST_DYNAMIC_READINESS_MANIFEST.sha256
  FULL_TOPOLOGY_INGEST_DYNAMIC_READINESS_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  evidence/full_topology_export_18696267_validated_v4
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c \
  evidence/full_topology_export_18696267_validated_v4/EVIDENCE_MANIFEST.sha256

git commit -m \
  "Freeze validated full-topology export and dynamic readiness"
git push

COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/full_topology_export_18696267_validated_v4/FR3_FULL_TOPOLOGY_DYNAMIC_READINESS_REVIEW_v1.zip"

echo "FULL-TOPOLOGY INGEST PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: IMPLEMENT_LOCAL_STATIC_MYOPIC_AND_PREDICTIVE_CONTROLLERS"
