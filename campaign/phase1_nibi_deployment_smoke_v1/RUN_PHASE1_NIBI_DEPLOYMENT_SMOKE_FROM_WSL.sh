#!/usr/bin/env bash
# Local WSL orchestrator for exactly one excluded Nibi H100 deployment smoke.
set -Eeuo pipefail

ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
fi

SMOKE_DIR="campaign/phase1_nibi_deployment_smoke_v1"
SMOKE_CONTRACT="$SMOKE_DIR/SMOKE_PACKAGE_CONTRACT.json"
SMOKE_ZIP="$SMOKE_DIR/FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1.zip"
REMOTE_SCRIPT="$SMOKE_DIR/remote_smoke_orchestrator.sh"
JOB_ZIP="campaign/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip"
NIBI_HOST="${1:-${FR3_NIBI_HOST:-rsadve1@nibi.alliancecan.ca}}"

for path in \
  "$SMOKE_CONTRACT" \
  "$SMOKE_ZIP" \
  "$SMOKE_ZIP.sha256" \
  "$REMOTE_SCRIPT" \
  "$JOB_ZIP" \
  "$JOB_ZIP.sha256"
do
  [[ -f "$path" ]] || {
    echo "ERROR: required local smoke input is missing: $path"
    exit 2
  }
done

readarray -t VALUE < <(
  python3 - "$SMOKE_CONTRACT" <<'PY'
from pathlib import Path
import json
import sys
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["job_package_id"])
print(value["job_package_sha256"])
print(value["candidate_v3_sha256"])
print(value["smoke_seed"])
print(value["token_ttl_hours"])
print(value["job_package_review_commit"])
PY
)
PACKAGE_ID="${VALUE[0]}"
EXPECTED_JOB_SHA="${VALUE[1]}"
CANDIDATE_SHA="${VALUE[2]}"
SMOKE_SEED="${VALUE[3]}"
TOKEN_TTL_HOURS="${VALUE[4]}"
REVIEW_COMMIT="${VALUE[5]}"
EXPECTED_SMOKE_SHA="$(sha256sum "$SMOKE_ZIP" | awk '{print $1}')"
SOURCE_COMMIT="$(git rev-parse HEAD)"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: expected branch e3-first-sector-p452"
  exit 3
}
git merge-base --is-ancestor "$REVIEW_COMMIT" HEAD || {
  echo "ERROR: independent job-package review commit is not in current history"
  exit 4
}
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected Git origin: $ORIGIN"
  exit 5
}
[[ "$(sha256sum "$JOB_ZIP" | awk '{print $1}')" == "$EXPECTED_JOB_SHA" ]]
(
  cd "$SMOKE_DIR"
  sha256sum -c "$(basename "$SMOKE_ZIP.sha256")"
  unzip -t "$(basename "$SMOKE_ZIP")" >/dev/null
)
[[ "$SMOKE_SEED" -lt 44000 || "$SMOKE_SEED" -gt 44029 ]] || {
  echo "ERROR: smoke seed overlaps the confirmatory campaign"
  exit 6
}

STAMP="$(date -u +%Y%m%d_%H%M%S)"
SHORT="${PACKAGE_ID:0:12}_${SMOKE_SEED}_${SOURCE_COMMIT:0:7}"
LOCAL_RETURN="/mnt/c/Users/alifa/Downloads/FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_${SHORT}_${STAMP}"
mkdir -p "$LOCAL_RETURN"
LOCAL_LOG="$LOCAL_RETURN/local_orchestrator.log"
exec > >(tee "$LOCAL_LOG") 2>&1

CONTROL_PATH="/tmp/fr3p1smoke-$$-%C"
SSH_OPTS=(
  -o ControlMaster=auto
  -o ControlPersist=15m
  -o ControlPath="$CONTROL_PATH"
  -o ServerAliveInterval=60
  -o ServerAliveCountMax=20
  -o ConnectTimeout=30
)
SCP_OPTS=(
  -o ControlMaster=auto
  -o ControlPersist=15m
  -o ControlPath="$CONTROL_PATH"
  -o ServerAliveInterval=60
  -o ServerAliveCountMax=20
  -o ConnectTimeout=30
)

cleanup_control() {
  ssh "${SSH_OPTS[@]}" -O exit "$NIBI_HOST" >/dev/null 2>&1 || true
}
trap cleanup_control EXIT

