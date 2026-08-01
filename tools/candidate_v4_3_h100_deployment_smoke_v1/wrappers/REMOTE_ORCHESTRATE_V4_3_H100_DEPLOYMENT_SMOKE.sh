#!/usr/bin/env bash
# Rorqual-side orchestration for one excluded candidate-v4.3 H100 smoke.
set -Eeuo pipefail

: "${REMOTE_RUN_ROOT:?REMOTE_RUN_ROOT is required}"
: "${REMOTE_BASE:?REMOTE_BASE is required}"
: "${SOURCE_COMMIT:?SOURCE_COMMIT is required}"
: "${EXPECTED_CHANNEL_RECORD_SHA256:?EXPECTED_CHANNEL_RECORD_SHA256 is required}"
: "${EXPECTED_FREQUENCY_ARRAY_SHA256:?EXPECTED_FREQUENCY_ARRAY_SHA256 is required}"

CPUS="${CPUS:-16}"
MEMORY_GIB="${MEMORY_GIB:-64}"
TIME_LIMIT="${TIME_LIMIT:-00:30:00}"
POLL_SECONDS="${POLL_SECONDS:-20}"
PAYLOAD="$REMOTE_RUN_ROOT/payload"
RUN="$REMOTE_RUN_ROOT/run"
RETURN="$REMOTE_RUN_ROOT/return"
LOGS="$RUN/slurm"
SUMMARY="$RUN/summary"
PACKAGE="$REMOTE_BASE/package_rorqual_smoke"
CHANNEL="$REMOTE_BASE/run/results/seed_43999/channel"
ENV_LINK="/home/rsadve1/links/scratch/FR3_PHASE1_RORQUAL_ENV_5037b4e33448"
ENV_ROOT="$(realpath -e "$ENV_LINK" 2>/dev/null || true)"
VENV="$ENV_ROOT/.venv"
REMOTE_STAGE="INITIALIZATION"
JOB_ID="NOT_SUBMITTED"
ACCOUNT="UNKNOWN"
STATE="NOT_SUBMITTED"
SLURM_EXIT="NOT_AVAILABLE"
MAXRSS="NOT_AVAILABLE"
CANDIDATE_EXIT="NOT_RUN"
AUDIT_EXIT="NOT_RUN"
WRAPPER_EXIT=99
mkdir -p "$RUN" "$RETURN" "$LOGS" "$SUMMARY"

write_prejob_failure() {
    local code="$1"
    cat > "$RUN/REMOTE_PREJOB_FAILURE.env" <<EOF
REMOTE_WRAPPER_EXIT_CODE=$code
REMOTE_FAILURE_STAGE=$REMOTE_STAGE
SLURM_JOB_ID=$JOB_ID
SLURM_ACCOUNT=$ACCOUNT
SLURM_STATE=$STATE
SLURM_EXIT_CODE=$SLURM_EXIT
SLURM_MAXRSS=$MAXRSS
CANDIDATE_SCRIPT_EXIT_CODE=$CANDIDATE_EXIT
INDEPENDENT_AUDIT_EXIT_CODE=$AUDIT_EXIT
SOURCE_COMMIT=$SOURCE_COMMIT
H100_REQUESTED=YES
H100_CHANNEL_REGENERATED=NO
CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO
NEXT_GATE=DIAGNOSE_EXCLUDED_H100_SMOKE_FAILURE
EOF
}

