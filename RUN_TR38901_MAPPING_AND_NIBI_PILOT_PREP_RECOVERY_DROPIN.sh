#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
mkdir -p logs/tr38901_nibi_dlp_pilot_prep
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/tr38901_nibi_dlp_pilot_prep/api_recovery_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "PANELARRAY API RECOVERY DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 260 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/tr38901_nibi_dlp_pilot_prep")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "SIONNA PANELARRAY API RECOVERY + NIBI PILOT PREPARATION RESUME"
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
git merge-base --is-ancestor 16dfe8e267bc7ea8005da8f8cc03d4143519d7c8 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes detected"
  git diff --cached --name-status
  exit 2
}

WORK="data/real/tr38901_nibi_dlp_pilot_prep"
MAPPING="$WORK/TR38901_USED_SUBSET_MAPPING_DECISION.json"
[[ -f "$MAPPING" ]] || {
  echo "ERROR: the already-passed used-subset mapping decision is missing"
  exit 3
}
MAPPING_STATUS="$(
  python3 - <<'PY'
import json
from pathlib import Path
value = json.loads(
    Path(
        "data/real/tr38901_nibi_dlp_pilot_prep/"
        "TR38901_USED_SUBSET_MAPPING_DECISION.json"
    ).read_text(encoding="utf-8")
)
print(value["status"])
PY
)"
[[ "$MAPPING_STATUS" == "USED_SUBSET_READY_FOR_NONPAPER_GPU_PILOT_WITH_RELEASE19_GAPS" ]] || {
  echo "ERROR: mapping status is $MAPPING_STATUS"
  exit 4
}
echo "EXISTING USED-SUBSET MAPPING: PASS"
echo "Status: $MAPPING_STATUS"

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_tr38901_nibi_pilot_prep.py
echo "RECOVERY STATIC TESTS: PASS"

VENV="/home/afazeli2006/.venvs/fr3-sionna2-2.0.1-cpu"
[[ -x "$VENV/bin/python" ]] || {
  echo "ERROR: qualified Sionna environment is missing: $VENV"
  exit 5
}

echo
echo "=== LIVE SIONNA PANELARRAY API PROBE ==="
PYTHONPATH="$REPO_ROOT/scripts:$REPO_ROOT/src" \
PYTHONDONTWRITEBYTECODE=1 \
"$VENV/bin/python" \
  scripts/31_4_record_sionna_panelarray_api.py \
  --config config/tr38901_nibi_dlp_pilot_prep.json

echo
echo "=== RERUN DUAL-POLARIZATION PORT AUDIT ==="
set +e
set -o pipefail
bash wrappers/tr38901_nibi_pilot_prep/20_port_audit.sh \
  2>&1 | tee logs/tr38901_nibi_dlp_pilot_prep/20_port_audit_recovery.log
PORT_CODE=${PIPESTATUS[0]}
set +o pipefail
set -e
printf '%s\n' "$PORT_CODE" \
  > logs/tr38901_nibi_dlp_pilot_prep/20_port_audit_recovery.exitcode
echo "WRAPPER EXITCODE: 20_port_audit_recovery=$PORT_CODE"
[[ "$PORT_CODE" -eq 0 ]] || exit "$PORT_CODE"

echo
echo "=== BUILD, PACKAGE, COMMIT, AND PUSH ==="
set +e
set -o pipefail
bash wrappers/tr38901_nibi_pilot_prep/30_bundle_package_push.sh \
  2>&1 | tee logs/tr38901_nibi_dlp_pilot_prep/30_bundle_package_push_recovery.log
PACKAGE_CODE=${PIPESTATUS[0]}
set +o pipefail
set -e
printf '%s\n' "$PACKAGE_CODE" \
  > logs/tr38901_nibi_dlp_pilot_prep/30_bundle_package_push_recovery.exitcode
echo "WRAPPER EXITCODE: 30_bundle_package_push_recovery=$PACKAGE_CODE"
[[ "$PACKAGE_CODE" -eq 0 ]] || exit "$PACKAGE_CODE"

COMMIT="$(git rev-parse HEAD)"
UPLOAD="$REPO_ROOT/results/tr38901_nibi_dlp_pilot_prep/upload"
BUNDLE="$UPLOAD/FR3_DLP_RZF_NIBI_ONE_SEED_GPU_PILOT_v1.zip"
CHECKSUM="$BUNDLE.sha256"

[[ -f "$BUNDLE" && -f "$CHECKSUM" ]]
(
  cd "$UPLOAD"
  sha256sum -c "$(basename "$CHECKSUM")"
  unzip -t "$(basename "$BUNDLE")"
)

echo
echo "================================================================="
echo "SIONNA PANELARRAY API RECOVERY DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Next gate: INDEPENDENT_REVIEW_THEN_RUN_NIBI_ONE_SEED_GPU_PILOT"
echo "Nibi bundle: $BUNDLE"
echo "Nibi checksum: $CHECKSUM"
echo "Bundle SHA-256: $(sha256sum "$BUNDLE" | awk '{print $1}')"
echo "Review root: evidence/tr38901_nibi_dlp_pilot_prep/"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$UPLOAD")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/tr38901_nibi_dlp_pilot_prep")" >/dev/null 2>&1 || true
fi
