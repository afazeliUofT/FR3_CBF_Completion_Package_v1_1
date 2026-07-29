#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

WORK="data/real/controller_ready_full_topology_export_prep"
UPLOAD="results/controller_ready_full_topology_export_prep/upload"
EVIDENCE="evidence/controller_ready_full_topology_export_prep"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"

cp \
  "$WORK/FULL_TOPOLOGY_EXPORT_PREP_METADATA.json" \
  "$WORK/FULL_TOPOLOGY_EXPORT_BUNDLE_MANIFEST.sha256" \
  "$UPLOAD/FR3_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_NIBI_v1.zip" \
  "$UPLOAD/FR3_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_NIBI_v1.zip.sha256" \
  "$EVIDENCE/"

cat > "$EVIDENCE/README.md" <<'EOF'
# Controller-ready full-topology export preparation

This evidence contains the source-reviewed Nibi H100 package for one Sionna
topology call with all 228 users. It also includes the immutable job-18658301
reference outputs needed to reproduce the legacy chunked platform numerically.

No cluster job has been submitted by this preparation stage.
EOF

python3 - <<'PY'
from pathlib import Path
import hashlib

root = Path("evidence/controller_ready_full_topology_export_prep")
manifest = root / "EVIDENCE_MANIFEST.sha256"
lines = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path != manifest:
        lines.append(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.as_posix()}"
        )
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("EVIDENCE MANIFEST:", len(lines), "files")
PY

find scripts tests nibi \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests nibi \
  -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

STAGE=(
  config/full_topology_export_prep.json
  config/controller_ready_full_topology_export_v2.yaml
  nibi/controller_ready_full_topology_export_v1
  scripts/33_0_build_full_topology_export_bundle.py
  scripts/33_1_validate_full_topology_export_bundle.py
  tests/test_full_topology_export_prep.py
  wrappers/full_topology_export_prep
  RUN_FULL_TOPOLOGY_EXPORT_PREP_DROPIN.sh
  README_FULL_TOPOLOGY_EXPORT_PREP.md
  FULL_TOPOLOGY_EXPORT_PREP_MANIFEST.sha256
  FULL_TOPOLOGY_EXPORT_PREP_TEST_REPORT.txt
  evidence/controller_ready_full_topology_export_prep
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c "$EVIDENCE/EVIDENCE_MANIFEST.sha256"

git commit -m \
  "Prepare controller-ready full-topology Nibi export"
git push

COMMIT="$(git rev-parse HEAD)"
BUNDLE="$EVIDENCE/FR3_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_NIBI_v1.zip"
echo "FULL-TOPOLOGY EXPORT PREP PACKAGE PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Bundle: $ROOT/$BUNDLE"
echo "Bundle SHA-256: $(sha256sum "$BUNDLE" | awk '{print $1}')"
echo "Next gate: INDEPENDENT_REVIEW_THEN_RUN_SINGLE_NIBI_FULL_TOPOLOGY_EXPORT"
