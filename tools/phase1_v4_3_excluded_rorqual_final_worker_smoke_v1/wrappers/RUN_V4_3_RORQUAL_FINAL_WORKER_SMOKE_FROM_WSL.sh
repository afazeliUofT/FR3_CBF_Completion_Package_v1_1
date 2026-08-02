#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE_ROOT="${1:?package root is required}"
PACKAGE_ROOT="$(realpath "$PACKAGE_ROOT")"
DOWNLOADS="${FR3_DOWNLOADS:-/mnt/c/Users/alifa/Downloads}"
REPO="${FR3_REPO_ROOT:?FR3_REPO_ROOT is required}"
RORQUAL_HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
RORQUAL_SCRATCH_LINK="${FR3_RORQUAL_SCRATCH_LINK:-/home/rsadve1/links/scratch}"
NIBI_HOST="${FR3_NIBI_HOST:-rsadve1@nibi.alliancecan.ca}"
SUPERSEDED_NIBI_JOB_ID="18953376"
SUPERSEDED_NIBI_RUN_ROOT="/scratch/rsadve1/FR3_V4_3_FINAL_WORKER_SMOKE_RUN_76603de75d9a_43999_20260802_032341"
BRANCH="e3-first-sector-p452"
REQUIRED_ANCESTOR="76603de75d9a1c45555d94443b5494a41275b7bb"
TOOL_DIR="tools/phase1_v4_3_excluded_rorqual_final_worker_smoke_v1"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_RETURN="$DOWNLOADS/FR3_V4_3_RORQUAL_FINAL_WORKER_SMOKE_RETURN_$STAMP"
mkdir -p "$LOCAL_RETURN"
LOCAL_LOG="$LOCAL_RETURN/LOCAL_WSL_ORCHESTRATOR.log"
exec > >(tee "$LOCAL_LOG") 2>&1

CONTROL_PATH="/tmp/fr3-v43-rorqual-final-$$-%C"
SSH_OPTS=(
  -o ControlMaster=auto
  -o ControlPersist=15m
  -o ControlPath="$CONTROL_PATH"
  -o ServerAliveInterval=60
  -o ServerAliveCountMax=30
  -o ConnectTimeout=30
)
SCP_OPTS=(
  -o ControlMaster=auto
  -o ControlPersist=15m
  -o ControlPath="$CONTROL_PATH"
  -o ServerAliveInterval=60
  -o ServerAliveCountMax=30
  -o ConnectTimeout=30
)

SOURCE_CLONE="$LOCAL_RETURN/github_source_clone"
EVIDENCE_CLONE="$LOCAL_RETURN/github_evidence_clone"
REMOTE_RC=99
RETRIEVAL_RC=99
LOCAL_VALIDATION_RC=99
SOURCE_COMMIT="NOT_CREATED"
EVIDENCE_COMMIT="NOT_CREATED"
JOB_ID="UNKNOWN"
RETURN_ZIP=""
NEXT_GATE="DIAGNOSE_FINAL_CAMPAIGN_WORKER_OR_RORQUAL_CHANNEL_REPRODUCTION_BEFORE_ANY_CAMPAIGN_AUTHORIZATION"

cleanup() {
  ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true
  ssh "${SSH_OPTS[@]}" -O exit "$NIBI_HOST" >/dev/null 2>&1 || true
  rm -rf "$SOURCE_CLONE" "$EVIDENCE_CLONE"
}
trap cleanup EXIT

local_failure() {
  local rc=$?
  trap - ERR
  printf '%s\n' \
    "LOCAL_WRAPPER_STATUS=FAIL" \
    "LOCAL_WRAPPER_EXIT_CODE=$rc" \
    "LOCAL_FAILURE_COMMAND=${BASH_COMMAND:-unknown}" \
    "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_RC" \
    "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$RETRIEVAL_RC" \
    "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO" \
    "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
  python3 "$PACKAGE_ROOT/scripts/package_local_failure.py" \
    --local-return "$LOCAL_RETURN" \
    --exit-code "$rc" \
    --command "${BASH_COMMAND:-unknown}" || true
  if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap local_failure ERR

printf '%s\n' \
  "=================================================================" \
  "FR3 V4.3 — EXCLUDED RORQUAL FINAL CAMPAIGN-WORKER SMOKE" \
  "=================================================================" \
  "PACKAGE_ROOT=$PACKAGE_ROOT" \
  "REPO=$REPO" \
  "RORQUAL_HOST=$RORQUAL_HOST" \
  "RORQUAL_SCRATCH_LINK=$RORQUAL_SCRATCH_LINK" \
  "SUPERSEDED_NIBI_JOB_ID=$SUPERSEDED_NIBI_JOB_ID" \
  "CAMPAIGN_SEED=43999" \
  "CHANNEL_GENERATED_ON_RORQUAL=YES" \
  "PRESERVED_CHANNEL_REUSED=NO" \
  "SLURM_ARRAY_USED=NO" \
  "MERGE_JOB_SUBMITTED=NO" \
  "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO" \
  "LOCAL_RETURN=$LOCAL_RETURN"

for cmd in python3 bash sha256sum unzip git ssh scp tar realpath; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR_MISSING_COMMAND=$cmd"
    exit 90
  }