make_return() {
    local code="$1"
    local mode="$2"
    local name="FR3_RORQUAL_CANDIDATE_V4_3_H100_DEPLOYMENT_SMOKE_${JOB_ID}.zip"
    if [[ "$JOB_ID" == "NOT_SUBMITTED" ]]; then
        name="FR3_RORQUAL_CANDIDATE_V4_3_H100_DEPLOYMENT_SMOKE_PREJOB_FAILURE.zip"
    fi
    local path="$RETURN/$name"
    local packager_python="python3"
    if [[ -x "$VENV/bin/python" ]]; then
        packager_python="$VENV/bin/python"
    fi
    "$packager_python" "$PAYLOAD/scripts/package_h100_return.py" \
        --run-root "$RUN" \
        --payload-root "$PAYLOAD" \
        --output "$path" \
        --mode "$mode" \
        --wrapper-exit "$code" \
        --job-id "$JOB_ID" \
        --account "$ACCOUNT" \
        --state "$STATE" \
        --slurm-exit "$SLURM_EXIT" \
        --maxrss "$MAXRSS" \
        --candidate-exit "$CANDIDATE_EXIT" \
        --audit-exit "$AUDIT_EXIT" \
        --source-commit "$SOURCE_COMMIT"
    (
        cd "$RETURN"
        printf '%s  %s\n' "$(sha256sum "$name" | awk '{print $1}')" "$name" \
            > "$name.sha256"
        sha256sum -c "$name.sha256" >/dev/null
        unzip -t "$name" >/dev/null
    )
    echo "REMOTE_RETURN_ZIP=$path"
    echo "REMOTE_RETURN_ZIP_SHA256=$(sha256sum "$path" | awk '{print $1}')"
}

on_exit() {
    local code=$?
    trap - EXIT ERR
    if (( code != 0 )); then
        write_prejob_failure "$code" || true
        if ! find "$RETURN" -maxdepth 1 -type f \
            -name 'FR3_RORQUAL_CANDIDATE_V4_3_H100_DEPLOYMENT_SMOKE_*.zip' \
            -print -quit | grep -q .; then
            make_return "$code" FAIL || true
        fi
    fi
    printf '%s\n' \
        "REMOTE_WRAPPER_EXIT_CODE=$code" \
        "REMOTE_FAILURE_STAGE=$REMOTE_STAGE" \
        "SLURM_JOB_ID=$JOB_ID" \
        "SLURM_ACCOUNT=$ACCOUNT" \
        "SLURM_STATE=$STATE" \
        "SLURM_EXIT_CODE=$SLURM_EXIT" \
        "SLURM_MAXRSS=$MAXRSS" \
        "CANDIDATE_SCRIPT_EXIT_CODE=$CANDIDATE_EXIT" \
        "INDEPENDENT_AUDIT_EXIT_CODE=$AUDIT_EXIT" \
        "H100_REQUESTED=YES" \
        "H100_CHANNEL_REGENERATED=NO" \
        "CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO"
    exit "$code"
}
trap on_exit EXIT

REMOTE_STAGE="PAYLOAD_MANIFEST_VERIFICATION"
[[ -f "$PAYLOAD/PACKAGE_MANIFEST.sha256" ]] || {
    echo "REMOTE_PACKAGE_MANIFEST_MISSING=$PAYLOAD/PACKAGE_MANIFEST.sha256"
    exit 9
}
(
    cd "$PAYLOAD"
    sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
)
echo "REMOTE_PACKAGE_MANIFEST_VERIFICATION=PASS"

REMOTE_STAGE="PRESERVED_INPUT_PREFLIGHT"
for path in \
    "$PACKAGE/phase1_seed_worker.py" \
    "$PACKAGE/PHASE1_CAMPAIGN_CONTRACT_V3.json" \
    "$CHANNEL/CHANNEL_RECORD.json" \
    "$CHANNEL/frequency_response.npy" \
    "$PAYLOAD/candidate_v4_3_package/scripts/run_seed43999_floor_feasibility_candidate_v4_3.py" \
    "$PAYLOAD/candidate_v4_3_package/src/fr3_cbf/floor_feasibility_repair.py" \
    "$PAYLOAD/immutable_bindings/v4_3_cpu_return/summary/OUTPUT_MANIFEST.sha256" \
    "$PAYLOAD/scripts/capture_h100_environment.py" \
    "$PAYLOAD/scripts/audit_h100_deployment_smoke.py"
do
    [[ -f "$path" ]] || {
        echo "REMOTE_PREFLIGHT_MISSING=$path"
        exit 10
    }
