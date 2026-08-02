#!/usr/bin/env bash
set -Eeuo pipefail

: "${REMOTE_PACKAGE_ZIP:?REMOTE_PACKAGE_ZIP required}"
: "${EXPECTED_PACKAGE_SHA256:?EXPECTED_PACKAGE_SHA256 required}"
: "${REMOTE_LOCAL_AUDIT_JSON:?REMOTE_LOCAL_AUDIT_JSON required}"
: "${RUN_TAG:?RUN_TAG required}"

SCRATCH_ROOT="${SCRATCH:-/home/rsadve1/links/scratch}"
SCRATCH_ROOT="$(readlink -f "$SCRATCH_ROOT")"
RUN_ROOT="$SCRATCH_ROOT/FR3_V4_3_FAILED_SEED_DIAGNOSIS_${RUN_TAG}"
SOURCE_ROOT="$RUN_ROOT/source"
TASK_ROOT="$RUN_ROOT/tasks"
LOG_ROOT="$RUN_ROOT/logs"
RETURN_ROOT="$RUN_ROOT/return"
JOB_ROOT="$RUN_ROOT/job_package"
mkdir -p "$SOURCE_ROOT" "$TASK_ROOT" "$LOG_ROOT" "$RETURN_ROOT"

actual="$(sha256sum "$REMOTE_PACKAGE_ZIP" | awk '{print $1}')"
[[ "$actual" == "$EXPECTED_PACKAGE_SHA256" ]]
echo "REMOTE_DIAGNOSTIC_PACKAGE_SHA256_GATE=PASS"