done
[[ -d "$REPO/.git" ]] || {
  echo "ERROR_REPOSITORY_NOT_FOUND=$REPO"
  exit 91
}
[[ -d "$PACKAGE_ROOT" ]] || {
  echo "ERROR_PACKAGE_ROOT_NOT_FOUND=$PACKAGE_ROOT"
  exit 92
}

(
  cd "$PACKAGE_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo "INTERNAL_MANIFEST_VERIFICATION=PASS"
echo "SOURCE_PAYLOAD_MANIFEST_VERIFICATION=PASS"

if [[ -f "$REPO/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
  echo "REPO_VENV_ACTIVATED=YES"
else
  python3 -m venv "$REPO/.venv"
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
  echo "REPO_VENV_CREATED=YES"
fi
if python - <<'PY' >/dev/null 2>&1
import numpy, pandas, scipy, pytest
PY
then
  echo "LOCAL_VENV_DEPENDENCY_REUSE=PASS"
else
  python -m pip install -r "$PACKAGE_ROOT/requirements.txt"
  echo "LOCAL_VENV_DEPENDENCY_INSTALL=PASS"
fi
python -m pip check >/dev/null
echo "LOCAL_VENV_DEPENDENCY_GATE=PASS"

python - "$PACKAGE_ROOT" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
files=sorted(root.rglob('*.py'))
for path in files:
    compile(path.read_bytes(), str(path), 'exec')
print('PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS')
print(f'PYTHON_SYNTAX_FILE_COUNT={len(files)}')
PY
while IFS= read -r script; do bash -n "$script"; done < <(find "$PACKAGE_ROOT" -type f -name '*.sh' -print | sort)
echo "BASH_SYNTAX_CHECK=PASS"
python -m pytest -q "$PACKAGE_ROOT/tests"

python "$PACKAGE_ROOT/scripts/audit_locked_campaign_inputs.py" \
  --package-root "$PACKAGE_ROOT" \
  --output "$LOCAL_RETURN/LOCKED_CAMPAIGN_INPUT_AUDIT.json" \
  | tee "$LOCAL_RETURN/LOCKED_CAMPAIGN_INPUT_AUDIT.log"
echo "LOCAL_QUALITY_GATE=PASS"

echo "SUPERSEDED_NIBI_SMOKE_CANCELLATION_BEGIN=YES"
if NIBI_CANCEL_OUTPUT="$(
  ssh "${SSH_OPTS[@]}" "$NIBI_HOST" \
    "SUPERSEDED_JOB_ID='$SUPERSEDED_NIBI_JOB_ID' SUPERSEDED_RUN_ROOT='$SUPERSEDED_NIBI_RUN_ROOT' bash -s" <<'NIBI_CANCEL'
set -Eeuo pipefail
job="${SUPERSEDED_JOB_ID:?}"
run_root="${SUPERSEDED_RUN_ROOT:?}"
host="$(hostname -f 2>/dev/null || hostname)"
[[ "$host" == *nibi* ]] || {
  echo "ERROR_CANCELLATION_HOST_NOT_NIBI=$host"
  exit 31
}
state="$(squeue -h -j "$job" -o '%T' 2>/dev/null | head -n1 || true)"
printf '%s\n' \
  "NIBI_CANCELLATION_HOST=$host" \
  "SUPERSEDED_NIBI_JOB_ID=$job" \
  "SUPERSEDED_NIBI_INITIAL_STATE=${state:-NOT_IN_SQUEUE}"
case "$state" in
  PENDING|RUNNING|CONFIGURING|COMPLETING|SUSPENDED)
    scancel "$job"
    echo "SUPERSEDED_NIBI_SCANCEL_ISSUED=YES"
    ;;
  *)
    echo "SUPERSEDED_NIBI_SCANCEL_ISSUED=NO_ALREADY_TERMINAL_OR_ABSENT"
    ;;
esac
for _attempt in $(seq 1 60); do
  active="$(squeue -h -j "$job" -o '%T' 2>/dev/null | head -n1 || true)"
  [[ -z "$active" ]] && break
  sleep 2
done
active="$(squeue -h -j "$job" -o '%T' 2>/dev/null | head -n1 || true)"
[[ -z "$active" ]] || {
  echo "ERROR_SUPERSEDED_NIBI_JOB_STILL_ACTIVE=$active"
  exit 32
}
token="$run_root/provenance/FINAL_WORKER_SMOKE_AUTHORIZATION.json"
rm -f -- "$token"
[[ ! -e "$token" ]]
echo "SUPERSEDED_NIBI_AUTHORIZATION_TOKEN_DELETED=PASS"
{
  echo "SUPERSEDED_NIBI_SACCT_BEGIN"
  sacct -X -j "$job" \
    --format=JobID,JobName,Account,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES -P \
    2>&1 || true
  echo "SUPERSEDED_NIBI_SACCT_END"
}
final_state="$(
  sacct -n -X -j "$job" --format=State -P 2>/dev/null \
    | head -n1 | cut -d'|' -f1 | xargs
)"
echo "SUPERSEDED_NIBI_FINAL_STATE=${final_state:-UNKNOWN_OR_NOT_YET_ACCOUNTED}"
echo "SUPERSEDED_NIBI_SMOKE_CANCELLATION=PASS"
echo "SUPERSEDED_NIBI_RESULT_CLASSIFICATION=ROUTING_CORRECTION_NOT_SCIENTIFIC_EVIDENCE"
NIBI_CANCEL
)"; then
  printf '%s\n' "$NIBI_CANCEL_OUTPUT" | tee "$LOCAL_RETURN/SUPERSEDED_NIBI_CANCELLATION.log"
