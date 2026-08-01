#!/usr/bin/env bash
# Rorqual-side CPU-only orchestration. Reuses the immutable seed-43999 channel.
set -Eeuo pipefail

: "${REMOTE_RUN_ROOT:?REMOTE_RUN_ROOT is required}"
: "${REMOTE_BASE:?REMOTE_BASE is required}"
: "${SOURCE_COMMIT:?SOURCE_COMMIT is required}"
: "${EXPECTED_CHANNEL_RECORD_SHA256:?EXPECTED_CHANNEL_RECORD_SHA256 is required}"
: "${EXPECTED_FREQUENCY_ARRAY_SHA256:?EXPECTED_FREQUENCY_ARRAY_SHA256 is required}"

CPUS="${CPUS:-16}"
MEMORY_GIB="${MEMORY_GIB:-64}"
TIME_LIMIT="${TIME_LIMIT:-06:00:00}"
POLL_SECONDS="${POLL_SECONDS:-20}"
PAYLOAD="$REMOTE_RUN_ROOT/payload"
RUN="$REMOTE_RUN_ROOT/run"
RETURN="$REMOTE_RUN_ROOT/return"
LOGS="$RUN/logs"
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
SCIENTIFIC_EXIT="NOT_RUN"
SOURCE_PAYLOAD_MANIFEST_SHA256="UNKNOWN"
mkdir -p "$RUN" "$RETURN" "$LOGS" "$SUMMARY"

write_prejob_failure() {
  local code="$1"
  cat > "$RUN/REMOTE_PREJOB_FAILURE.env" <<EOF_FAIL
REMOTE_WRAPPER_EXIT_CODE=$code
REMOTE_FAILURE_STAGE=$REMOTE_STAGE
SLURM_JOB_ID=$JOB_ID
SLURM_ACCOUNT=$ACCOUNT
SLURM_STATE=$STATE
SLURM_EXIT_CODE=$SLURM_EXIT
SLURM_MAXRSS=$MAXRSS
SCIENTIFIC_SCRIPT_EXIT_CODE=$SCIENTIFIC_EXIT
SOURCE_COMMIT=$SOURCE_COMMIT
SOURCE_PAYLOAD_MANIFEST_SHA256=$SOURCE_PAYLOAD_MANIFEST_SHA256
H100_CHANNEL_REGENERATED=NO
CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO
NEXT_GATE=DIAGNOSE_RORQUAL_PREJOB_OR_JOB_FAILURE
EOF_FAIL
}

