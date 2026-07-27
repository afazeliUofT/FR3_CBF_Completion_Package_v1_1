#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
mkdir -p logs/sionna2_topology_readiness
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/sionna2_topology_readiness/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 260 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/sionna2_topology_readiness")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "SIONNA 2.0.1 QUALIFICATION HARDENING + 57-SECTOR TOPOLOGY READINESS"
echo "================================================================="
echo "Repository: $REPO_ROOT"
echo "Log: $MASTER_LOG"

WRAPPERS=(
  00_preflight
  10_delay_source_audit
  20_etsi_source
  30_topology_adapter
  40_finalize_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/sionna2_topology_readiness/${name}.sh"
  log="logs/sionna2_topology_readiness/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > "logs/sionna2_topology_readiness/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
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

echo
echo "================================================================="
echo "SIONNA 2.0.1 TOPOLOGY READINESS DROP-IN: PASS"
echo "Status: $STATUS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Branch URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/tree/e3-first-sector-p452"
echo "Next gate: $NEXT"
echo "Review files:"
echo "  evidence/sionna2_topology_readiness/SIONNA2_DELAY_AND_SOURCE_AUDIT.json"
echo "  evidence/sionna2_topology_readiness/SIONNA2_RAW_DELAY_OUTLIERS.csv"
echo "  evidence/sionna2_topology_readiness/TR38901_V19_4_MAPPING_CHECKLIST.csv"
echo "  evidence/sionna2_topology_readiness/SIONNA2_TOPOLOGY_READINESS_DECISION.json"
echo "  evidence/sionna2_topology_readiness/CUSTOM_57_SECTOR_SIONNA_PILOT_AUDIT.json (when generated)"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/sionna2_topology_readiness")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/logs/sionna2_topology_readiness")" >/dev/null 2>&1 || true
fi
if command -v cmd.exe >/dev/null 2>&1; then
  cmd.exe /c start "" "https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT" >/dev/null 2>&1 || true
fi