else
  NIBI_CANCEL_RC=$?
  printf '%s\n' "$NIBI_CANCEL_OUTPUT" | tee "$LOCAL_RETURN/SUPERSEDED_NIBI_CANCELLATION.log"
  echo "SUPERSEDED_NIBI_SMOKE_CANCELLATION=FAIL"
  exit "$NIBI_CANCEL_RC"
fi
echo "SUPERSEDED_NIBI_SMOKE_CANCELLATION_END=YES"

ARCHIVE_PATH="${FR3_SMOKE_ARCHIVE_PATH:-}"
ARCHIVE_SHA="${FR3_SMOKE_ARCHIVE_SHA256:-}"
if [[ -z "$ARCHIVE_PATH" || ! -f "$ARCHIVE_PATH" ]]; then
  CANONICAL_NAME="$(python - "$PACKAGE_ROOT/PACKAGE_VERSION.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['package_name']+'.zip')
PY
)"
  ARCHIVE_PATH="$DOWNLOADS/$CANONICAL_NAME"
fi
[[ -f "$ARCHIVE_PATH" ]] || {
  echo "ERROR_ORIGINAL_SMOKE_ARCHIVE_NOT_FOUND=$ARCHIVE_PATH"
  exit 93
}
ACTUAL_ARCHIVE_SHA="$(sha256sum "$ARCHIVE_PATH" | awk '{print $1}')"
if [[ -n "$ARCHIVE_SHA" ]]; then
  [[ "$ACTUAL_ARCHIVE_SHA" == "$ARCHIVE_SHA" ]]
else
  ARCHIVE_SHA="$ACTUAL_ARCHIVE_SHA"
fi
echo "SMOKE_PACKAGE_ARCHIVE=$ARCHIVE_PATH"
echo "SMOKE_PACKAGE_ARCHIVE_SHA256=$ARCHIVE_SHA"

ORIGIN="$(git -C "$REPO" remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR_UNEXPECTED_GIT_ORIGIN=$ORIGIN"
  exit 94
}

git clone --branch "$BRANCH" --single-branch "$ORIGIN" "$SOURCE_CLONE"
git -C "$SOURCE_CLONE" fetch origin "$BRANCH"
git -C "$SOURCE_CLONE" reset --hard "origin/$BRANCH"
GIT_HEAD_BEFORE="$(git -C "$REPO" rev-parse HEAD)"
GIT_REMOTE_HEAD_BEFORE="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
echo "GIT_HEAD_BEFORE=$GIT_HEAD_BEFORE"
echo "GIT_REMOTE_HEAD_BEFORE=$GIT_REMOTE_HEAD_BEFORE"
git -C "$SOURCE_CLONE" merge-base --is-ancestor "$REQUIRED_ANCESTOR" HEAD
echo "GITHUB_REQUIRED_ANCESTOR_GATE=PASS"

EXISTING_SMOKE_EVIDENCE="$(
  find "$SOURCE_CLONE/evidence" -mindepth 1 -maxdepth 1 -type d \
    -name 'phase1_v4_3_rorqual_final_worker_smoke_v1_job_*' -print 2>/dev/null \
    | sort | head -n1
)"
if [[ -n "$EXISTING_SMOKE_EVIDENCE" ]]; then
  echo "ERROR_EXISTING_FINAL_WORKER_SMOKE_EVIDENCE=$EXISTING_SMOKE_EVIDENCE"
  echo "AUTOMATIC_SMOKE_RERUN_AUTHORIZED=NO"
  exit 97