make_return_zip() {
  local code="$1"
  local mode="$2"
  local zip_name="FR3_RORQUAL_FLOOR_FEASIBILITY_CANDIDATE_V4_3_${JOB_ID}.zip"
  if [[ "$JOB_ID" == "NOT_SUBMITTED" ]]; then
    zip_name="FR3_RORQUAL_FLOOR_FEASIBILITY_CANDIDATE_V4_3_PREJOB_FAILURE.zip"
  fi
  local zip_path="$RETURN/$zip_name"
  python3 - "$REMOTE_BASE" "$REMOTE_RUN_ROOT" "$zip_path" "$JOB_ID" "$ACCOUNT" "$STATE" "$SLURM_EXIT" "$MAXRSS" "$SCIENTIFIC_EXIT" "$SOURCE_COMMIT" "$mode" "$code" <<'PY'
from pathlib import Path
import json,sys,zipfile
(base_s,root_s,out_s,job_id,account,state,slurm_exit,maxrss,
 scientific_exit,source_commit,mode,wrapper_exit)=sys.argv[1:]
base=Path(base_s); root=Path(root_s); out=Path(out_s); run=root/'run'; payload=root/'payload'
files=[]
def add(path,arc):
    path=Path(path)
    if path.is_file(): files.append((path,arc))
add(base/'run/results/seed_43999/channel/CHANNEL_RECORD.json',
    'immutable_channel/CHANNEL_RECORD.json')
source_manifest = payload/'SOURCE_PAYLOAD_MANIFEST.sha256'
if source_manifest.is_file():
    add(source_manifest, 'candidate_source/SOURCE_PAYLOAD_MANIFEST.sha256')
    for line in source_manifest.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        _digest, rel = line.split(None, 1)
        rel = rel.strip()
        add(payload/rel, 'candidate_source/'+Path(rel).as_posix())
for path,arc in [
    (run/'floor_candidate_v4_3.sbatch','slurm/floor_candidate_v4_3.sbatch'),
    (run/'REMOTE_RUN_SUMMARY.env','slurm/REMOTE_RUN_SUMMARY.env'),
    (run/'REMOTE_PREJOB_FAILURE.env','slurm/REMOTE_PREJOB_FAILURE.env'),
    (run/'slurm_job_id.txt','slurm/slurm_job_id.txt'),
    (run/f'logs/sacct-{job_id}.txt',f'slurm/sacct-{job_id}.txt'),
    (run/f'logs/floor-v4-3-{job_id}.out',f'slurm/floor-v4-3-{job_id}.out'),
    (run/f'logs/floor-v4-3-{job_id}.err',f'slurm/floor-v4-3-{job_id}.err'),
    (run/'scientific_stdout.txt','logs/scientific_stdout.txt'),
    (run/'scientific_stderr.txt','logs/scientific_stderr.txt'),
    (run/'scientific_exit_code.txt','logs/scientific_exit_code.txt'),
    (run/'python_environment.txt','environment/python_environment.txt'),
    (run/'pip_freeze_exact.txt','environment/pip_freeze_exact.txt'),
]: add(path,arc)
summary=run/'summary'
if summary.is_dir():
    for path in sorted(summary.rglob('*')):
        if path.is_file(): add(path,'summary/'+path.relative_to(summary).as_posix())
meta={
 'schema_version':1,
 'candidate_version':'v4.3',
 'status':'PASS_RETURN_READY' if mode=='PASS' else 'FAIL_RETURN_READY',
 'mode':mode,
 'remote_wrapper_exit_code':int(wrapper_exit),
 'slurm_job_id':job_id,
 'slurm_account':account,
 'slurm_state':state,
 'slurm_exit_code':slurm_exit,
 'slurm_maxrss':maxrss,
 'scientific_exit_code':scientific_exit,
 'source_commit':source_commit,
 'seed':43999,
 'channel_reused':True,
 'h100_channel_regenerated':False,
 'confirmatory_campaign_authorized':False,
}
meta_path=run/'RETURN_METADATA.json'
meta_path.write_text(json.dumps(meta,indent=2,sort_keys=True)+'\n',encoding='utf-8')
add(meta_path,'RETURN_METADATA.json')
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,allowZip64=True) as z:
    for path,arc in files: z.write(path,arc)
with zipfile.ZipFile(out) as z:
    bad=z.testzip()
    if bad is not None: raise RuntimeError(f'bad ZIP member: {bad}')
PY
  (
    cd "$RETURN"
    sha256sum "$zip_name" > "$zip_name.sha256"
    sha256sum -c "$zip_name.sha256" >/dev/null
    unzip -t "$zip_name" >/dev/null
  )
  echo "REMOTE_RETURN_ZIP=$zip_path"
  echo "REMOTE_RETURN_ZIP_SHA256=$(sha256sum "$zip_path" | awk '{print $1}')"
}

on_exit() {
  local code=$?
  trap - EXIT ERR
  if (( code != 0 )); then
    write_prejob_failure "$code" || true
    if ! find "$RETURN" -maxdepth 1 -type f -name 'FR3_RORQUAL_FLOOR_FEASIBILITY_CANDIDATE_V4_3_*.zip' -print -quit | grep -q .; then
      make_return_zip "$code" FAIL || true
    fi
  fi
  echo "REMOTE_WRAPPER_EXIT_CODE=$code"
  echo "REMOTE_FAILURE_STAGE=$REMOTE_STAGE"
  echo "SLURM_JOB_ID=$JOB_ID"
  echo "SLURM_ACCOUNT=$ACCOUNT"
  echo "SLURM_STATE=$STATE"
  echo "SLURM_EXIT_CODE=$SLURM_EXIT"
  echo "SLURM_MAXRSS=$MAXRSS"
  echo "SCIENTIFIC_SCRIPT_EXIT_CODE=$SCIENTIFIC_EXIT"
  echo "CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO"
  exit "$code"
}
trap on_exit EXIT

REMOTE_STAGE="PRESERVED_ENVIRONMENT_PREFLIGHT"
[[ -n "$ENV_ROOT" && -d "$ENV_ROOT" ]] || { echo "REMOTE_ENVIRONMENT_ROOT_MISSING=$ENV_LINK"; exit 15; }

