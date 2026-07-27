#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
mkdir -p logs/sionna2_topology_readiness
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/sionna2_topology_readiness/etsi_recovery_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "ETSI RECOVERY DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 260 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/sionna2_topology_readiness")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "SIONNA TOPOLOGY READINESS — ETSI 403 RECOVERY AND RESUME"
echo "================================================================="
echo "Repository: $REPO_ROOT"
echo "Log: $MASTER_LOG"

source .venv/bin/activate
export PYTHONPATH="$REPO_ROOT/scripts:$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong Git branch"
  exit 2
}
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected Git origin: $ORIGIN"
  exit 2
}
git merge-base --is-ancestor 95ba554e31b7505b97f09cb6ed23c6ba115ad653 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes detected"
  git diff --cached --name-status
  exit 2
}

DELAY_AUDIT='data/real/sionna2_topology_readiness/SIONNA2_DELAY_AND_SOURCE_AUDIT.json'
[[ -f "$DELAY_AUDIT" ]] || {
  echo "ERROR: the already-completed delay/source audit is missing"
  exit 3
}

DELAY_STATUS="$(
  python3 - <<'PY'
import json
from pathlib import Path
value = json.loads(
    Path(
        "data/real/sionna2_topology_readiness/"
        "SIONNA2_DELAY_AND_SOURCE_AUDIT.json"
    ).read_text(encoding="utf-8")
)
print(value["status"])
PY
)"
[[ "$DELAY_STATUS" == "PASS_ENERGY_WEIGHTED_DELAY_SANITY" ]] || {
  echo "ERROR: delay/source audit status is $DELAY_STATUS"
  exit 4
}
echo "EXISTING DELAY/SOURCE AUDIT: PASS"
echo "Status: $DELAY_STATUS"

WRAPPERS=(
  20_etsi_source
  30_topology_adapter
  40_finalize_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/sionna2_topology_readiness/${name}.sh"
  log="logs/sionna2_topology_readiness/${name}_recovery.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" \
    > "logs/sionna2_topology_readiness/${name}_recovery.exitcode"
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
echo "SIONNA TOPOLOGY READINESS ETSI RECOVERY DROP-IN: PASS"
echo "Status: $STATUS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Next gate: $NEXT"
echo "Review root: evidence/sionna2_topology_readiness/"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/sionna2_topology_readiness")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/logs/sionna2_topology_readiness")" >/dev/null 2>&1 || true
fi