failure() {
  code=$?
  trap - ERR
  echo
  echo "================================================================="
  echo "LOCAL NONCAMPAIGN NIBI SMOKE ORCHESTRATOR: FAIL"
  echo "Exit code: $code"
  echo "Command: ${BASH_COMMAND:-unknown}"
  echo "Local return folder: $LOCAL_RETURN"
  echo "Full campaign execution authorized: NO"
  echo "================================================================="
  exit "$code"
}
trap failure ERR

echo "================================================================="
echo "PHASE-1 NONCAMPAIGN NIBI DEPLOYMENT SMOKE — LOCAL WSL"
echo "================================================================="
echo "Repository: $ROOT"
echo "Source commit: $SOURCE_COMMIT"
echo "Nibi host: $NIBI_HOST"
echo "Package ID: $PACKAGE_ID"
echo "Job ZIP SHA-256: $EXPECTED_JOB_SHA"
echo "Smoke ZIP SHA-256: $EXPECTED_SMOKE_SHA"
echo "Candidate SHA-256: $CANDIDATE_SHA"
echo "Smoke seed: $SMOKE_SEED"
echo "Confirmatory analysis included: NO"
echo "Full campaign authorized: NO"
echo "Local return folder: $LOCAL_RETURN"

echo
echo "=== Nibi connection and scratch preflight ==="
PREFLIGHT="$(
  ssh "${SSH_OPTS[@]}" "$NIBI_HOST" '
    set -Eeuo pipefail
    host="$(hostname -f 2>/dev/null || hostname)"
    [[ "$host" == *nibi* ]] || {
      echo "ERROR: connection did not reach Nibi: $host"
      exit 10
    }
    [[ -n "${SCRATCH:-}" ]] || {
      echo "ERROR: SCRATCH is not defined"
      exit 11
    }
    echo "NIBI CONNECTION: PASS"
    echo "Remote user: $USER"
    echo "Remote host: $host"
    echo "Remote scratch: $SCRATCH"
    echo "__SCRATCH__=$SCRATCH"
  '
)"
printf '%s\n' "$PREFLIGHT"
REMOTE_SCRATCH="$(
  printf '%s\n' "$PREFLIGHT" \
  | sed -n 's/^__SCRATCH__=//p' \
  | tail -n 1
)"
[[ -n "$REMOTE_SCRATCH" ]] || {
  echo "ERROR: could not parse Nibi SCRATCH"
  exit 12
}

REMOTE_TRANSFER="$REMOTE_SCRATCH/FR3_PHASE1_NIBI_SMOKE_TRANSFER_${SHORT}"
REMOTE_RETURN="$REMOTE_SCRATCH/FR3_PHASE1_NIBI_SMOKE_RETURN_${SHORT}"
REMOTE_RUN="$REMOTE_SCRATCH/FR3_PHASE1_NIBI_SMOKE_RUN_${SHORT}"
REMOTE_ENV="$REMOTE_SCRATCH/FR3_PHASE1_NIBI_ENV_${PACKAGE_ID:0:12}"

ssh "${SSH_OPTS[@]}" "$NIBI_HOST" \
  "mkdir -p '$REMOTE_TRANSFER' '$REMOTE_RETURN' '$REMOTE_ENV'; rm -f '$REMOTE_TRANSFER'/* '$REMOTE_RETURN'/*"

echo
echo "=== Transfer immutable job package and reviewed smoke package ==="
scp "${SCP_OPTS[@]}" -p \
  "$JOB_ZIP" \
  "$SMOKE_ZIP" \
  "$REMOTE_SCRIPT" \
  "$NIBI_HOST:$REMOTE_TRANSFER/"

REMOTE_SCRIPT_SHA="$(sha256sum "$REMOTE_SCRIPT" | awk '{print $1}')"
ssh "${SSH_OPTS[@]}" "$NIBI_HOST" \
  "test \"\$(sha256sum '$REMOTE_TRANSFER/$(basename "$REMOTE_SCRIPT")' | awk '{print \$1}')\" = '$REMOTE_SCRIPT_SHA'"
echo "REMOTE ORCHESTRATOR HASH: PASS"

REMOTE_COMMAND="$(
  python3 - \
    "$(basename "$JOB_ZIP")" \
    "$(basename "$SMOKE_ZIP")" \
    "$EXPECTED_JOB_SHA" \
    "$EXPECTED_SMOKE_SHA" \
    "$PACKAGE_ID" \
    "$REMOTE_TRANSFER" \
    "$REMOTE_RETURN" \
    "$REMOTE_RUN" \
    "$REMOTE_ENV" \
    "$SOURCE_COMMIT" \
    "$SMOKE_SEED" \
    "$TOKEN_TTL_HOURS" \
    "$REMOTE_TRANSFER/$(basename "$REMOTE_SCRIPT")" <<'PY'
