#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/full_topology_ingest
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/full_topology_ingest/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "FULL-TOPOLOGY INGEST DROP-IN: FAIL"; echo "exit=$code command=$BASH_COMMAND"; tail -n 300 "$MASTER_LOG" || true; exit $code' ERR

FULL_ZIP="$(
  find /mnt/c/Users/alifa/Downloads \
    -maxdepth 4 -type f \
    -iname 'FR3_FULL_TOPOLOGY_EXPORT_RETURN_18696267_VALIDATED_v4.zip' \
    -printf '%T@ %p\n' \
  | sort -nr | head -n 1 | cut -d' ' -f2-
)"
REVIEW_ZIP="$(
  find /mnt/c/Users/alifa/Downloads \
    -maxdepth 4 -type f \
    -iname 'FR3_FULL_TOPOLOGY_EXPORT_REVIEW_18696267_VALIDATED_v4.zip' \
    -printf '%T@ %p\n' \
  | sort -nr | head -n 1 | cut -d' ' -f2-
)"
[[ -f "$FULL_ZIP" ]] || {
  echo "ERROR: validated full return ZIP was not found"
  exit 2
}
[[ -f "$REVIEW_ZIP" ]] || {
  echo "ERROR: validated compact review ZIP was not found"
  exit 3
}
export FR3_FULL_ZIP="$FULL_ZIP"
export FR3_REVIEW_ZIP="$REVIEW_ZIP"

echo "================================================================="
echo "VALIDATED FULL-TOPOLOGY INGEST + DYNAMIC READINESS"
echo "================================================================="
echo "Repository: $ROOT"
echo "Full return: $FR3_FULL_ZIP"
echo "Compact review: $FR3_REVIEW_ZIP"
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, or Narval command will be run."
echo "Master log: $MASTER_LOG"

for name in 00_preflight 10_ingest_analyze 20_sync_package 30_push; do
  wrapper="wrappers/full_topology_ingest/${name}.sh"
  log="logs/full_topology_ingest/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > "logs/full_topology_ingest/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/full_topology_export_18696267_validated_v4/FR3_FULL_TOPOLOGY_DYNAMIC_READINESS_REVIEW_v1.zip"

echo
echo "================================================================="
echo "FULL-TOPOLOGY INGEST + DYNAMIC READINESS DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Next gate: IMPLEMENT_LOCAL_STATIC_MYOPIC_AND_PREDICTIVE_CONTROLLERS"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$REVIEW")")" >/dev/null 2>&1 || true
fi