fi
echo "NO_PRIOR_FINAL_WORKER_SMOKE_EVIDENCE_GATE=PASS"

git -C "$SOURCE_CLONE" config user.name "Ali Fazeli"
git -C "$SOURCE_CLONE" config user.email "ali.fazeli@utoronto.ca"
TARGET="$SOURCE_CLONE/$TOOL_DIR"
if [[ -e "$TARGET" ]]; then
  if diff -qr "$PACKAGE_ROOT/repo_payload" "$TARGET" >/dev/null; then
    echo "GITHUB_SMOKE_SOURCE_ALREADY_IDENTICAL=YES"
  else
    echo "ERROR_GITHUB_TOOL_VERSION_COLLISION=$TOOL_DIR"
    exit 95
  fi
else
  mkdir -p "$(dirname "$TARGET")"
  cp -a "$PACKAGE_ROOT/repo_payload" "$TARGET"
fi

git -C "$SOURCE_CLONE" add "$TOOL_DIR"
git -C "$SOURCE_CLONE" diff --cached --check
if git -C "$SOURCE_CLONE" diff --cached --quiet; then
  SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
else
  git -C "$SOURCE_CLONE" commit -m "Add excluded Rorqual final campaign-worker smoke for candidate-v4.3"
  if git -C "$SOURCE_CLONE" push origin "HEAD:$BRANCH"; then
    :
  else
    git -C "$SOURCE_CLONE" fetch origin "$BRANCH"
    git -C "$SOURCE_CLONE" rebase "origin/$BRANCH"
    git -C "$SOURCE_CLONE" push origin "HEAD:$BRANCH"
  fi
  SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
fi
git -C "$SOURCE_CLONE" fetch origin "$BRANCH"
[[ "$SOURCE_COMMIT" == "$(git -C "$SOURCE_CLONE" rev-parse "origin/$BRANCH")" ]]
echo "SMOKE_SOURCE_COMMIT=$SOURCE_COMMIT"
echo "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

PREFLIGHT="$(
  ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
    "RORQUAL_SCRATCH_LINK='$RORQUAL_SCRATCH_LINK' bash -s" <<'RORQUAL_PREFLIGHT'
set -Eeuo pipefail
host="$(hostname -f 2>/dev/null || hostname)"
[[ "$host" == *rorqual* ]]
scratch="$(realpath -e "$RORQUAL_SCRATCH_LINK")"
[[ -d "$scratch" ]]
echo "RORQUAL_CONNECTION=PASS"
echo "RORQUAL_REMOTE_USER=$USER"
echo "RORQUAL_REMOTE_HOST=$host"
echo "RORQUAL_REMOTE_SCRATCH=$scratch"
echo "__SCRATCH__=$scratch"
RORQUAL_PREFLIGHT
)"
printf '%s\n' "$PREFLIGHT"
REMOTE_SCRATCH="$(printf '%s\n' "$PREFLIGHT" | sed -n 's/^__SCRATCH__=//p' | tail -n1)"
[[ -n "$REMOTE_SCRATCH" ]]

SHORT="${SOURCE_COMMIT:0:12}_43999_${STAMP}"
REMOTE_TRANSFER="$REMOTE_SCRATCH/FR3_V4_3_FINAL_WORKER_SMOKE_TRANSFER_$SHORT"
REMOTE_RETURN="$REMOTE_SCRATCH/FR3_V4_3_FINAL_WORKER_SMOKE_RETURN_$SHORT"
REMOTE_RUN="$REMOTE_SCRATCH/FR3_V4_3_FINAL_WORKER_SMOKE_RUN_$SHORT"
REMOTE_ENV="$REMOTE_SCRATCH/FR3_PHASE1_RORQUAL_ENV_5037b4e33448"
REMOTE_SCRIPT="$PACKAGE_ROOT/wrappers/REMOTE_ORCHESTRATE_V4_3_RORQUAL_FINAL_WORKER_SMOKE.sh"
REMOTE_SCRIPT_SHA="$(sha256sum "$REMOTE_SCRIPT" | awk '{print $1}')"

ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
  "mkdir -p '$REMOTE_TRANSFER' '$REMOTE_RETURN' '$REMOTE_ENV'; rm -f '$REMOTE_TRANSFER'/* '$REMOTE_RETURN'/*"
scp "${SCP_OPTS[@]}" -p "$ARCHIVE_PATH" "$REMOTE_SCRIPT" "$RORQUAL_HOST:$REMOTE_TRANSFER/"
ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
  "test \"\$(sha256sum '$REMOTE_TRANSFER/$(basename "$REMOTE_SCRIPT")' | awk '{print \$1}')\" = '$REMOTE_SCRIPT_SHA'"
