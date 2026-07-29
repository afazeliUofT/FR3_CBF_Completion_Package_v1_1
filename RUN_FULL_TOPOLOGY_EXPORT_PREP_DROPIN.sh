#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/full_topology_export_prep
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="logs/full_topology_export_prep/master_${STAMP}.log"
exec > >(tee "$LOG") 2>&1

trap 'code=$?; echo; echo "FULL-TOPOLOGY EXPORT PREP FAIL: exit=$code command=$BASH_COMMAND"; tail -n 260 "$LOG" || true; exit $code' ERR

REVIEW_ZIP="$(
  find /mnt/c/Users/alifa/Downloads \
    -maxdepth 4 -type f \
    -iname 'FR3_NIBI_18658301_REVIEW_UPLOAD.zip' \
    -printf '%T@ %p\n' \
  | sort -nr | head -n 1 | cut -d' ' -f2-
)"
[[ -f "$REVIEW_ZIP" ]] || {
  echo "ERROR: FR3_NIBI_18658301_REVIEW_UPLOAD.zip was not found"
  exit 2
}
export FR3_REVIEW_ZIP="$REVIEW_ZIP"

echo "================================================================="
echo "CONTROLLER-READY FULL-TOPOLOGY EXPORT PREPARATION"
echo "================================================================="
echo "Repository: $ROOT"
echo "Review ZIP: $FR3_REVIEW_ZIP"
echo "Execution: LOCAL WSL ONLY"
echo "No Nibi or Narval job will be submitted."

for name in 00_preflight 10_build_bundle 20_validate_bundle 30_package_push; do
  echo
  echo "=== RUNNING $name ==="
  wrapper="wrappers/full_topology_export_prep/${name}.sh"
  wrapper_log="logs/full_topology_export_prep/${name}.log"

  set +e
  set -o pipefail
  bash "$wrapper" 2>&1 | tee "$wrapper_log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e

  printf '%s\n' "$code"     > "logs/full_topology_export_prep/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
BUNDLE="$ROOT/evidence/controller_ready_full_topology_export_prep/FR3_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_NIBI_v1.zip"

echo
echo "================================================================="
echo "FULL-TOPOLOGY EXPORT PREP DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Bundle: $BUNDLE"
echo "Bundle SHA-256: $(sha256sum "$BUNDLE" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Next gate: INDEPENDENT_REVIEW_THEN_RUN_SINGLE_NIBI_FULL_TOPOLOGY_EXPORT"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$(dirname "$BUNDLE")")" >/dev/null 2>&1 || true
fi