import shlex
import sys

(
    job_name,
    smoke_name,
    job_sha,
    smoke_sha,
    package_id,
    transfer,
    returned,
    run_root,
    env_root,
    source_commit,
    smoke_seed,
    ttl,
    script,
) = sys.argv[1:]
values = {
    "JOB_ZIP_NAME": job_name,
    "SMOKE_ZIP_NAME": smoke_name,
    "EXPECTED_JOB_SHA256": job_sha,
    "EXPECTED_SMOKE_SHA256": smoke_sha,
    "EXPECTED_PACKAGE_ID": package_id,
    "TRANSFER_ABS": transfer,
    "RETURN_ABS": returned,
    "RUN_ROOT_ABS": run_root,
    "ENV_ROOT_ABS": env_root,
    "SMOKE_SOURCE_COMMIT": source_commit,
    "SMOKE_SEED": smoke_seed,
    "TOKEN_TTL_HOURS": ttl,
}
print(
    " ".join(
        f"{key}={shlex.quote(value)}"
        for key, value in values.items()
    )
    + " bash "
    + shlex.quote(script)
)
PY
)"

echo
echo "=== Execute one excluded Nibi H100 deployment smoke ==="
set +e
ssh "${SSH_OPTS[@]}" "$NIBI_HOST" "$REMOTE_COMMAND"
REMOTE_EXIT=$?
set -e
echo "Remote smoke orchestration exit code: $REMOTE_EXIT"

echo
echo "=== Retrieve compact success/diagnostic return ==="
REMOTE_FILES="$(
  ssh "${SSH_OPTS[@]}" "$NIBI_HOST" \
    "find '$REMOTE_RETURN' -maxdepth 1 -type f -printf '%f\\n' | sort"
)"
[[ -n "$REMOTE_FILES" ]] || {
  echo "ERROR: remote smoke return directory is empty"
  exit 13
}
while IFS= read -r name; do
  [[ -n "$name" ]] || continue
  scp "${SCP_OPTS[@]}" -p \
    "$NIBI_HOST:$REMOTE_RETURN/$name" \
    "$LOCAL_RETURN/"
done <<< "$REMOTE_FILES"

echo "Retrieved files:"
find "$LOCAL_RETURN" -maxdepth 1 -type f -printf '%f | %s bytes\n' | sort

for checksum in "$LOCAL_RETURN"/*.sha256; do
  [[ -f "$checksum" ]] || continue
  (
    cd "$LOCAL_RETURN"
    sha256sum -c "$(basename "$checksum")"
  )
done
for archive in "$LOCAL_RETURN"/*.zip; do
  [[ -f "$archive" ]] || continue
  unzip -t "$archive" >/dev/null
  echo "$(basename "$archive"): ZIP INTEGRITY PASS"
done

RETURN_ZIP="$(
  find "$LOCAL_RETURN" -maxdepth 1 -type f \
    -name 'FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_RETURN_*.zip' \
    -print | head -n 1
)"
if [[ "$REMOTE_EXIT" -eq 0 ]]; then
  [[ -n "$RETURN_ZIP" && -f "$RETURN_ZIP" ]] || {
    echo "ERROR: remote smoke passed but success return ZIP is missing"
    exit 14
  }
  python3 "$SMOKE_DIR/validate_smoke_return.py" \
    --return-zip "$RETURN_ZIP" \
    --smoke-tools-root "$SMOKE_DIR"

  echo
  echo "================================================================="
  echo "LOCAL NONCAMPAIGN NIBI DEPLOYMENT SMOKE: PASS"
  echo "Source commit: $SOURCE_COMMIT"
  echo "Smoke seed: $SMOKE_SEED"
  echo "Return ZIP: $RETURN_ZIP"
  echo "Return ZIP SHA-256: $(sha256sum "$RETURN_ZIP" | awk '{print $1}')"
  echo "Confirmatory analysis included: NO"
  echo "Full campaign execution authorized: NO"
  echo "Next gate: INDEPENDENTLY_REVIEW_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_RETURN"
  echo "================================================================="
else
  echo
  echo "================================================================="
  echo "LOCAL NIBI DEPLOYMENT SMOKE: DIAGNOSTIC RETURN RETRIEVED"
  echo "Remote exit code: $REMOTE_EXIT"
  echo "Local return folder: $LOCAL_RETURN"
  echo "Full campaign execution authorized: NO"
  echo "================================================================="
  exit "$REMOTE_EXIT"
fi

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
fi