echo "REMOTE_ORCHESTRATOR_HASH_VERIFICATION=PASS"

REMOTE_COMMAND="$(
  python - \
    "$(basename "$ARCHIVE_PATH")" "$ARCHIVE_SHA" \
    "$REMOTE_TRANSFER" "$REMOTE_RETURN" "$REMOTE_RUN" "$REMOTE_ENV" "$REMOTE_SCRATCH" \
    "$SOURCE_COMMIT" "168" "$REMOTE_TRANSFER/$(basename "$REMOTE_SCRIPT")" <<'PY'
import shlex,sys
(zip_name,zip_sha,transfer,returned,run,env,scratch,commit,ttl,script)=sys.argv[1:]
values={
 'SMOKE_ZIP_NAME':zip_name,
 'EXPECTED_SMOKE_ZIP_SHA256':zip_sha,
 'TRANSFER_ABS':transfer,
 'RETURN_ABS':returned,
 'RUN_ROOT_ABS':run,
 'ENV_ROOT_ABS':env,
 'SMOKE_SOURCE_COMMIT':commit,
 'TOKEN_TTL_HOURS':ttl,
 'SCRATCH_ROOT_ABS':scratch,
}
print(' '.join(f'{k}={shlex.quote(v)}' for k,v in values.items())+' bash '+shlex.quote(script))
PY
)"

if ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" "$REMOTE_COMMAND" \
    | tee "$LOCAL_RETURN/REMOTE_ORCHESTRATOR.log"
then
  REMOTE_RC=0
else
  REMOTE_RC=${PIPESTATUS[0]}
fi
echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_RC"

if REMOTE_FILES="$(
  ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
    "find '$REMOTE_RETURN' -maxdepth 1 -type f -printf '%f\\n' | sort"
)"
then
  RETRIEVAL_RC=0
else
  RETRIEVAL_RC=$?
  REMOTE_FILES=""
fi
if [[ -n "$REMOTE_FILES" ]]; then
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    if scp "${SCP_OPTS[@]}" -p "$RORQUAL_HOST:$REMOTE_RETURN/$name" "$LOCAL_RETURN/"; then
      :
    else
      RETRIEVAL_RC=$?
    fi
  done <<< "$REMOTE_FILES"
fi
echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$RETRIEVAL_RC"

