#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/30_3_finalize_topology_readiness.py \
  --config config/sionna2_topology_readiness.json

WORK="data/real/sionna2_topology_readiness"
EVIDENCE="evidence/sionna2_topology_readiness"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"

FILES=(
  "$WORK/SIONNA2_DELAY_AND_SOURCE_AUDIT.json"
  "$WORK/SIONNA2_DELAY_LINK_METRICS.csv"
  "$WORK/SIONNA2_RAW_DELAY_OUTLIERS.csv"
  "$WORK/ETSI_TR_138901_V19_4_SOURCE_RECORD.json"
  "$WORK/TR38901_V19_4_MAPPING_CHECKLIST.csv"
  "$WORK/SIONNA2_TOPOLOGY_READINESS_DECISION.json"
  "$WORK/SIONNA2_TOPOLOGY_STATUS_SYNC.json"
)
OPTIONAL=(
  "$WORK/CUSTOM_57_SECTOR_BS_TOPOLOGY.csv"
  "$WORK/CUSTOM_57_SECTOR_UT_TOPOLOGY.csv"
  "$WORK/CUSTOM_57_SECTOR_TOPOLOGY.npz"
  "$WORK/CUSTOM_57_SECTOR_TOPOLOGY_AUDIT.json"
  "$WORK/CUSTOM_57_SECTOR_USER_RATE_AUDIT.csv"
  "$WORK/CUSTOM_57_SECTOR_SIONNA_PILOT_AUDIT.json"
  "$WORK/CUSTOM_TOPOLOGY_ADAPTER_SKIPPED.json"
)
cp "${FILES[@]}" "$EVIDENCE/"
for path in "${OPTIONAL[@]}"; do
  [[ -f "$path" ]] && cp "$path" "$EVIDENCE/"
done

cat > "$EVIDENCE/README.md" <<'EOF'
# Sionna 2.0.1 topology-readiness and delay hardening

This evidence resolves the qualification's misleading raw maximum-delay
statistic using path-energy-supported and RMS-delay metrics, hashes the
installed Sionna source modules, archives the official ETSI TR 138 901 V19.4.0
source record, creates a standards-mapping checklist, and—when the delay gate
passes—qualifies a finite one-user-per-sector 57-sector CPU adapter.

It is not a four-user GPU DLP-RZF paper experiment.
EOF

python3 - <<'PY'
from hashlib import sha256
from pathlib import Path

root = Path("evidence/sionna2_topology_readiness")
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
  config/sionna2_topology_readiness.json
  scripts/30_0_audit_sionna2_delay_and_source.py
  scripts/30_1_prepare_custom_57_sector_topology.py
  scripts/30_2_run_custom_57_sector_sionna_pilot.py
  scripts/30_3_finalize_topology_readiness.py
  tests/test_sionna2_topology_readiness_static.py
  RUN_SIONNA2_TOPOLOGY_READINESS_DROPIN.sh
  RUN_SIONNA2_TOPOLOGY_READINESS_ETSI_RECOVERY_DROPIN.sh
  README_SIONNA2_TOPOLOGY_READINESS.md
  README_SIONNA2_TOPOLOGY_READINESS_ETSI_RECOVERY.md
  SIONNA2_TOPOLOGY_READINESS_MANIFEST.sha256
  SIONNA2_TOPOLOGY_READINESS_TEST_REPORT.txt
  wrappers/sionna2_topology_readiness
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  config/current_audited_state.yaml
  evidence/sionna2_topology_readiness
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c "$EVIDENCE/EVIDENCE_MANIFEST.sha256"

STATUS="$(
  python3 - <<'PY'
import json
from pathlib import Path
value = json.loads(
    Path(
        "data/real/sionna2_topology_readiness/"
        "SIONNA2_TOPOLOGY_READINESS_DECISION.json"
    ).read_text(encoding="utf-8")
)
print(value["status"])
PY
)"
if [[ "$STATUS" == "PASS_TO_GPU_4USER_PILOT_WITH_STANDARDS_MAPPING_OPEN" ]]; then
  MESSAGE="Harden Sionna delay audit and qualify custom 57-sector adapter"
else
  MESSAGE="Record Sionna delay scientific stop and standards source audit"
fi

git commit -m "$MESSAGE"
git push
COMMIT="$(git rev-parse HEAD)"
NEXT="$(
  python3 - <<'PY'
import json
from pathlib import Path
value = json.loads(
    Path(
        "data/real/sionna2_topology_readiness/"
        "SIONNA2_TOPOLOGY_READINESS_DECISION.json"
    ).read_text(encoding="utf-8")
)
print(value["next_gate"])
PY
)"

echo "WRAPPER 40 FINALIZE/PUSH: PASS"
echo "Status: $STATUS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Next gate: $NEXT"
echo "Review root: evidence/sionna2_topology_readiness/"
