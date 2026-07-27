#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

WORK="data/real/sionna2_channel_qualification"
EVIDENCE="evidence/sionna2_channel_qualification"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"

cp \
  "$WORK/CHANNEL_SOURCE_REVIEW_DECISION.json" \
  "$WORK/CHANNEL_SOURCE_REVIEW_DECISION.md" \
  "$WORK/SIONNA2_API_QUALIFICATION_AUDIT.json" \
  "$WORK/UMA_API_QUALIFICATION_SUMMARY.json" \
  "$WORK/UMI_API_QUALIFICATION_SUMMARY.json" \
  "$WORK/SIONNA2_ENVIRONMENT.json" \
  "$WORK/SIONNA2_CHANNEL_QUALIFICATION_VALIDATION.json" \
  "$WORK/SIONNA2_CHANNEL_QUALIFICATION_VALIDATION.md" \
  "$WORK/CHANNEL_IMPLEMENTATION_DECISION.json" \
  "$WORK/CHANNEL_IMPLEMENTATION_DECISION.md" \
  "$WORK/SIONNA2_STATUS_SYNC.json" \
  "$WORK/SIONNA_TOP_LEVEL_WHEEL.sha256" \
  "$WORK/PIP_FREEZE.txt" \
  "$WORK/PIP_LIST.json" \
  "$WORK/PIP_CHECK.txt" \
  "$EVIDENCE/"

cat > "$EVIDENCE/README.md" <<'EOF'
# Clean Sionna 2.0.1 channel implementation qualification

The reviewed FR3 source root did not contain a reusable executable UMa/UMi
channel engine or archived channel-result bundle. This evidence qualifies a
clean CPU installation of `sionna-no-rt==2.0.1` with `torch==2.9.1` and runs
small deterministic UMa and UMi API pilots at 8.15 GHz.

This is environment/API evidence only. It does not certify exact ETSI
TR 138 901 V19.4.0 clause coverage and is not a paper result.
EOF

python3 - <<'PY'
from hashlib import sha256
from pathlib import Path

root = Path("evidence/sionna2_channel_qualification")
manifest = root / "EVIDENCE_MANIFEST.sha256"
lines = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path != manifest:
        lines.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.as_posix()}")
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("EVIDENCE MANIFEST:", manifest, len(lines))
PY

find scripts tests src \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests src \
  -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

STAGE=(
  config/sionna2_channel_qualification.json
  requirements/sionna2_channel_qualification.txt
  scripts/29_0_close_channel_snapshot_review.py
  scripts/29_1_run_sionna2_api_qualification.py
  scripts/29_2_validate_sionna2_qualification.py
  scripts/29_3_freeze_channel_implementation_decision.py
  tests/test_sionna2_channel_qualification_static.py
  RUN_SIONNA2_CHANNEL_QUALIFICATION_DROPIN.sh
  README_SIONNA2_CHANNEL_QUALIFICATION.md
  SIONNA2_CHANNEL_QUALIFICATION_MANIFEST.sha256
  SIONNA2_CHANNEL_QUALIFICATION_TEST_REPORT.txt
  wrappers/sionna2_channel_qualification
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  config/current_audited_state.yaml
  evidence/sionna2_channel_qualification
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c "$EVIDENCE/EVIDENCE_MANIFEST.sha256"

git commit -m "Qualify clean Sionna 2.0.1 channel implementation candidate"
git push
COMMIT="$(git rev-parse HEAD)"

echo "WRAPPER 30 PACKAGE/PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "NEXT REVIEW FILES:"
echo "  evidence/sionna2_channel_qualification/CHANNEL_SOURCE_REVIEW_DECISION.json"
echo "  evidence/sionna2_channel_qualification/SIONNA2_API_QUALIFICATION_AUDIT.json"
echo "  evidence/sionna2_channel_qualification/SIONNA2_CHANNEL_QUALIFICATION_VALIDATION.json"
echo "  evidence/sionna2_channel_qualification/CHANNEL_IMPLEMENTATION_DECISION.json"
echo "  evidence/sionna2_channel_qualification/PIP_FREEZE.txt"