REMOTE_STAGE="SOURCE_PAYLOAD_MANIFEST_VERIFICATION"
[[ -f "$PAYLOAD/SOURCE_PAYLOAD_MANIFEST.sha256" ]] || { echo "REMOTE_SOURCE_PAYLOAD_MANIFEST_MISSING=$PAYLOAD/SOURCE_PAYLOAD_MANIFEST.sha256"; exit 9; }
(
  cd "$PAYLOAD"
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
SOURCE_PAYLOAD_MANIFEST_SHA256="$(sha256sum "$PAYLOAD/SOURCE_PAYLOAD_MANIFEST.sha256" | awk '{print $1}')"
echo "REMOTE_SOURCE_MANIFEST_VERIFICATION=PASS"
echo "SOURCE_PAYLOAD_MANIFEST_SHA256=$SOURCE_PAYLOAD_MANIFEST_SHA256"

REMOTE_STAGE="PRESERVED_INPUT_PREFLIGHT"
for path in \
  "$PACKAGE/phase1_seed_worker.py" \
  "$PACKAGE/PHASE1_CAMPAIGN_CONTRACT_V3.json" \
  "$CHANNEL/CHANNEL_RECORD.json" \
  "$CHANNEL/frequency_response.npy" \
  "$PAYLOAD/scripts/run_seed43999_floor_feasibility_candidate_v4_3.py" \
  "$PAYLOAD/src/fr3_cbf/floor_feasibility_repair.py"
do
  [[ -f "$path" ]] || { echo "REMOTE_PREFLIGHT_MISSING=$path"; exit 10; }
done
ACTUAL_CHANNEL_SHA="$(sha256sum "$CHANNEL/CHANNEL_RECORD.json" | awk '{print $1}')"
[[ "$ACTUAL_CHANNEL_SHA" == "$EXPECTED_CHANNEL_RECORD_SHA256" ]] || { echo "REMOTE_CHANNEL_RECORD_SHA256_MISMATCH=$ACTUAL_CHANNEL_SHA"; exit 11; }
ACTUAL_ARRAY_SHA="$(python3 - "$CHANNEL/CHANNEL_RECORD.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['frequency_response_sha256_array_bytes'])
PY
)"
[[ "$ACTUAL_ARRAY_SHA" == "$EXPECTED_FREQUENCY_ARRAY_SHA256" ]] || { echo "REMOTE_FREQUENCY_ARRAY_SHA256_MISMATCH=$ACTUAL_ARRAY_SHA"; exit 12; }

REMOTE_STAGE="VENV_PREFLIGHT_OR_REPAIR"
if [[ ! -x "$VENV/bin/python" ]] || ! "$VENV/bin/python" - <<'PY' >/dev/null 2>&1
import numpy,pandas,scipy
from scipy.optimize import milp
PY
then
  echo "REMOTE_VENV_REPAIR_REQUIRED=YES"
  [[ -f "$PACKAGE/setup_environment.sh" ]] || { echo "REMOTE_SETUP_ENVIRONMENT_MISSING=$PACKAGE/setup_environment.sh"; exit 13; }
  PHASE1_BASE="$ENV_ROOT" PHASE1_VENV="$VENV" bash "$PACKAGE/setup_environment.sh"
else
  echo "REMOTE_VENV_REUSE=PASS"
fi

REMOTE_STAGE="SLURM_ACCOUNT_SELECTION"
mapfile -t ACCOUNTS < <(sacctmgr -nP show assoc user="$USER" cluster=rorqual format=Account 2>/dev/null | cut -d'|' -f1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed '/^$/d' | sort -u)
ACCOUNT=""
for preferred in def-rsadve_cpu def-rsadve def-rsadve_gpu; do
  for value in "${ACCOUNTS[@]}"; do
    if [[ "$value" == "$preferred" ]]; then ACCOUNT="$value"; break 2; fi
  done
done
[[ -n "$ACCOUNT" ]] || { echo "REMOTE_ACCOUNT_SELECTION=FAIL"; exit 14; }
echo "SLURM_ACCOUNT=$ACCOUNT"
echo "RORQUAL_REQUIRED=YES_CPU_ONLY"
echo "H100_REQUESTED=NO"
echo "PRESERVED_CHANNEL_REUSED=YES"

REMOTE_STAGE="SBATCH_CREATION_AND_SUBMISSION"
SBATCH="$RUN/floor_candidate_v4_3.sbatch"
cat > "$SBATCH" <<EOF_SBATCH
#!/usr/bin/env bash
#SBATCH --account=$ACCOUNT
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=$CPUS
#SBATCH --mem=${MEMORY_GIB}G
#SBATCH --time=$TIME_LIMIT
#SBATCH --job-name=fr3-floor-v4-3
#SBATCH --output=$LOGS/floor-v4-3-%j.out
#SBATCH --error=$LOGS/floor-v4-3-%j.err