done
ACTUAL_CHANNEL_SHA="$(sha256sum "$CHANNEL/CHANNEL_RECORD.json" | awk '{print $1}')"
[[ "$ACTUAL_CHANNEL_SHA" == "$EXPECTED_CHANNEL_RECORD_SHA256" ]] || {
    echo "REMOTE_CHANNEL_RECORD_SHA256_MISMATCH=$ACTUAL_CHANNEL_SHA"
    exit 11
}
ACTUAL_ARRAY_SHA="$(python3 - "$CHANNEL/CHANNEL_RECORD.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['frequency_response_sha256_array_bytes'])
PY
)"
[[ "$ACTUAL_ARRAY_SHA" == "$EXPECTED_FREQUENCY_ARRAY_SHA256" ]] || {
    echo "REMOTE_FREQUENCY_ARRAY_SHA256_MISMATCH=$ACTUAL_ARRAY_SHA"
    exit 12
}
cp "$CHANNEL/CHANNEL_RECORD.json" "$RUN/CHANNEL_RECORD.json"
echo "PRESERVED_CHANNEL_REUSED=YES"
echo "H100_CHANNEL_REGENERATION=NO"

REMOTE_STAGE="VENV_PREFLIGHT_OR_REPAIR"
[[ -n "$ENV_ROOT" && -d "$ENV_ROOT" ]] || {
    echo "REMOTE_ENVIRONMENT_ROOT_MISSING=$ENV_LINK"
    exit 13
}
if [[ ! -x "$VENV/bin/python" ]] || ! "$VENV/bin/python" - <<'PY' >/dev/null 2>&1
import numpy,pandas,scipy,torch
from scipy.optimize import milp
assert torch.version.cuda is not None
PY
then
    echo "REMOTE_VENV_REPAIR_REQUIRED=YES"
    [[ -f "$PACKAGE/setup_environment.sh" ]] || {
        echo "REMOTE_SETUP_ENVIRONMENT_MISSING=$PACKAGE/setup_environment.sh"
        exit 14
    }
    PHASE1_BASE="$ENV_ROOT" PHASE1_VENV="$VENV" bash "$PACKAGE/setup_environment.sh"
else
    echo "REMOTE_VENV_REUSE=PASS"
fi

REMOTE_STAGE="SLURM_ACCOUNT_SELECTION"
mapfile -t ACCOUNTS < <(
    sacctmgr -nP show assoc user="$USER" cluster=rorqual format=Account 2>/dev/null \
        | cut -d'|' -f1 \
        | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
        | sed '/^$/d' \
        | sort -u
)
ACCOUNT=""
for preferred in def-rsadve_gpu def-rsadve def-rsadve_cpu; do
    for value in "${ACCOUNTS[@]}"; do
        if [[ "$value" == "$preferred" ]]; then
            ACCOUNT="$value"
            break 2
        fi
    done
done
if [[ -z "$ACCOUNT" && "${#ACCOUNTS[@]}" -gt 0 ]]; then
    ACCOUNT="${ACCOUNTS[0]}"
fi
[[ -n "$ACCOUNT" ]] || {
    echo "REMOTE_ACCOUNT_SELECTION=FAIL"
    exit 15
}
printf '%s\n' \
    "SLURM_ACCOUNT=$ACCOUNT" \
    "RORQUAL_REQUIRED=YES_H100" \
    "H100_REQUESTED=YES_ONE_FULL_H100" \
    "PRESERVED_CHANNEL_REUSED=YES" \
    "CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO"

REMOTE_STAGE="SBATCH_CREATION_AND_SUBMISSION"
SBATCH="$RUN/h100_deployment_smoke.sbatch"
cat > "$SBATCH" <<EOF
#!/usr/bin/env bash
#SBATCH --account=$ACCOUNT
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus=h100:1
#SBATCH --cpus-per-task=$CPUS
#SBATCH --mem=${MEMORY_GIB}G
#SBATCH --time=$TIME_LIMIT
#SBATCH --job-name=fr3-v43-h100
#SBATCH --output=$LOGS/h100-v43-%j.out
#SBATCH --error=$LOGS/h100-v43-%j.err

