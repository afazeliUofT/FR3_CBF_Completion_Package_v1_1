#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
mkdir -p logs/one_seed_dynamic_contract
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/one_seed_dynamic_contract/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 260 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$ROOT/logs/one_seed_dynamic_contract")" >/dev/null 2>&1 || true; exit $code' ERR

REVIEW_ZIP="$(
  find /mnt/c/Users/alifa/Downloads \
    -maxdepth 4 \
    -type f \
    -iname 'FR3_NIBI_18658301_REVIEW_UPLOAD.zip' \
    -printf '%T@ %p\n' \
  | sort -nr \
  | head -n 1 \
  | cut -d' ' -f2-
)"

[[ -f "$REVIEW_ZIP" ]] || {
  echo "ERROR: FR3_NIBI_18658301_REVIEW_UPLOAD.zip was not found"
  exit 2
}
export FR3_REVIEW_ZIP="$REVIEW_ZIP"

echo "================================================================="
echo "ONE-SEED 18658301 FREEZE + DYNAMIC TWC CONTRACT"
echo "================================================================="
echo "Repository: $ROOT"
echo "Review ZIP: $FR3_REVIEW_ZIP"
echo "Execution: LOCAL WSL ONLY"
echo "No SSH, Slurm, Nibi, or Narval command will be run."
echo "Log: $MASTER_LOG"

WRAPPERS=(
  00_preflight
  10_freeze_evidence
  20_sync_contract_status
  30_package_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/one_seed_dynamic_contract/${name}.sh"
  log="logs/one_seed_dynamic_contract/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" \
    > "logs/one_seed_dynamic_contract/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
REVIEW="$ROOT/evidence/nibi_one_seed_18658301/FR3_ONE_SEED_18658301_DYNAMIC_CONTRACT_REVIEW_v1.zip"

echo
echo "================================================================="
echo "ONE-SEED FREEZE + DYNAMIC CONTRACT DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Execution performed: LOCAL WSL ONLY"
echo "Nibi submission performed: NO"
echo "Narval submission performed: NO"
echo "Next gate: INDEPENDENT_REVIEW_THEN_PREPARE_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$ROOT/evidence/nibi_one_seed_18658301")" >/dev/null 2>&1 || true
fi
if command -v cmd.exe >/dev/null 2>&1; then
  cmd.exe /c start "" "https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT" >/dev/null 2>&1 || true
fi