set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$RUN/pycache"
export OMP_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export MKL_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export OPENBLAS_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export NUMEXPR_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
"$VENV/bin/python" -m pip freeze --all > "$RUN/pip_freeze_exact.txt"
"$VENV/bin/python" - <<'PY' > "$RUN/python_environment.txt"
import platform,numpy,pandas,scipy
print('python='+platform.python_version())
print('numpy='+numpy.__version__)
print('pandas='+pandas.__version__)
print('scipy='+scipy.__version__)
PY
if "$VENV/bin/python" "$PAYLOAD/scripts/run_seed43999_floor_feasibility_candidate_v4_3.py" \
  --package-root "$PACKAGE" \
  --channel-root "$CHANNEL" \
  --candidate-source "$PAYLOAD/src/fr3_cbf/floor_feasibility_repair.py" \
  --output-root "$SUMMARY" \
  --expected-channel-record-sha256 "$EXPECTED_CHANNEL_RECORD_SHA256" \
  --expected-frequency-array-sha256 "$EXPECTED_FREQUENCY_ARRAY_SHA256" \
  --source-commit "$SOURCE_COMMIT" \
  --grid-time-limit-s 45 \
  > "$RUN/scientific_stdout.txt" 2> "$RUN/scientific_stderr.txt"
then
  scientific_exit=0
else
  scientific_exit=\$?
fi
printf '%s\n' "\$scientific_exit" > "$RUN/scientific_exit_code.txt"
cat "$RUN/scientific_stdout.txt"
cat "$RUN/scientific_stderr.txt" >&2
exit "\$scientific_exit"
EOF_SBATCH
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
  sacct -j "$JOB_ID" --format=JobID,JobName%24,Account,State,ExitCode,Elapsed,MaxRSS,MaxVMSize,ReqMem,AllocTRES -P > "$LOGS/sacct-${JOB_ID}.txt" || true
  STATE="$(sacct -n -X -j "$JOB_ID" --format=State -P 2>/dev/null | head -n1 | cut -d'|' -f1 | xargs)"
  [[ -n "$STATE" ]] && break
  sleep 10
done
MAXRSS="$(sacct -n -j "$JOB_ID.batch" --format=MaxRSS -P 2>/dev/null | head -n1 | cut -d'|' -f1 | xargs || true)"
SLURM_EXIT="$(sacct -n -X -j "$JOB_ID" --format=ExitCode -P 2>/dev/null | head -n1 | cut -d'|' -f1 | xargs || true)"
SCIENTIFIC_EXIT="$(cat "$RUN/scientific_exit_code.txt" 2>/dev/null || echo 99)"
cat "$LOGS/sacct-${JOB_ID}.txt" || true

cat > "$RUN/REMOTE_RUN_SUMMARY.env" <<EOF_SUMMARY
SLURM_JOB_ID=$JOB_ID
SLURM_ACCOUNT=$ACCOUNT
SLURM_STATE=${STATE:-UNKNOWN}
SLURM_EXIT_CODE=${SLURM_EXIT:-UNKNOWN}
SLURM_MAXRSS=${MAXRSS:-UNKNOWN}
SCIENTIFIC_SCRIPT_EXIT_CODE=$SCIENTIFIC_EXIT
CHANNEL_RECORD_SHA256=$ACTUAL_CHANNEL_SHA
FREQUENCY_RESPONSE_ARRAY_SHA256=$ACTUAL_ARRAY_SHA
SOURCE_COMMIT=$SOURCE_COMMIT
SOURCE_PAYLOAD_MANIFEST_SHA256=$SOURCE_PAYLOAD_MANIFEST_SHA256
H100_CHANNEL_REGENERATED=NO
CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO
EOF_SUMMARY
cp "$RUN/REMOTE_RUN_SUMMARY.env" "$RETURN/"

REMOTE_STAGE="RETURN_PACKAGING"
MODE=FAIL
WRAPPER_EXIT=1
if [[ "$STATE" == COMPLETED* && "$SCIENTIFIC_EXIT" == 0 ]]; then MODE=PASS; WRAPPER_EXIT=0; elif [[ "$SCIENTIFIC_EXIT" =~ ^[0-9]+$ ]]; then WRAPPER_EXIT="$SCIENTIFIC_EXIT"; fi
make_return_zip "$WRAPPER_EXIT" "$MODE"
echo "SLURM_STATE=${STATE:-UNKNOWN}"
echo "SLURM_EXIT_CODE=${SLURM_EXIT:-UNKNOWN}"
echo "SLURM_MAXRSS=${MAXRSS:-UNKNOWN}"
echo "SCIENTIFIC_SCRIPT_EXIT_CODE=$SCIENTIFIC_EXIT"
exit "$WRAPPER_EXIT"