set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$RUN/pycache"
export CUDA_CACHE_PATH="$RUN/cache/cuda"
export XDG_CACHE_HOME="$RUN/cache/xdg"
export TMPDIR="$RUN/cache/tmp"
export TORCH_HOME="$RUN/cache/torch"
export MPLCONFIGDIR="$RUN/cache/matplotlib"
export OMP_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export MKL_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export OPENBLAS_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export NUMEXPR_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
mkdir -p "$SUMMARY" "$RUN/cache/cuda" "$RUN/cache/xdg" \
    "$RUN/cache/tmp" "$RUN/cache/torch" "$RUN/cache/matplotlib"

nvidia-smi > "$RUN/nvidia_smi.txt"
"$VENV/bin/python" -m pip freeze --all > "$RUN/pip_freeze_exact.txt"
"$VENV/bin/python" - <<'PY' > "$RUN/python_environment.txt"
import platform,numpy,pandas,scipy,torch
print('python='+platform.python_version())
print('numpy='+numpy.__version__)
print('pandas='+pandas.__version__)
print('scipy='+scipy.__version__)
print('torch='+torch.__version__)
print('torch_cuda_build='+str(torch.version.cuda))
PY

"$VENV/bin/python" "$PAYLOAD/scripts/capture_h100_environment.py" \
    --channel-root "$CHANNEL" \
    --output-json "$RUN/H100_ENVIRONMENT.json"

if "$VENV/bin/python" \
    "$PAYLOAD/candidate_v4_3_package/scripts/run_seed43999_floor_feasibility_candidate_v4_3.py" \
    --package-root "$PACKAGE" \
    --channel-root "$CHANNEL" \
    --candidate-source "$PAYLOAD/candidate_v4_3_package/src/fr3_cbf/floor_feasibility_repair.py" \
    --output-root "$SUMMARY" \
    --expected-channel-record-sha256 "$EXPECTED_CHANNEL_RECORD_SHA256" \
    --expected-frequency-array-sha256 "$EXPECTED_FREQUENCY_ARRAY_SHA256" \
    --source-commit "$SOURCE_COMMIT" \
    --grid-time-limit-s 45 \
    > "$RUN/scientific_stdout.txt" 2> "$RUN/scientific_stderr.txt"
then
    candidate_exit=0
else
    candidate_exit=\$?
fi
printf '%s\n' "\$candidate_exit" > "$RUN/candidate_exit_code.txt"
cat "$RUN/scientific_stdout.txt"
cat "$RUN/scientific_stderr.txt" >&2

if (( candidate_exit == 0 )); then
    if "$VENV/bin/python" "$PAYLOAD/scripts/audit_h100_deployment_smoke.py" \
        --cpu-summary "$PAYLOAD/immutable_bindings/v4_3_cpu_return/summary" \
        --h100-summary "$SUMMARY" \
        --h100-environment "$RUN/H100_ENVIRONMENT.json" \
        --output-json "$RUN/H100_DEPLOYMENT_SMOKE_AUDIT.json" \
        --output-env "$RUN/H100_DEPLOYMENT_SMOKE_STATUS.env" \
        --utility-csv "$RUN/CANDIDATE_UTILITY_SUMMARY.csv" \
        > "$RUN/audit_stdout.txt" 2> "$RUN/audit_stderr.txt"
    then
        audit_exit=0
    else
        audit_exit=\$?
    fi
else
    audit_exit=98
    printf '%s\n' "H100_AUDIT_SKIPPED_CANDIDATE_EXIT=\$candidate_exit" \
        > "$RUN/audit_stderr.txt"
    : > "$RUN/audit_stdout.txt"
fi
printf '%s\n' "\$audit_exit" > "$RUN/audit_exit_code.txt"
cat "$RUN/audit_stdout.txt"
cat "$RUN/audit_stderr.txt" >&2
if (( candidate_exit != 0 )); then exit "\$candidate_exit"; fi
exit "\$audit_exit"
EOF
chmod 700 "$SBATCH"
JOB_ID="$(sbatch --parsable "$SBATCH")"
printf '%s\n' "$JOB_ID" > "$RUN/slurm_job_id.txt"
echo "SLURM_JOB_ID=$JOB_ID"

