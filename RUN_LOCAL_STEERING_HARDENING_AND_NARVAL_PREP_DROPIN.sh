#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
mkdir -p logs/tr38901_narval_dlp_pilot_prep
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/tr38901_narval_dlp_pilot_prep/local_prep_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "LOCAL/NARVAL PREP FAIL: exit=$code command=$BASH_COMMAND"; tail -n 260 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/tr38901_narval_dlp_pilot_prep")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "LOCAL STEERING HARDENING + NARVAL A100 PILOT PREPARATION"
echo "================================================================="
echo "Repository: $REPO_ROOT"
echo "Execution location: LOCAL WSL ONLY"
echo "No SSH, Slurm, Narval, or Nibi job will be started."
echo "Log: $MASTER_LOG"

WRAPPERS=(
  00_preflight
  10_local_audits
  20_build_validate_bundle
  30_package_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/tr38901_narval_pilot_prep/${name}.sh"
  log="logs/tr38901_narval_dlp_pilot_prep/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" \
    > "logs/tr38901_narval_dlp_pilot_prep/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
UPLOAD="$REPO_ROOT/results/tr38901_narval_dlp_pilot_prep/upload"
BUNDLE="$UPLOAD/FR3_DLP_RZF_NARVAL_ONE_SEED_GPU_PILOT_v1.zip"
CHECKSUM="$BUNDLE.sha256"

echo
echo "================================================================="
echo "LOCAL STEERING HARDENING + NARVAL PREP DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Narval submission performed: NO"
echo "Next gate: TRANSFER_AND_RUN_ONE_SEED_PILOT_ON_NARVAL"
echo "Narval bundle: $BUNDLE"
echo "Narval checksum: $CHECKSUM"
echo "Bundle SHA-256: $(sha256sum "$BUNDLE" | awk '{print $1}')"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$UPLOAD")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/tr38901_narval_dlp_pilot_prep")" >/dev/null 2>&1 || true
fi
