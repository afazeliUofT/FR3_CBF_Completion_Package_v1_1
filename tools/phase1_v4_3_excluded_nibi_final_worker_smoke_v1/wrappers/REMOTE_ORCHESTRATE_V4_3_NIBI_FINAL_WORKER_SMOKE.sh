#!/usr/bin/env bash
set -Eeuo pipefail

: "${SMOKE_ZIP_NAME:?SMOKE_ZIP_NAME is required}"
: "${EXPECTED_SMOKE_ZIP_SHA256:?EXPECTED_SMOKE_ZIP_SHA256 is required}"
: "${TRANSFER_ABS:?TRANSFER_ABS is required}"
: "${RETURN_ABS:?RETURN_ABS is required}"
: "${RUN_ROOT_ABS:?RUN_ROOT_ABS is required}"
: "${ENV_ROOT_ABS:?ENV_ROOT_ABS is required}"
: "${SMOKE_SOURCE_COMMIT:?SMOKE_SOURCE_COMMIT is required}"
: "${TOKEN_TTL_HOURS:?TOKEN_TTL_HOURS is required}"

HOST_FULL="$(hostname -f 2>/dev/null || hostname)"
[[ "$HOST_FULL" == *nibi* ]] || {
  echo "ERROR_REMOTE_HOST_NOT_NIBI=$HOST_FULL"
  exit 20
}
[[ -n "${SCRATCH:-}" ]] || {
  echo "ERROR_NIBI_SCRATCH_UNDEFINED=YES"
  exit 21
}

TRANSFER="$TRANSFER_ABS"
RETURN_HOME="$RETURN_ABS"
RUN_ROOT="$RUN_ROOT_ABS"
ENV_ROOT="$ENV_ROOT_ABS"
VENV="$ENV_ROOT/venv"
SMOKE_ZIP="$TRANSFER/$SMOKE_ZIP_NAME"
SMOKE_EXTRACT="$RUN_ROOT/smoke_extract"
SMOKE_ROOT=""
JOB_ROOT="$RUN_ROOT/locked_job"
PROVENANCE="$RUN_ROOT/provenance"
LOGS="$RUN_ROOT/logs"
JOB_ID="NOT_SUBMITTED"
SLURM_STATE="NOT_SUBMITTED"
SLURM_EXIT_CODE="NOT_AVAILABLE"
SLURM_MAXRSS="NOT_AVAILABLE"
FINAL_WORKER_RC=99
STRUCTURAL_RC=99
PASS_VALIDATOR_RC=99
AUDIT_RC=99
TOKEN=""