rm -rf "$SOURCE_ROOT"/* "$JOB_ROOT"
unzip -q "$REMOTE_PACKAGE_ZIP" -d "$SOURCE_ROOT"
PACKAGE_ROOT="$(find "$SOURCE_ROOT" -mindepth 1 -maxdepth 1 -type d | head -1)"
[[ -d "$PACKAGE_ROOT" ]]
(
  cd "$PACKAGE_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo "REMOTE_PACKAGE_MANIFEST_VERIFICATION=PASS"

CAMPAIGN_RUN_ROOT="$(python3 - "$PACKAGE_ROOT/config/DIAGNOSTIC_CONTRACT.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['campaign_return']['campaign_run_root'])
PY
)"
[[ -d "$CAMPAIGN_RUN_ROOT" ]]

job_zip="$PACKAGE_ROOT/immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip"
[[ "$(sha256sum "$job_zip" | awk '{print $1}')" == "c106fa6441b15873d0d2d9b29d636434625edcd58f4033a4700589cb91e19e82" ]]
mkdir -p "$JOB_ROOT"
unzip -q "$job_zip" -d "$JOB_ROOT"
(
  cd "$JOB_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
)
echo "REMOTE_JOB_PACKAGE_MANIFEST_VERIFICATION=PASS"

FAILED_SEEDS=(44001 44007 44008 44013 44017 44018 44024 44025 44026 44027 44028)
for seed in "${FAILED_SEEDS[@]}"; do
  [[ -f "$CAMPAIGN_RUN_ROOT/results/seed_${seed}/channel/CHANNEL_RECORD.json" ]]
  [[ -f "$CAMPAIGN_RUN_ROOT/results/seed_${seed}/channel/frequency_response.npy" ]]
  [[ -f "$CAMPAIGN_RUN_ROOT/results/seed_${seed}/result/SEED_RESULT.json" ]]
done
echo "RORQUAL_PRESERVED_CHANNEL_BINDING=PASS"
echo "CHANNEL_REGENERATION=NO"
echo "GPU_REQUESTED=NO"
echo "WORKER_WALLTIME=00:15:00"
echo "MERGE_WALLTIME=00:05:00"

cp "$REMOTE_LOCAL_AUDIT_JSON" "$RUN_ROOT/LOCAL_CAMPAIGN_SCIENTIFIC_AUDIT.json"

VENV="$SCRATCH_ROOT/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv"
[[ -x "$VENV/bin/python" ]]
"$VENV/bin/python" -m pip check

auth_token="$CAMPAIGN_RUN_ROOT/private/FULL_30_SEED_AUTHORIZATION.json"
[[ ! -e "$auth_token" ]] || {
  echo "ERROR=FULL_CAMPAIGN_AUTHORIZATION_TOKEN_STILL_PRESENT"
  exit 70
}
echo "AUTHORIZATION_TOKEN_PRESENT=NO"

ARRAY_SBATCH="$RUN_ROOT/failed_seed_diagnostic_array.sbatch"
cat > "$ARRAY_SBATCH" <<EOF_ARRAY
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v43-faildiag
#SBATCH --array=0-10%4
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=00:15:00
#SBATCH --output=$LOG_ROOT/%x-%A_%a.out
#SBATCH --error=$LOG_ROOT/%x-%A_%a.err
set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
SEEDS=(44001 44007 44008 44013 44017 44018 44024 44025 44026 44027 44028)
SEED="\${SEEDS[\${SLURM_ARRAY_TASK_ID}]}"
OUT="$TASK_ROOT/seed_\${SEED}"
mkdir -p "\$OUT"
if "$VENV/bin/python" "$PACKAGE_ROOT/scripts/diagnose_failed_seed.py" \
    --seed "\$SEED" \
    --campaign-run-root "$CAMPAIGN_RUN_ROOT" \
    --job-package-root "$JOB_ROOT" \
    --output-dir "\$OUT" \
    >"\$OUT/stdout.log" 2>"\$OUT/stderr.log"; then
  RC=0
else
  RC=\$?
fi
printf '%s\n' "\$RC" >"\$OUT/process_exit_code.txt"
"$VENV/bin/python" - "\$OUT/TASK_STATUS.json" "\$SEED" "\$RC" <<'PY_TASK'
import json,sys
from pathlib import Path
path=Path(sys.argv[1])
record={
    'schema_version':1,
    'campaign_seed':int(sys.argv[2]),
    'process_exit_code':int(sys.argv[3]),
    'status':'PASS' if int(sys.argv[3])==0 else 'FAIL',
}
path.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY_TASK
exit "\$RC"
EOF_ARRAY
chmod +x "$ARRAY_SBATCH"
ARRAY_JOB_ID="$(sbatch --parsable --account=def-rsadve_cpu "$ARRAY_SBATCH")"

MERGE_SBATCH="$RUN_ROOT/failed_seed_diagnostic_merge.sbatch"
cat > "$MERGE_SBATCH" <<EOF_MERGE
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v43-faildiag-merge
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:05:00
#SBATCH --output=$LOG_ROOT/%x-%j.out
#SBATCH --error=$LOG_ROOT/%x-%j.err
set -uo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
MERGED="$RUN_ROOT/merged"
mkdir -p "\$MERGED"
MERGE_RC=0
if "$VENV/bin/python" "$PACKAGE_ROOT/scripts/merge_failed_seed_diagnostics.py" \
    --task-root "$TASK_ROOT" \
    --campaign-audit "$RUN_ROOT/LOCAL_CAMPAIGN_SCIENTIFIC_AUDIT.json" \
    --output-dir "\$MERGED" \
    >"\$MERGED/merge_stdout.log" 2>"\$MERGED/merge_stderr.log"; then
  MERGE_RC=0
else
  MERGE_RC=\$?
fi
printf '%s\n' "\$MERGE_RC" >"\$MERGED/merge_exit_code.txt"
sacct -j "$ARRAY_JOB_ID" --format=JobIDRaw,JobName,Account,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES,NodeList -P \
  >"$RUN_ROOT/sacct_diagnostic.txt" 2>&1 || true
RETURN_DIR="$RETURN_ROOT/FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_$ARRAY_JOB_ID"
rm -rf "\$RETURN_DIR"
mkdir -p "\$RETURN_DIR"
cp "$RUN_ROOT/LOCAL_CAMPAIGN_SCIENTIFIC_AUDIT.json" "\$RETURN_DIR/" || true
cp "$RUN_ROOT/sacct_diagnostic.txt" "\$RETURN_DIR/" || true
cp "$PACKAGE_ROOT/config/DIAGNOSTIC_CONTRACT.json" "\$RETURN_DIR/" || true
cp "$ARRAY_SBATCH" "$MERGE_SBATCH" "\$RETURN_DIR/" || true
cp -a "$RUN_ROOT/merged" "\$RETURN_DIR/" || true
cp -a "$TASK_ROOT" "\$RETURN_DIR/seed_diagnostics" || true
"$VENV/bin/python" - "\$RETURN_DIR/RETURN_STATUS.json" "\$MERGE_RC" <<'PY_STATUS'
import json,sys
from pathlib import Path
path=Path(sys.argv[1]); rc=int(sys.argv[2])
record={
    'schema_version':1,
    'status':'PASS_COMPLETE_DIAGNOSIS_RETURN' if rc==0 else 'FAILURE_DIAGNOSIS_RETURN_REVIEW_REQUIRED',
    'merge_exit_code':rc,
    'channel_regenerated':False,
    'gpu_requested':False,
}
path.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY_STATUS
(
  cd "\$RETURN_DIR"
  find . -type f ! -name RETURN_MANIFEST.sha256 -print0 | sort -z | \
    xargs -0 sha256sum | sed 's#  \./#  #' > RETURN_MANIFEST.sha256
)
RETURN_ZIP="$RETURN_ROOT/FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_$ARRAY_JOB_ID.zip"
rm -f "\$RETURN_ZIP" "\$RETURN_ZIP.sha256"
(
  cd "$RETURN_ROOT"
  zip -q -r "\$(basename "\$RETURN_ZIP")" "\$(basename "\$RETURN_DIR")"
  sha256sum "\$(basename "\$RETURN_ZIP")" > "\$(basename "\$RETURN_ZIP").sha256"
)
echo "DIAGNOSTIC_RETURN_PACKAGING=PASS"
exit "\$MERGE_RC"
EOF_MERGE
chmod +x "$MERGE_SBATCH"
MERGE_JOB_ID="$(sbatch --parsable --account=def-rsadve_cpu --dependency=afterany:$ARRAY_JOB_ID "$MERGE_SBATCH")"

printf '%s\n' \
  "FAILED_SEED_DIAGNOSTIC_SUBMISSION=PASS" \
  "ARRAY_JOB_ID=$ARRAY_JOB_ID" \
  "MERGE_JOB_ID=$MERGE_JOB_ID" \
  "WORKER_ARRAY=0-10%4" \
  "WORKER_CPUS_PER_TASK=8" \
  "WORKER_MEMORY=16G" \
  "WORKER_WALLTIME=00:15:00" \
  "MERGE_CPUS_PER_TASK=4" \
  "MERGE_MEMORY=8G" \
  "MERGE_WALLTIME=00:05:00"

while squeue -h -j "$MERGE_JOB_ID" | grep -q .; do
  squeue -h -j "$ARRAY_JOB_ID,$MERGE_JOB_ID" -o '%18i %30j %10T %10M %30R' || true
  sleep 20
done

sacct -j "$ARRAY_JOB_ID,$MERGE_JOB_ID" --format=JobIDRaw,JobName,Account,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES,NodeList -P || true
RETURN_ZIP="$RETURN_ROOT/FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_$ARRAY_JOB_ID.zip"

# Emergency packaging on the login node if the merge job ended before creating
# its return. This preserves diagnostics without rerunning any scientific task.
if [[ ! -f "$RETURN_ZIP" || ! -f "$RETURN_ZIP.sha256" ]]; then
  EMERGENCY_DIR="$RETURN_ROOT/FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_$ARRAY_JOB_ID"
  rm -rf "$EMERGENCY_DIR"
  mkdir -p "$EMERGENCY_DIR"
  cp "$RUN_ROOT/LOCAL_CAMPAIGN_SCIENTIFIC_AUDIT.json" "$EMERGENCY_DIR/" || true
  cp "$PACKAGE_ROOT/config/DIAGNOSTIC_CONTRACT.json" "$EMERGENCY_DIR/" || true
  cp "$ARRAY_SBATCH" "$MERGE_SBATCH" "$EMERGENCY_DIR/" || true
  cp -a "$TASK_ROOT" "$EMERGENCY_DIR/seed_diagnostics" || true
  cp -a "$LOG_ROOT" "$EMERGENCY_DIR/logs" || true
  sacct -j "$ARRAY_JOB_ID,$MERGE_JOB_ID" --format=JobIDRaw,JobName,Account,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES,NodeList -P \
    >"$EMERGENCY_DIR/sacct_diagnostic.txt" 2>&1 || true
  printf '%s\n' '{"schema_version":1,"status":"EMERGENCY_PARTIAL_RETURN","merge_exit_code":42,"channel_regenerated":false,"gpu_requested":false}' \
    >"$EMERGENCY_DIR/RETURN_STATUS.json"
  (
    cd "$EMERGENCY_DIR"
    find . -type f ! -name RETURN_MANIFEST.sha256 -print0 | sort -z | \
      xargs -0 sha256sum | sed 's#  \./#  #' > RETURN_MANIFEST.sha256
  )
  (
    cd "$RETURN_ROOT"
    zip -q -r "$(basename "$RETURN_ZIP")" "$(basename "$EMERGENCY_DIR")"
    sha256sum "$(basename "$RETURN_ZIP")" > "$(basename "$RETURN_ZIP").sha256"
  )
  echo "DIAGNOSTIC_EMERGENCY_RETURN_PACKAGING=PASS"
fi

(
  cd "$RETURN_ROOT"
  sha256sum -c "$(basename "$RETURN_ZIP").sha256" >/dev/null
)
unzip -t "$RETURN_ZIP" >/dev/null

NEXT_DECISION="UNAVAILABLE_DIAGNOSTIC_RETURN_REVIEW_REQUIRED"
NEXT_GATE="REVIEW_FAILED_SEED_DIAGNOSTIC_INFRASTRUCTURE"
REMOTE_SCIENTIFIC_EXIT_CODE=42
if [[ -f "$RUN_ROOT/merged/NEXT_REPAIR_DECISION.json" ]]; then
  NEXT_DECISION="$(python3 - "$RUN_ROOT/merged/NEXT_REPAIR_DECISION.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['next_repair_decision'])
PY
)"
  NEXT_GATE="$(python3 - "$RUN_ROOT/merged/NEXT_REPAIR_DECISION.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['next_gate'])
PY
)"
  REMOTE_SCIENTIFIC_EXIT_CODE=0
fi

MERGE_STATE="$(sacct -n -X -j "$MERGE_JOB_ID" --format=State | awk 'NF{print $1; exit}' || true)"
MERGE_EXIT="$(sacct -n -X -j "$MERGE_JOB_ID" --format=ExitCode | awk 'NF{print $1; exit}' || true)"
printf '%s\n' \
  "REMOTE_RETURN_ZIP=$RETURN_ZIP" \
  "REMOTE_RETURN_ZIP_SHA256=$(sha256sum "$RETURN_ZIP" | awk '{print $1}')" \
  "ARRAY_JOB_ID=$ARRAY_JOB_ID" \
  "MERGE_JOB_ID=$MERGE_JOB_ID" \
  "MERGE_STATE=${MERGE_STATE:-UNKNOWN}" \
  "MERGE_EXIT_CODE=${MERGE_EXIT:-UNKNOWN}" \
  "REMOTE_SCIENTIFIC_EXIT_CODE=$REMOTE_SCIENTIFIC_EXIT_CODE" \
  "DIAGNOSTIC_SEED_RETURN_COUNT=$(find "$TASK_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'seed_*' | wc -l)" \
  "NEXT_REPAIR_DECISION=$NEXT_DECISION" \
  "NEXT_GATE=$NEXT_GATE" \
  "CHANNEL_REGENERATION=NO" \
  "GPU_REQUESTED=NO"

exit "$REMOTE_SCIENTIFIC_EXIT_CODE"
