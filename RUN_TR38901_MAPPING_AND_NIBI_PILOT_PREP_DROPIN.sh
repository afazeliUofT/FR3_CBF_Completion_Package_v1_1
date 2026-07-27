#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
mkdir -p logs/tr38901_nibi_dlp_pilot_prep
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/tr38901_nibi_dlp_pilot_prep/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 260 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/tr38901_nibi_dlp_pilot_prep")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "TR 38.901 MAPPING + SIONNA PORT AUDIT + NIBI DLP-RZF PILOT PREP"
echo "================================================================="
echo "Repository: $REPO_ROOT"
echo "Log: $MASTER_LOG"

WRAPPERS=(
  00_preflight
  10_mapping
  20_port_audit
  30_bundle_package_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/tr38901_nibi_pilot_prep/${name}.sh"
  log="logs/tr38901_nibi_dlp_pilot_prep/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > "logs/tr38901_nibi_dlp_pilot_prep/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
UPLOAD="$REPO_ROOT/results/tr38901_nibi_dlp_pilot_prep/upload"
echo
echo "================================================================="
echo "TR 38.901 / NIBI PILOT PREPARATION DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Next gate: INDEPENDENT_REVIEW_THEN_RUN_NIBI_ONE_SEED_GPU_PILOT"
echo "Nibi upload folder: $UPLOAD"
echo "Upload files:"
echo "  FR3_DLP_RZF_NIBI_ONE_SEED_GPU_PILOT_v1.zip"
echo "  FR3_DLP_RZF_NIBI_ONE_SEED_GPU_PILOT_v1.zip.sha256"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$UPLOAD")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/tr38901_nibi_dlp_pilot_prep")" >/dev/null 2>&1 || true
fi
if command -v cmd.exe >/dev/null 2>&1; then
  cmd.exe /c start "" "https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT" >/dev/null 2>&1 || true
fi
