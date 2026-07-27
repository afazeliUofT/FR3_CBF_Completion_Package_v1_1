#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

WORK="data/real/tr38901_narval_dlp_pilot_prep"
EVIDENCE="evidence/tr38901_narval_dlp_pilot_prep"
UPLOAD="results/tr38901_narval_dlp_pilot_prep/upload"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"

cp \
  "$WORK/SIONNA_PANELARRAY_API_RECOVERY.json" \
  "$WORK/SIONNA_PANELARRAY_API_RECOVERY.md" \
  "$WORK/SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json" \
  "$WORK/SIONNA_DUAL_POL_PORT_ORDER_AUDIT.md" \
  "$WORK/SIONNA_8X8_DUAL_PORT_ORDER.csv" \
  "$WORK/SIONNA_8X8_DUAL_STEERING_SAMPLE.npz" \
  "$WORK/SIONNA_INCUMBENT_LOCAL_FRAME.csv" \
  "$WORK/SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT.json" \
  "$WORK/SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT.md" \
  "$WORK/NARVAL_BUNDLE_METADATA.json" \
  "$WORK/NARVAL_BUNDLE_CONTENTS.sha256" \
  "$EVIDENCE/"

cat > "$EVIDENCE/README.md" <<'EOF'
# Local steering hardening and Narval pilot preparation

All non-heavy work in this stage ran locally in WSL. No SSH, Slurm, Narval,
or Nibi job was started.

The generated pilot package targets Narval only, uses a Narval-specific
virtual environment and scratch directory, requests one full A100 40 GB GPU,
and generates Sionna channels in user chunks to fit that GPU.

The previously generated Nibi FR3 bundle with SHA-256
a6ad7c3e202b57ff002b330b1d2c4e0f5b58a90b10fb7e64d6ae86c7069bef69
is superseded and must not be run.
EOF

cat > NIBI_FR3_EXECUTION_SUPERSEDED.md <<'EOF'
# FR3 Nibi execution is superseded

No FR3 job was submitted to Nibi.

The prior locally generated Nibi-oriented FR3 bundle with SHA-256

`a6ad7c3e202b57ff002b330b1d2c4e0f5b58a90b10fb7e64d6ae86c7069bef69`

must not be transferred or run. The active heavy-compute target is Narval and
uses a separate Narval-only virtual environment, job name, scratch directory,
and A100 request. The user's unrelated quantum-computing work on Nibi remains
separate.
EOF

python3 - <<'PY'
from hashlib import sha256
from pathlib import Path

root = Path("evidence/tr38901_narval_dlp_pilot_prep")
manifest = root / "EVIDENCE_MANIFEST.sha256"
lines = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path != manifest:
        lines.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.as_posix()}")
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("EVIDENCE MANIFEST:", manifest, len(lines))
PY

find scripts tests src narval \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests src narval \
  -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

STAGE=(
  config/tr38901_narval_dlp_pilot_prep.json
  scripts/31_1_audit_sionna_dual_pol_port_order.py
  scripts/31_2_build_narval_dlp_pilot_bundle.py
  scripts/31_4_record_sionna_panelarray_api.py
  scripts/31_5_audit_sionna_incumbent_local_frame.py
  scripts/31_6_validate_narval_bundle_source.py
  tests/test_tr38901_narval_pilot_prep.py
  narval/dlp_rzf_pilot_v1
  wrappers/tr38901_narval_pilot_prep
  RUN_LOCAL_STEERING_HARDENING_AND_NARVAL_PREP_DROPIN.sh
  README_LOCAL_STEERING_HARDENING_AND_NARVAL_PREP.md
  LOCAL_STEERING_NARVAL_PREP_MANIFEST.sha256
  LOCAL_STEERING_NARVAL_PREP_TEST_REPORT.txt
  NIBI_FR3_EXECUTION_SUPERSEDED.md
  evidence/tr38901_narval_dlp_pilot_prep
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c "$EVIDENCE/EVIDENCE_MANIFEST.sha256"

git commit -m "Harden steering locally and prepare separate Narval A100 pilot"
git push
COMMIT="$(git rev-parse HEAD)"

BUNDLE="$UPLOAD/FR3_DLP_RZF_NARVAL_ONE_SEED_GPU_PILOT_v1.zip"
CHECKSUM="$BUNDLE.sha256"
(
  cd "$UPLOAD"
  sha256sum -c "$(basename "$CHECKSUM")"
  unzip -t "$(basename "$BUNDLE")"
)

echo "LOCAL PACKAGE/PUSH: PASS"
echo "Commit: $COMMIT"
echo "Bundle: $ROOT/$BUNDLE"
echo "Bundle SHA-256: $(sha256sum "$BUNDLE" | awk '{print $1}')"
echo "Next gate: TRANSFER_AND_RUN_ONE_SEED_PILOT_ON_NARVAL"