REMOTE_STAGE="SLURM_JOB_WAIT"
while squeue -h -j "$JOB_ID" 2>/dev/null | grep -q .; do
    squeue -j "$JOB_ID" -o '%.18i %.10T %.10M %.35R' || true
    sleep "$POLL_SECONDS"
done
for _ in $(seq 1 30); do
    sacct -j "$JOB_ID" \
        --format=JobID,JobName%24,Account,State,ExitCode,Elapsed,MaxRSS,MaxVMSize,ReqMem,AllocTRES \
        -P > "$LOGS/sacct-${JOB_ID}.txt" || true
    STATE="$(sacct -n -X -j "$JOB_ID" --format=State -P 2>/dev/null \
        | head -n1 | cut -d'|' -f1 | xargs)"
    [[ -n "$STATE" ]] && break
    sleep 10
done
MAXRSS="$(sacct -n -j "$JOB_ID.batch" --format=MaxRSS -P 2>/dev/null \
    | head -n1 | cut -d'|' -f1 | xargs || true)"
SLURM_EXIT="$(sacct -n -X -j "$JOB_ID" --format=ExitCode -P 2>/dev/null \
    | head -n1 | cut -d'|' -f1 | xargs || true)"
CANDIDATE_EXIT="$(cat "$RUN/candidate_exit_code.txt" 2>/dev/null || echo 99)"
AUDIT_EXIT="$(cat "$RUN/audit_exit_code.txt" 2>/dev/null || echo 99)"
cat "$LOGS/sacct-${JOB_ID}.txt" || true

cat > "$RUN/REMOTE_RUN_SUMMARY.env" <<EOF
SLURM_JOB_ID=$JOB_ID
SLURM_ACCOUNT=$ACCOUNT
SLURM_STATE=${STATE:-UNKNOWN}
SLURM_EXIT_CODE=${SLURM_EXIT:-UNKNOWN}
SLURM_MAXRSS=${MAXRSS:-UNKNOWN}
CANDIDATE_SCRIPT_EXIT_CODE=$CANDIDATE_EXIT
INDEPENDENT_AUDIT_EXIT_CODE=$AUDIT_EXIT
CHANNEL_RECORD_SHA256=$ACTUAL_CHANNEL_SHA
FREQUENCY_RESPONSE_ARRAY_SHA256=$ACTUAL_ARRAY_SHA
SOURCE_COMMIT=$SOURCE_COMMIT
H100_REQUESTED=YES_ONE_FULL_H100
H100_CHANNEL_REGENERATED=NO
PRESERVED_CHANNEL_REUSED=YES
CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO
EOF

REMOTE_STAGE="RETURN_PACKAGING"
MODE=FAIL
WRAPPER_EXIT=1
if [[ "$STATE" == COMPLETED* && "$CANDIDATE_EXIT" == 0 && "$AUDIT_EXIT" == 0 ]]; then
    MODE=PASS
    WRAPPER_EXIT=0
elif [[ "$CANDIDATE_EXIT" =~ ^[0-9]+$ ]] && (( CANDIDATE_EXIT != 0 )); then
    WRAPPER_EXIT="$CANDIDATE_EXIT"
elif [[ "$AUDIT_EXIT" =~ ^[0-9]+$ ]]; then
    WRAPPER_EXIT="$AUDIT_EXIT"
fi
make_return "$WRAPPER_EXIT" "$MODE"
REMOTE_STAGE="COMPLETE"
printf '%s\n' \
    "SLURM_STATE=${STATE:-UNKNOWN}" \
    "SLURM_EXIT_CODE=${SLURM_EXIT:-UNKNOWN}" \
    "SLURM_MAXRSS=${MAXRSS:-UNKNOWN}" \
    "CANDIDATE_SCRIPT_EXIT_CODE=$CANDIDATE_EXIT" \
    "INDEPENDENT_AUDIT_EXIT_CODE=$AUDIT_EXIT"
exit "$WRAPPER_EXIT"