for sidecar in "$LOCAL_RETURN"/*.zip.sha256; do
  [[ -f "$sidecar" ]] || continue
  (
    cd "$LOCAL_RETURN"
    sha256sum -c "$(basename "$sidecar")"
  )
done
for archive in "$LOCAL_RETURN"/*.zip; do
  [[ -f "$archive" ]] || continue
  unzip -t "$archive" >/dev/null
  echo "RETURN_ZIP_CRC_PASS=$(basename "$archive")"
done

RETURN_ZIP="$(
  find "$LOCAL_RETURN" -maxdepth 1 -type f \
    -name 'FR3_RORQUAL_V4_3_FINAL_WORKER_SMOKE_43999_*.zip' \
    ! -name '*EMERGENCY*' -print | sort | head -n1
)"
if [[ -z "$RETURN_ZIP" ]]; then
  RETURN_ZIP="$(find "$LOCAL_RETURN" -maxdepth 1 -type f -name '*.zip' -print | sort | head -n1)"
fi
if [[ -n "$RETURN_ZIP" && -f "$RETURN_ZIP" ]]; then
  if python "$PACKAGE_ROOT/scripts/validate_final_worker_smoke_return.py" \
      --return-zip "$RETURN_ZIP" \
      | tee "$LOCAL_RETURN/LOCAL_RETURN_VALIDATION.log"
  then
    LOCAL_VALIDATION_RC=0
  else
    LOCAL_VALIDATION_RC=${PIPESTATUS[0]}
  fi
else
  LOCAL_VALIDATION_RC=98
fi
echo "LOCAL_RETURN_VALIDATION_EXIT_CODE=$LOCAL_VALIDATION_RC"

if [[ -n "$RETURN_ZIP" && -f "$RETURN_ZIP" ]]; then
  JOB_ID="$(basename "$RETURN_ZIP" | sed -n 's/^FR3_RORQUAL_V4_3_FINAL_WORKER_SMOKE_43999_\([0-9][0-9]*\)\.zip$/\1/p')"
  [[ -n "$JOB_ID" ]] || JOB_ID="UNKNOWN"
  RETURN_EXTRACT="$LOCAL_RETURN/return_extract"
  rm -rf "$RETURN_EXTRACT" && mkdir -p "$RETURN_EXTRACT"
  unzip -q "$RETURN_ZIP" -d "$RETURN_EXTRACT"
  RETURN_ROOT="$(find "$RETURN_EXTRACT" -mindepth 1 -maxdepth 1 -type d -print | head -n1)"
  if [[ -f "$RETURN_ROOT/RETURN_METADATA.json" ]]; then
    NEXT_GATE="$(python - "$RETURN_ROOT/RETURN_METADATA.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['next_gate'])
PY
)"
  fi

  python - "$RETURN_ROOT" "$LOCAL_RETURN/PARSED_RETURN_VALUES.env" <<'PY'
from pathlib import Path
import json,sys
root=Path(sys.argv[1]); output=Path(sys.argv[2])
def read_env(path):
    values={}
    if path.is_file():
        for raw in path.read_text(encoding='utf-8').splitlines():
            if '=' in raw:
                key,value=raw.split('=',1); values[key]=value
    return values
def emit(key,value):
    return f"{key}={value}"
metadata=json.load(open(root/'RETURN_METADATA.json',encoding='utf-8'))
audit_path=root/'provenance/FINAL_WORKER_SMOKE_AUDIT.json'
audit=json.load(open(audit_path,encoding='utf-8')) if audit_path.is_file() else {}
remote=read_env(root/'provenance/REMOTE_RUN_SUMMARY.env')
environment_path=root/'provenance/RORQUAL_H100_ENVIRONMENT.json'
environment=json.load(open(environment_path,encoding='utf-8')) if environment_path.is_file() else {}
lines=[
    emit('RETURN_STATUS',metadata.get('status','NOT_AVAILABLE')),
    emit('FINAL_WORKER_SMOKE_STATUS',audit.get('status','NOT_AVAILABLE')),
    emit('SLURM_ACCOUNT',remote.get('SLURM_ACCOUNT','NOT_AVAILABLE')),
    emit('SLURM_STATE',remote.get('SLURM_STATE',metadata.get('slurm_state','NOT_AVAILABLE'))),
    emit('SLURM_EXIT_CODE',remote.get('SLURM_EXIT_CODE',metadata.get('slurm_exit_code','NOT_AVAILABLE'))),
    emit('SLURM_MAXRSS',remote.get('SLURM_MAXRSS','NOT_AVAILABLE')),
    emit('FINAL_WORKER_EXIT_CODE',metadata.get('worker_exit_code','NOT_AVAILABLE')),
    emit('STRUCTURAL_VALIDATOR_EXIT_CODE',metadata.get('structural_validator_exit_code','NOT_AVAILABLE')),
    emit('SCIENTIFIC_PASS_VALIDATOR_EXIT_CODE',metadata.get('scientific_pass_validator_exit_code','NOT_AVAILABLE')),
    emit('INDEPENDENT_AUDIT_EXIT_CODE',metadata.get('independent_audit_exit_code','NOT_AVAILABLE')),
    emit('RORQUAL_H100_FINAL_WORKER_ENVIRONMENT_GATE','PASS' if environment.get('status')=='PASS_RORQUAL_H100_FINAL_WORKER_ENVIRONMENT' else 'FAIL_OR_MISSING'),
    emit('RORQUAL_EXACT_REFERENCE_ENVIRONMENT_GATE',environment.get('exact_reference_environment_gate','NOT_AVAILABLE')),
    emit('CHANNEL_EXACT_REFERENCE_GATE',audit.get('channel_exact_reference_gate','NOT_AVAILABLE')),
    emit('COMPARATOR_REFERENCE_SUMMARY_GATE',audit.get('comparator_reference_summary_gate','NOT_AVAILABLE')),
    emit('CANDIDATE_REFERENCE_TRACE_GATE',audit.get('candidate_reference_trace_gate','NOT_AVAILABLE')),
    emit('CANDIDATE_ACTION_CLASS_TRACE_EXACT',audit.get('candidate_action_class_trace_exact','NOT_AVAILABLE')),
    emit('CANDIDATE_TRACE_MAXIMUM_ABSOLUTE_ERROR',audit.get('candidate_trace_maximum_absolute_error','NOT_AVAILABLE')),
    emit('CANDIDATE_HARD_GATES',audit.get('candidate_hard_gates','NOT_AVAILABLE')),
    emit('CANDIDATE_FLOOR_VIOLATION_USER_SECONDS',audit.get('candidate_floor_violation_user_seconds','NOT_AVAILABLE')),
    emit('CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS',audit.get('candidate_floor_violation_user_intervals','NOT_AVAILABLE')),
    emit('CANDIDATE_LONG_EESS_VIOLATION_SECONDS',audit.get('candidate_long_eess_violation_seconds','NOT_AVAILABLE')),
    emit('CANDIDATE_SHORT_EESS_VIOLATION_SECONDS',audit.get('candidate_short_eess_violation_seconds','NOT_AVAILABLE')),
    emit('CANDIDATE_LOCAL_GRID_REPAIR_INTERVALS',audit.get('candidate_local_grid_repair_intervals','NOT_AVAILABLE')),
    emit('CANDIDATE_LOCAL_STREAM_REPAIR_INTERVALS',audit.get('candidate_local_stream_repair_intervals','NOT_AVAILABLE')),
    emit('CANDIDATE_UNRESOLVED_INTERVALS',audit.get('candidate_unresolved_intervals','NOT_AVAILABLE')),
    emit('CANDIDATE_NETWORK_WIDE_SHUTDOWN_INTERVALS',audit.get('candidate_network_wide_shutdown_intervals','NOT_AVAILABLE')),
    emit('CANDIDATE_MAXIMUM_STRICT_POST_MODE_POWER_RATIO',audit.get('candidate_maximum_strict_post_mode_power_ratio','NOT_AVAILABLE')),
    emit('GENERATED_CHANNEL_RECORD_SHA256',audit.get('generated_channel_record_sha256','NOT_AVAILABLE')),
    emit('GENERATED_FREQUENCY_RESPONSE_FILE_SHA256',audit.get('generated_frequency_response_file_sha256','NOT_AVAILABLE')),
    emit('GENERATED_FREQUENCY_RESPONSE_ARRAY_SHA256',audit.get('generated_frequency_response_array_sha256','NOT_AVAILABLE')),
    emit('INFORMATION_EXCHANGE_LOCALITY_CERTIFIED','YES' if audit.get('information_exchange_locality_certified') else 'NO'),
    emit('FULL_CAMPAIGN_EXECUTION_AUTHORIZED','YES' if metadata.get('full_campaign_execution_authorized') else 'NO'),
    emit('NEXT_GATE',metadata.get('next_gate','NOT_AVAILABLE')),
]
output.write_text('\n'.join(lines)+'\n',encoding='utf-8')
PY
  cat "$LOCAL_RETURN/PARSED_RETURN_VALUES.env"

  git clone --branch "$BRANCH" --single-branch "$ORIGIN" "$EVIDENCE_CLONE"
  git -C "$EVIDENCE_CLONE" config user.name "Ali Fazeli"
  git -C "$EVIDENCE_CLONE" config user.email "ali.fazeli@utoronto.ca"
  git -C "$EVIDENCE_CLONE" merge-base --is-ancestor "$SOURCE_COMMIT" HEAD
  EVIDENCE_DIR="$EVIDENCE_CLONE/evidence/phase1_v4_3_rorqual_final_worker_smoke_v1_job_${JOB_ID}"
  [[ ! -e "$EVIDENCE_DIR" ]] || {
    echo "ERROR_EVIDENCE_DIRECTORY_ALREADY_EXISTS=$EVIDENCE_DIR"
    exit 96
  }
  mkdir -p "$EVIDENCE_DIR"
  cp -p "$RETURN_ZIP.sha256" "$EVIDENCE_DIR/"
  cp -p "$LOCAL_LOG" "$EVIDENCE_DIR/LOCAL_WSL_ORCHESTRATOR.log"
  cp -p "$LOCAL_RETURN/PARSED_RETURN_VALUES.env" "$EVIDENCE_DIR/"
  cp -p "$LOCAL_RETURN/SUPERSEDED_NIBI_CANCELLATION.log" "$EVIDENCE_DIR/"
  cp -p "$PACKAGE_ROOT/immutable_bindings/ROUTING_CORRECTION_RECORD.json" "$EVIDENCE_DIR/"
  for relative in \
    RETURN_METADATA.json \
    RETURN_MANIFEST.sha256 \
    channel/CHANNEL_RECORD.json \
    provenance/FINAL_WORKER_SMOKE_AUDIT.json \
    provenance/FINAL_WORKER_SMOKE_AUTHORIZATION_RECORD.json \
    provenance/RORQUAL_H100_ENVIRONMENT.json \
    provenance/REMOTE_RUN_SUMMARY.env \
    provenance/JOB_EXIT_SUMMARY.env \
    result/SEED_RESULT.json \
    result/RESULT_FILE_MANIFEST.json \
    result/CELL_SUMMARY.csv \
    result/PRIMARY_PAIRED_EFFECTS.csv
  do
    if [[ -f "$RETURN_ROOT/$relative" ]]; then
      mkdir -p "$EVIDENCE_DIR/$(dirname "$relative")"
      cp -p "$RETURN_ROOT/$relative" "$EVIDENCE_DIR/$relative"
    fi
  done
  if compgen -G "$RETURN_ROOT/logs/sacct-*.txt" >/dev/null; then
    mkdir -p "$EVIDENCE_DIR/logs"
    cp -p "$RETURN_ROOT"/logs/sacct-*.txt "$EVIDENCE_DIR/logs/"
  fi
  python - "$EVIDENCE_DIR" "$RETURN_ROOT/RETURN_METADATA.json" "$(sha256sum "$RETURN_ZIP" | awk '{print $1}')" <<'PY'
from pathlib import Path
import hashlib,json,sys
root=Path(sys.argv[1]); metadata=json.load(open(sys.argv[2],encoding='utf-8'))
status={
 'schema_version':1,
 'status':'COLLECTED_FOR_INDEPENDENT_REVIEW',
 'scientific_status':metadata.get('scientific_smoke_status'),
 'return_status':metadata.get('status'),
 'return_zip_sha256':sys.argv[3],
 'job_id':metadata.get('job_id'),
 'campaign_seed':43999,
 'full_campaign_execution_authorized':False,
 'next_gate':metadata.get('next_gate'),
}
(root/'COLLECTION_STATUS.json').write_text(json.dumps(status,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def sha(path):
 h=hashlib.sha256();
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
lines=[]
for path in sorted(root.rglob('*')):
 if path.is_file() and path.name!='EVIDENCE_MANIFEST.sha256': lines.append(f'{sha(path)}  {path.relative_to(root).as_posix()}')
(root/'EVIDENCE_MANIFEST.sha256').write_text('\n'.join(lines)+'\n',encoding='utf-8')
PY
  git -C "$EVIDENCE_CLONE" add "evidence/phase1_v4_3_rorqual_final_worker_smoke_v1_job_${JOB_ID}"
  git -C "$EVIDENCE_CLONE" diff --cached --check
  git -C "$EVIDENCE_CLONE" commit -m "Collect candidate-v4.3 Rorqual final-worker smoke evidence"
  if git -C "$EVIDENCE_CLONE" push origin "HEAD:$BRANCH"; then
    :
  else
    git -C "$EVIDENCE_CLONE" fetch origin "$BRANCH"
    git -C "$EVIDENCE_CLONE" rebase "origin/$BRANCH"
    git -C "$EVIDENCE_CLONE" push origin "HEAD:$BRANCH"
  fi
  EVIDENCE_COMMIT="$(git -C "$EVIDENCE_CLONE" rev-parse HEAD)"
  git -C "$EVIDENCE_CLONE" fetch origin "$BRANCH"
  [[ "$EVIDENCE_COMMIT" == "$(git -C "$EVIDENCE_CLONE" rev-parse "origin/$BRANCH")" ]]
fi

GIT_REMOTE_FINAL_COMMIT="$(git ls-remote "$ORIGIN" "refs/heads/$BRANCH" | awk '{print $1}')"
RETURN_SHA="NOT_AVAILABLE"
[[ -n "$RETURN_ZIP" && -f "$RETURN_ZIP" ]] && RETURN_SHA="$(sha256sum "$RETURN_ZIP" | awk '{print $1}')"

printf '%s\n' \
  "=================================================================" \
  "FR3 V4.3 — RORQUAL FINAL WORKER SMOKE FINAL REPORT" \
  "=================================================================" \
  "LOCAL_WRAPPER_EXIT_CODE=$REMOTE_RC" \
  "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_RC" \
  "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$RETRIEVAL_RC" \
  "LOCAL_RETURN_VALIDATION_EXIT_CODE=$LOCAL_VALIDATION_RC" \
  "SLURM_JOB_ID=$JOB_ID" \
  "SMOKE_SOURCE_COMMIT=$SOURCE_COMMIT" \
  "GIT_EVIDENCE_COMMIT=$EVIDENCE_COMMIT" \
  "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT" \
  "GITHUB_NEWER_WORK_OVERWRITTEN=NO" \
  "SUPERSEDED_NIBI_JOB_ID=$SUPERSEDED_NIBI_JOB_ID" \
  "SUPERSEDED_NIBI_SMOKE_CANCELLATION=PASS" \
  "LOCAL_RETURN_ZIP=$RETURN_ZIP" \
  "LOCAL_RETURN_ZIP_SHA256=$RETURN_SHA" \
  "CHANNEL_GENERATED_ON_RORQUAL=YES" \
  "PRESERVED_CHANNEL_REUSED=NO" \
  "SLURM_ARRAY_USED=NO" \
  "MERGE_JOB_SUBMITTED=NO" \
  "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO" \
  "NEXT_GATE=$NEXT_GATE" \
  "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN" \
  "WSL_TERMINAL_CLOSE_REQUESTED=NO"

if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
fi

if [[ "$REMOTE_RC" -eq 0 && "$RETRIEVAL_RC" -eq 0 && "$LOCAL_VALIDATION_RC" -eq 0 ]]; then
  exit 0
fi
[[ "$REMOTE_RC" -ne 0 ]] && exit "$REMOTE_RC"
[[ "$RETRIEVAL_RC" -ne 0 ]] && exit "$RETRIEVAL_RC"
exit "$LOCAL_VALIDATION_RC"
