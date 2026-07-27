#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/31_2_build_nibi_dlp_pilot_bundle.py \
  --config config/tr38901_nibi_dlp_pilot_prep.json

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/31_3_sync_pilot_prep_status.py \
  --config config/tr38901_nibi_dlp_pilot_prep.json

WORK="data/real/tr38901_nibi_dlp_pilot_prep"
EVIDENCE="evidence/tr38901_nibi_dlp_pilot_prep"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"

cp \
  "$WORK/SIONNA_PANELARRAY_API_RECOVERY.json" \
  "$WORK/SIONNA_PANELARRAY_API_RECOVERY.md" \
  "$WORK/TR38901_USED_SUBSET_MAPPING_DECISION.json" \
  "$WORK/TR38901_USED_SUBSET_MAPPING_DECISION.md" \
  "$WORK/TR38901_V19_4_USED_SUBSET_MAPPING.csv" \
  "$WORK/SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json" \
  "$WORK/SIONNA_DUAL_POL_PORT_ORDER_AUDIT.md" \
  "$WORK/SIONNA_8X8_DUAL_PORT_ORDER.csv" \
  "$WORK/SIONNA_8X8_DUAL_STEERING_SAMPLE.npz" \
  "$WORK/NIBI_BUNDLE_METADATA.json" \
  "$WORK/NIBI_BUNDLE_CONTENTS.sha256" \
  "$WORK/NIBI_PILOT_PREP_STATUS_SYNC.json" \
  "$EVIDENCE/"

cat > "$EVIDENCE/README.md" <<'EOF'
# TR 38.901 mapping and Nibi DLP-RZF pilot preparation

This evidence freezes the used-subset V19.4.0 mapping boundary, verifies the
exact Sionna 2.0.1 8x8 dual-polarized port ordering, and records the contents
and hash of the Nibi one-seed GPU pilot bundle.

It is preparation evidence only. The GPU pilot and paper campaign are not yet
complete.
EOF

python3 - <<'PY'
from hashlib import sha256
from pathlib import Path
root = Path("evidence/tr38901_nibi_dlp_pilot_prep")
manifest = root / "EVIDENCE_MANIFEST.sha256"
lines = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path != manifest:
        lines.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.as_posix()}")
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("EVIDENCE MANIFEST:", manifest, len(lines))
PY

find scripts tests src nibi \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests src nibi \
  -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

STAGE=(
  config/tr38901_nibi_dlp_pilot_prep.json
  scripts/31_0_freeze_tr38901_used_subset_mapping.py
  scripts/31_1_audit_sionna_dual_pol_port_order.py
  scripts/31_2_build_nibi_dlp_pilot_bundle.py
  scripts/31_3_sync_pilot_prep_status.py
  scripts/31_4_record_sionna_panelarray_api.py
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  config/current_audited_state.yaml
  tests/test_tr38901_nibi_pilot_prep.py
  nibi/dlp_rzf_pilot_v1
  RUN_TR38901_MAPPING_AND_NIBI_PILOT_PREP_DROPIN.sh
  RUN_TR38901_MAPPING_AND_NIBI_PILOT_PREP_RECOVERY_DROPIN.sh
  README_TR38901_MAPPING_AND_NIBI_PILOT_PREP.md
  README_TR38901_MAPPING_AND_NIBI_PILOT_PREP_RECOVERY.md
  TR38901_MAPPING_NIBI_PILOT_PREP_MANIFEST.sha256
  TR38901_MAPPING_NIBI_PILOT_PREP_TEST_REPORT.txt
  wrappers/tr38901_nibi_pilot_prep
  evidence/tr38901_nibi_dlp_pilot_prep
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c "$EVIDENCE/EVIDENCE_MANIFEST.sha256"

git commit -m "Repair Sionna PanelArray API and prepare Nibi DLP-RZF GPU bundle"
git push
COMMIT="$(git rev-parse HEAD)"

echo "WRAPPER 30 BUNDLE/PACKAGE/PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Nibi ZIP:"
echo "  results/tr38901_nibi_dlp_pilot_prep/upload/FR3_DLP_RZF_NIBI_ONE_SEED_GPU_PILOT_v1.zip"
echo "Nibi checksum:"
echo "  results/tr38901_nibi_dlp_pilot_prep/upload/FR3_DLP_RZF_NIBI_ONE_SEED_GPU_PILOT_v1.zip.sha256"
echo "Next gate: INDEPENDENT_REVIEW_THEN_RUN_NIBI_ONE_SEED_GPU_PILOT"