mkdir -p "$TRANSFER" "$RETURN_HOME" "$ENV_ROOT"
rm -rf "$RUN_ROOT"
mkdir -p "$RUN_ROOT" "$SMOKE_EXTRACT" "$JOB_ROOT" "$PROVENANCE" "$LOGS"
rm -f "$RETURN_HOME"/*

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1

build_emergency_return() {
  local code="$1"
  local output="$RETURN_HOME/FR3_NIBI_V4_3_FINAL_WORKER_SMOKE_43999_${JOB_ID}_EMERGENCY.zip"
  python3 - "$RUN_ROOT" "$output" "$code" "$JOB_ID" "$SLURM_STATE" <<'PY' || true
from pathlib import Path
import hashlib
import sys
import zipfile
run=Path(sys.argv[1]); out=Path(sys.argv[2]); code,job,state=sys.argv[3:]
files=[]
for root in [run/'logs', run/'provenance']:
    if root.is_dir():
        for path in sorted(root.rglob('*')):
            if path.is_file() and 'AUTHORIZATION.json' not in path.name:
                files.append((path,path.relative_to(run).as_posix()))
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for path,rel in files: z.write(path,rel)
    z.writestr('EMERGENCY_STATUS.env',f'EXIT_CODE={code}\nSLURM_JOB_ID={job}\nSLURM_STATE={state}\nFULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO\n')
h=hashlib.sha256(out.read_bytes()).hexdigest()
Path(str(out)+'.sha256').write_text(f'{h}  {out.name}\n',encoding='utf-8')
PY
}

remote_failure() {
  local code=$?
  trap - ERR
  {
    echo "REMOTE_ORCHESTRATOR_STATUS=FAIL"
    echo "REMOTE_ORCHESTRATOR_EXIT_CODE=$code"
    echo "REMOTE_FAILURE_COMMAND=${BASH_COMMAND:-unknown}"
    echo "SLURM_JOB_ID=$JOB_ID"
    echo "SLURM_STATE=$SLURM_STATE"
    echo "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO"
    date -u '+CREATED_UTC=%Y-%m-%dT%H:%M:%SZ'
  } > "$RETURN_HOME/REMOTE_FAILURE_STATUS.env"
  [[ -n "$TOKEN" ]] && rm -f "$TOKEN" || true
  build_emergency_return "$code"
  echo "REMOTE_ORCHESTRATOR_EXIT_CODE=$code"
  echo "REMOTE_RETURN_DIRECTORY=$RETURN_HOME"
  exit "$code"
}
trap remote_failure ERR

printf '%s\n' \
  "REMOTE_HOST=$HOST_FULL" \
  "REMOTE_SCRATCH=$SCRATCH" \
  "EXECUTION_STAGE=EXCLUDED_FINAL_WORKER_SMOKE_SEED43999" \
  "CAMPAIGN_SEED=43999" \
  "CHANNEL_GENERATED_ON_NIBI=YES" \
  "PRESERVED_CHANNEL_REUSED=NO" \
  "SLURM_ARRAY_USED=NO" \
  "MERGE_JOB_SUBMITTED=NO" \
  "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO"

[[ -f "$SMOKE_ZIP" ]] || {
  echo "ERROR_TRANSFERRED_SMOKE_ZIP_MISSING=$SMOKE_ZIP"
  exit 22
}
ACTUAL_SMOKE_SHA="$(sha256sum "$SMOKE_ZIP" | awk '{print $1}')"
echo "EXPECTED_SMOKE_ZIP_SHA256=$EXPECTED_SMOKE_ZIP_SHA256"
echo "ACTUAL_SMOKE_ZIP_SHA256=$ACTUAL_SMOKE_SHA"
[[ "$ACTUAL_SMOKE_SHA" == "$EXPECTED_SMOKE_ZIP_SHA256" ]]
unzip -t "$SMOKE_ZIP" >/dev/null
unzip -q "$SMOKE_ZIP" -d "$SMOKE_EXTRACT"
mapfile -t ROOTS < <(find "$SMOKE_EXTRACT" -mindepth 1 -maxdepth 1 -type d -printf '%p\n')
[[ "${#ROOTS[@]}" -eq 1 ]]
SMOKE_ROOT="${ROOTS[0]}"
(
  cd "$SMOKE_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo "REMOTE_SMOKE_PACKAGE_MANIFEST_VERIFICATION=PASS"

python3 "$SMOKE_ROOT/scripts/audit_locked_campaign_inputs.py" \
  --package-root "$SMOKE_ROOT" \
  --output "$PROVENANCE/LOCKED_CAMPAIGN_INPUT_AUDIT.json" \
  | tee "$PROVENANCE/locked_campaign_input_audit.log"

CONTRACT="$SMOKE_ROOT/config/FINAL_WORKER_SMOKE_CONTRACT.json"
mapfile -t CONTRACT_VALUES < <(
  python3 - "$CONTRACT" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
print(v['locked_job_package']['filename'])
print(v['locked_job_package']['sha256'])
print(v['locked_job_package']['package_id'])
print(v['execution']['seed'])
print(v['authorization']['token_ttl_hours'])
PY
)
JOB_ZIP_NAME="${CONTRACT_VALUES[0]}"
EXPECTED_JOB_SHA="${CONTRACT_VALUES[1]}"
EXPECTED_PACKAGE_ID="${CONTRACT_VALUES[2]}"
SMOKE_SEED="${CONTRACT_VALUES[3]}"
CONTRACT_TTL="${CONTRACT_VALUES[4]}"
[[ "$SMOKE_SEED" == "43999" ]]
[[ "$TOKEN_TTL_HOURS" == "$CONTRACT_TTL" ]]
JOB_ZIP="$SMOKE_ROOT/immutable_bindings/locked_campaign/$JOB_ZIP_NAME"
[[ "$(sha256sum "$JOB_ZIP" | awk '{print $1}')" == "$EXPECTED_JOB_SHA" ]]
unzip -t "$JOB_ZIP" >/dev/null
unzip -q "$JOB_ZIP" -d "$JOB_ROOT"
(
  cd "$JOB_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  [[ "$(cat PACKAGE_ID.txt)" == "$EXPECTED_PACKAGE_ID" ]]
)
echo "REMOTE_LOCKED_JOB_PACKAGE_MANIFEST_VERIFICATION=PASS"

# The handoff required checking the old Nibi job before new work.
{
  echo "OLD_JOB_18906816_STATUS_CHECK_BEGIN"
  sacct -X -j 18906816 \
    --format=JobID,JobName,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES -P \
    2>&1 || true
  echo "OLD_JOB_18906816_STATUS_CHECK_END"
} | tee "$PROVENANCE/old_job_18906816_status.txt"
OLD_ACTIVE="$(squeue -h -j 18906816 -o '%T' 2>/dev/null | head -n1 || true)"
if [[ "$OLD_ACTIVE" == "PENDING" || "$OLD_ACTIVE" == "RUNNING" || "$OLD_ACTIVE" == "CONFIGURING" ]]; then
  echo "ERROR_OLD_NIBI_JOB_18906816_STILL_ACTIVE=$OLD_ACTIVE"
  exit 23
fi

ACTIVE_CAMPAIGN="$(
  squeue -h -u "$USER" -o '%i|%j|%T' 2>/dev/null \
    | grep -E '\|(fr3-v4-3-p1|fr3-phase1-v43|fr3-p1-campaign)\|' || true
)"
if [[ -n "$ACTIVE_CAMPAIGN" ]]; then
  echo "ERROR_ACTIVE_PHASE1_CAMPAIGN_JOB_DETECTED=YES"
  printf '%s\n' "$ACTIVE_CAMPAIGN"
  exit 24
fi

echo "NIBI_CONCURRENT_CAMPAIGN_GUARD=PASS"

export PHASE1_BASE="$ENV_ROOT"
export PHASE1_VENV="$VENV"
if bash "$JOB_ROOT/setup_environment.sh" \
    > >(tee "$PROVENANCE/environment_setup.log") \
    2> >(tee "$PROVENANCE/environment_setup.err" >&2)
then
  ENV_SETUP_RC=0
else
  ENV_SETUP_RC=$?
fi
echo "NIBI_ENVIRONMENT_SETUP_EXIT_CODE=$ENV_SETUP_RC"
[[ "$ENV_SETUP_RC" -eq 0 ]]

exact_environment_gate() {
  "$VENV/bin/python" - <<'PY'
import importlib.metadata
import platform
import torch
expected = {
    "numpy": "2.4.2",
    "pandas": "2.3.3",
    "scipy": "1.17.0",
    "torch": "2.9.1",
    "sionna-no-rt": "2.0.1",
}
actual = {name: importlib.metadata.version(name).split("+", 1)[0] for name in expected}
assert actual == expected, (actual, expected)
assert platform.python_version() == "3.12.4"
assert str(torch.version.cuda) == "12.6"
PY
}

if exact_environment_gate; then
  echo "NIBI_EXACT_REFERENCE_ENVIRONMENT_REUSE=PASS"
else
  echo "NIBI_EXACT_REFERENCE_ENVIRONMENT_REPAIR_REQUIRED=YES"
  "$VENV/bin/python" -m pip install --upgrade --force-reinstall \
    "numpy==2.4.2" \
    "pandas==2.3.3" \
    "scipy==1.17.0"
  exact_environment_gate
  echo "NIBI_EXACT_REFERENCE_ENVIRONMENT_REPAIR=PASS"
fi
"$VENV/bin/python" -m pip check
"$VENV/bin/python" -m pip freeze --all > "$PROVENANCE/pip_freeze_exact.txt"
"$VENV/bin/python" - <<'PY' > "$PROVENANCE/python_environment.txt"
import importlib.metadata, platform, torch
print(f"python={platform.python_version()}")
for name in ("numpy", "pandas", "scipy", "torch"):
    print(f"{name}={importlib.metadata.version(name).split('+', 1)[0]}")
print(f"torch_cuda_build={torch.version.cuda}")
print(f"sionna_no_rt={importlib.metadata.version('sionna-no-rt')}")
PY
echo "NIBI_EXACT_REFERENCE_ENVIRONMENT_GATE=PASS"

echo "SMOKE_SOURCE_COMMIT=$SMOKE_SOURCE_COMMIT" > "$PROVENANCE/SMOKE_SOURCE_BINDING.env"
echo "SMOKE_PACKAGE_SHA256=$EXPECTED_SMOKE_ZIP_SHA256" >> "$PROVENANCE/SMOKE_SOURCE_BINDING.env"
echo "LOCKED_JOB_PACKAGE_SHA256=$EXPECTED_JOB_SHA" >> "$PROVENANCE/SMOKE_SOURCE_BINDING.env"
echo "LOCKED_PACKAGE_ID=$EXPECTED_PACKAGE_ID" >> "$PROVENANCE/SMOKE_SOURCE_BINDING.env"
echo "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO" >> "$PROVENANCE/SMOKE_SOURCE_BINDING.env"

TOKEN="$PROVENANCE/FINAL_WORKER_SMOKE_AUTHORIZATION.json"
AUTH_RECORD="$PROVENANCE/FINAL_WORKER_SMOKE_AUTHORIZATION_RECORD.json"
python3 "$SMOKE_ROOT/scripts/issue_final_worker_smoke_authorization.py" \
  --job-root "$JOB_ROOT" \
  --output "$TOKEN" \
  --record-output "$AUTH_RECORD" \
  --ttl-hours "$TOKEN_TTL_HOURS" \
  --smoke-source-commit "$SMOKE_SOURCE_COMMIT" \
  --smoke-package-sha256 "$EXPECTED_SMOKE_ZIP_SHA256" \
  | tee "$PROVENANCE/authorization_issuance.log"

mapfile -t ASSOCIATIONS < <(
  sacctmgr -nP show assoc user="$USER" cluster=nibi format=Account 2>/dev/null \
    | cut -d'|' -f1 \
    | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
    | sed '/^$/d' \
    | sort -u
)
printf '%s\n' "${ASSOCIATIONS[@]:-}" > "$PROVENANCE/nibi_account_associations.txt"
ACCOUNT=""
if [[ -n "${FR3_ACCOUNT_OVERRIDE:-}" ]]; then
  ACCOUNT="$FR3_ACCOUNT_OVERRIDE"
else
  for preferred in def-rsadve_gpu def-rsadve def-rsadve_cpu; do
    for value in "${ASSOCIATIONS[@]}"; do
      if [[ "$value" == "$preferred" ]]; then
        ACCOUNT="$value"
        break 2
      fi
    done
  done
fi
[[ -n "$ACCOUNT" ]] || {
  echo "ERROR_NO_NIBI_ACCOUNT_SELECTED=YES"
  exit 25
}
echo "SLURM_ACCOUNT=$ACCOUNT"
echo "$ACCOUNT" > "$PROVENANCE/slurm_account.txt"

JOB_ID="$(
  sbatch \
    --parsable \
    --account="$ACCOUNT" \
    --nodes=1 \
    --ntasks=1 \
    --gpus-per-node=h100:1 \
    --cpus-per-task=16 \
    --mem=124G \
    --time=04:00:00 \
    --job-name=fr3-v43-final-smoke \
    --output="$LOGS/final-worker-%j.out" \
    --error="$LOGS/final-worker-%j.err" \
    --export=ALL,FR3_JOB_ROOT="$JOB_ROOT",FR3_SMOKE_ROOT="$SMOKE_ROOT",FR3_RUN_ROOT="$RUN_ROOT",FR3_VENV="$VENV",PHASE1_AUTHORIZATION_FILE="$TOKEN",FR3_AUTHORIZATION_RECORD="$AUTH_RECORD" \
    "$SMOKE_ROOT/wrappers/NIBI_FINAL_WORKER_SMOKE_H100.sh"
)"
echo "$JOB_ID" > "$PROVENANCE/slurm_job_id.txt"
echo "SLURM_JOB_ID=$JOB_ID"
echo "SLURM_ARRAY_USED=NO"
echo "MERGE_JOB_SUBMITTED=NO"

while squeue -h -j "$JOB_ID" 2>/dev/null | grep -q .; do
  squeue -j "$JOB_ID" -o '%.18i %.10T %.10M %.35R' || true
  sleep 30
done

for _attempt in $(seq 1 30); do
  sacct -j "$JOB_ID" \
    --format=JobID,JobName%28,Account,State,ExitCode,Elapsed,MaxRSS,MaxVMSize,ReqMem,AllocTRES,NodeList \
    -P > "$LOGS/sacct-${JOB_ID}.txt" 2>&1 || true
  SLURM_STATE="$(
    sacct -n -X -j "$JOB_ID" --format=State -P 2>/dev/null \
      | head -n1 | cut -d'|' -f1 | xargs
  )"
  SLURM_EXIT_CODE="$(
    sacct -n -X -j "$JOB_ID" --format=ExitCode -P 2>/dev/null \
      | head -n1 | cut -d'|' -f1 | xargs
  )"
  SLURM_MAXRSS="$(
    sacct -n -j "${JOB_ID}.batch" --format=MaxRSS -P 2>/dev/null \
      | head -n1 | cut -d'|' -f1 | xargs
  )"
  [[ -n "$SLURM_STATE" ]] && break
  sleep 10
done
cat "$LOGS/sacct-${JOB_ID}.txt" || true
[[ -n "$SLURM_STATE" ]] || SLURM_STATE="UNKNOWN"
[[ -n "$SLURM_EXIT_CODE" ]] || SLURM_EXIT_CODE="UNKNOWN"
[[ -n "$SLURM_MAXRSS" ]] || SLURM_MAXRSS="UNKNOWN"

if [[ -f "$PROVENANCE/JOB_EXIT_SUMMARY.env" ]]; then
  # shellcheck disable=SC1090
  source "$PROVENANCE/JOB_EXIT_SUMMARY.env"
  FINAL_WORKER_RC="${FINAL_WORKER_EXIT_CODE:-99}"
  STRUCTURAL_RC="${STRUCTURAL_VALIDATOR_EXIT_CODE:-99}"
  PASS_VALIDATOR_RC="${SCIENTIFIC_PASS_VALIDATOR_EXIT_CODE:-99}"
  AUDIT_RC="${INDEPENDENT_AUDIT_EXIT_CODE:-99}"
fi

{
  echo "REMOTE_ORCHESTRATOR_STATUS=RETURN_READY"
  echo "SLURM_JOB_ID=$JOB_ID"
  echo "SLURM_ACCOUNT=$ACCOUNT"
  echo "SLURM_STATE=$SLURM_STATE"
  echo "SLURM_EXIT_CODE=$SLURM_EXIT_CODE"
  echo "SLURM_MAXRSS=$SLURM_MAXRSS"
  echo "FINAL_WORKER_EXIT_CODE=$FINAL_WORKER_RC"
  echo "STRUCTURAL_VALIDATOR_EXIT_CODE=$STRUCTURAL_RC"
  echo "SCIENTIFIC_PASS_VALIDATOR_EXIT_CODE=$PASS_VALIDATOR_RC"
  echo "INDEPENDENT_AUDIT_EXIT_CODE=$AUDIT_RC"
  echo "CHANNEL_GENERATED_ON_NIBI=YES"
  echo "PRESERVED_CHANNEL_REUSED=NO"
  echo "SLURM_ARRAY_USED=NO"
  echo "MERGE_JOB_SUBMITTED=NO"
  echo "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO"
} > "$PROVENANCE/REMOTE_RUN_SUMMARY.env"

RETURN_NAME="FR3_NIBI_V4_3_FINAL_WORKER_SMOKE_43999_${JOB_ID}.zip"
RETURN_ZIP="$RUN_ROOT/$RETURN_NAME"
python3 "$SMOKE_ROOT/scripts/package_final_worker_smoke_return.py" \
  --run-root "$RUN_ROOT" \
  --smoke-package-root "$SMOKE_ROOT" \
  --job-package-root "$JOB_ROOT" \
  --job-id "$JOB_ID" \
  --slurm-state "$SLURM_STATE" \
  --slurm-exit-code "$SLURM_EXIT_CODE" \
  --worker-exit-code "$FINAL_WORKER_RC" \
  --structural-validator-exit-code "$STRUCTURAL_RC" \
  --pass-validator-exit-code "$PASS_VALIDATOR_RC" \
  --independent-audit-exit-code "$AUDIT_RC" \
  --output "$RETURN_ZIP" \
  | tee "$PROVENANCE/return_packaging.log"
(
  cd "$RUN_ROOT"
  sha256sum -c "$RETURN_NAME.sha256" >/dev/null
  unzip -t "$RETURN_NAME" >/dev/null
)
cp -p "$RETURN_ZIP" "$RETURN_ZIP.sha256" "$RETURN_HOME/"
rm -f "$TOKEN"
echo "AUTHORIZATION_TOKEN_DELETED_AFTER_JOB=PASS"

printf '%s\n' \
  "REMOTE_RETURN_ZIP=$RETURN_HOME/$RETURN_NAME" \
  "REMOTE_RETURN_ZIP_SHA256=$(sha256sum "$RETURN_ZIP" | awk '{print $1}')" \
  "SLURM_JOB_ID=$JOB_ID" \
  "SLURM_ACCOUNT=$ACCOUNT" \
  "SLURM_STATE=$SLURM_STATE" \
  "SLURM_EXIT_CODE=$SLURM_EXIT_CODE" \
  "SLURM_MAXRSS=$SLURM_MAXRSS" \
  "FINAL_WORKER_EXIT_CODE=$FINAL_WORKER_RC" \
  "STRUCTURAL_VALIDATOR_EXIT_CODE=$STRUCTURAL_RC" \
  "SCIENTIFIC_PASS_VALIDATOR_EXIT_CODE=$PASS_VALIDATOR_RC" \
  "INDEPENDENT_AUDIT_EXIT_CODE=$AUDIT_RC" \
  "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO"

if [[ "$SLURM_STATE" == "COMPLETED" \
   && "$FINAL_WORKER_RC" -eq 0 \
   && "$STRUCTURAL_RC" -eq 0 \
   && "$PASS_VALIDATOR_RC" -eq 0 \
   && "$AUDIT_RC" -eq 0 ]]
then
  echo "REMOTE_FINAL_WORKER_SMOKE_ORCHESTRATION=PASS"
  exit 0
fi

if [[ "$FINAL_WORKER_RC" -eq 42 || "$AUDIT_RC" -eq 42 ]]; then
  echo "REMOTE_FINAL_WORKER_SMOKE_ORCHESTRATION=SCIENTIFIC_FAIL_RETURN_RETRIEVABLE"
  exit 42
fi

echo "REMOTE_FINAL_WORKER_SMOKE_ORCHESTRATION=INFRASTRUCTURE_OR_VALIDATION_FAIL_RETURN_RETRIEVABLE"
exit 43
