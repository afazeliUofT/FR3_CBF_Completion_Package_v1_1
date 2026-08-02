#!/usr/bin/env bash
set -Eeuo pipefail

: "${REMOTE_PACKAGE_ZIP:?REMOTE_PACKAGE_ZIP required}"
: "${EXPECTED_PACKAGE_SHA256:?EXPECTED_PACKAGE_SHA256 required}"
: "${RUN_TAG:?RUN_TAG required}"

SCRATCH_ROOT="${SCRATCH:-/home/rsadve1/links/scratch}"
SCRATCH_ROOT="$(readlink -f "$SCRATCH_ROOT")"
CAMPAIGN_RUN_ROOT="$SCRATCH_ROOT/FR3_PHASE1_RORQUAL_CAMPAIGN_V4_3_R2_8473d5504e69_20260802_135838"
VENV="$SCRATCH_ROOT/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv"
RUN_ROOT="$SCRATCH_ROOT/FR3_V45_COMPANION_AWARE_DEVELOPMENT_${RUN_TAG}"
SOURCE_ROOT="$RUN_ROOT/source"
PACKAGE_ROOT="$RUN_ROOT/package"
JOB_ROOT="$RUN_ROOT/job_package"
TASK_ROOT="$RUN_ROOT/tasks"
MERGED_ROOT="$RUN_ROOT/merged"
LOG_ROOT="$RUN_ROOT/logs"
SLURM_ROOT="$RUN_ROOT/slurm"
RETURN_ROOT="$RUN_ROOT/return"
STATE_FILE="$RUN_ROOT/job_ids.env"
mkdir -p "$SOURCE_ROOT" "$TASK_ROOT" "$MERGED_ROOT" "$LOG_ROOT" "$SLURM_ROOT" "$RETURN_ROOT"

printf '%s\n' \
  "REMOTE_HOST=$(hostname -f)" \
  "REMOTE_SCRATCH=$SCRATCH_ROOT" \
  "EXECUTION_STAGE=V4_5_COMPANION_AWARE_SCHEDULING_DEVELOPMENT" \
  "FAILED_SEEDS=44001,44007,44008,44013,44017,44018,44024,44025,44026,44027,44028" \
  "CHANNEL_REGENERATION=NO" \
  "GPU_REQUESTED=NO" \
  "WORKER_ARRAY=0-10%4" \
  "WORKER_WALLTIME=00:06:00" \
  "WORKER_MEMORY=8G" \
  "MERGE_WALLTIME=00:03:00" \
  "MERGE_MEMORY=4G" \
  "CAMPAIGN_RERUN_AUTHORIZED=NO"

actual="$(sha256sum "$REMOTE_PACKAGE_ZIP" | awk '{print $1}')"
[[ "$actual" == "$EXPECTED_PACKAGE_SHA256" ]]
echo "REMOTE_V45_PACKAGE_SHA256_GATE=PASS"

if [[ -f "$STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  echo "EXISTING_V45_COMPANION_RUN_ATTACHED=YES"
else
  echo "EXISTING_V45_COMPANION_RUN_ATTACHED=NO"
  rm -rf "$SOURCE_ROOT" "$PACKAGE_ROOT" "$JOB_ROOT"
  mkdir -p "$SOURCE_ROOT" "$JOB_ROOT"
  unzip -q "$REMOTE_PACKAGE_ZIP" -d "$SOURCE_ROOT"
  extracted="$(find "$SOURCE_ROOT" -mindepth 1 -maxdepth 1 -type d -print -quit)"
  [[ -d "$extracted" ]]
  mv "$extracted" "$PACKAGE_ROOT"
  (
    cd "$PACKAGE_ROOT"
    sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
    sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
  )
  echo "REMOTE_PACKAGE_MANIFEST_VERIFICATION=PASS"

  job_zip="$PACKAGE_ROOT/immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip"
  [[ "$(sha256sum "$job_zip" | awk '{print $1}')" == "c106fa6441b15873d0d2d9b29d636434625edcd58f4033a4700589cb91e19e82" ]]
  unzip -q "$job_zip" -d "$JOB_ROOT"
  (
    cd "$JOB_ROOT"
    sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  )
  for module in \
    protected_subband_scheduler.py \
    candidate_v4_4_scheduling_campaign.py \
    companion_aware_scheduler.py \
    candidate_v4_5_companion_aware_campaign.py
  do
    cp "$PACKAGE_ROOT/src/fr3_cbf/$module" "$JOB_ROOT/src/fr3_cbf/"
  done
  : > "$RUN_ROOT/V45_OVERLAY_MANIFEST.sha256"
  for module in \
    protected_subband_scheduler.py \
    candidate_v4_4_scheduling_campaign.py \
    companion_aware_scheduler.py \
    candidate_v4_5_companion_aware_campaign.py
  do
    printf '%s  %s\n' \
      "$(sha256sum "$JOB_ROOT/src/fr3_cbf/$module" | awk '{print $1}')" \
      "src/fr3_cbf/$module" >> "$RUN_ROOT/V45_OVERLAY_MANIFEST.sha256"
    [[ "$(sha256sum "$PACKAGE_ROOT/src/fr3_cbf/$module" | awk '{print $1}')" == \
        "$(sha256sum "$JOB_ROOT/src/fr3_cbf/$module" | awk '{print $1}')" ]]
  done
  echo "REMOTE_JOB_PACKAGE_MANIFEST_VERIFICATION=PASS"
  echo "REMOTE_V45_OVERLAY_MANIFEST_VERIFICATION=PASS"
  echo "CANDIDATE_V4_3_IMMUTABLE_ARCHIVE_MODIFIED=NO"
  echo "RUN_SPECIFIC_V4_5_MODULE_OVERLAY=PASS"

  diagnosis_zip="$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_18150465.zip"
  [[ "$(sha256sum "$diagnosis_zip" | awk '{print $1}')" == "4d8181b7b328d12dad0070e2e531bb4661e87e8aaf1c6a8e59184bf66ae0e62e" ]]
  mkdir -p "$RUN_ROOT/local_audit"
  "$VENV/bin/python" "$PACKAGE_ROOT/scripts/audit_failed_seed_diagnosis.py" \
    --diagnosis-zip "$diagnosis_zip" \
    --output-json "$RUN_ROOT/local_audit/IMMUTABLE_FAILED_SEED_DIAGNOSIS_AUDIT.json" \
    >"$LOG_ROOT/failed_seed_diagnosis_audit.log" 2>&1
  "$VENV/bin/python" "$PACKAGE_ROOT/scripts/audit_scheduling_necessity.py" \
    --diagnosis-zip "$diagnosis_zip" \
    --output-json "$RUN_ROOT/local_audit/SCHEDULING_NECESSITY_AND_PLAUSIBILITY_AUDIT.json" \
    >"$LOG_ROOT/scheduling_necessity_audit.log" 2>&1
  "$VENV/bin/python" "$PACKAGE_ROOT/scripts/audit_v44_companion_mode_gap.py" \
    --v44-return-zip "$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_4_SCHEDULING_INFRA_REPAIR_R1_18154672.zip" \
    --diagnosis-zip "$diagnosis_zip" \
    --output-json "$RUN_ROOT/local_audit/CERTIFIED_V44_COMPANION_MODE_GAP_AUDIT.json" \
    >"$LOG_ROOT/prior_v44_infrastructure_failure_audit.log" 2>&1
  cat "$LOG_ROOT/failed_seed_diagnosis_audit.log"
  cat "$LOG_ROOT/scheduling_necessity_audit.log"
  cat "$LOG_ROOT/prior_v44_infrastructure_failure_audit.log"

  [[ -x "$VENV/bin/python" ]]
  "$VENV/bin/python" -m pip check
  echo "RORQUAL_REFERENCE_VENV_GATE=PASS"

  FAILED_SEEDS=(44001 44007 44008 44013 44017 44018 44024 44025 44026 44027 44028)
  for seed in "${FAILED_SEEDS[@]}"; do
    [[ -f "$CAMPAIGN_RUN_ROOT/results/seed_${seed}/channel/CHANNEL_RECORD.json" ]]
    [[ -f "$CAMPAIGN_RUN_ROOT/results/seed_${seed}/channel/frequency_response.npy" ]]
    [[ -f "$CAMPAIGN_RUN_ROOT/results/seed_${seed}/result/SEED_RESULT.json" ]]
    [[ -f "$CAMPAIGN_RUN_ROOT/results/seed_${seed}/result/CELL_SUMMARY.csv" ]]
  done
  echo "RORQUAL_PRESERVED_CHANNEL_BINDING=PASS"

  auth="$CAMPAIGN_RUN_ROOT/private/FULL_30_SEED_AUTHORIZATION.json"
  [[ ! -e "$auth" ]]
  echo "AUTHORIZATION_TOKEN_PRESENT=NO"

  active="$(squeue -u "$USER" -h -o '%i|%j|%T' | grep -E '\|(fr3-v45-comp|fr3-v45-comp-merge)\|' || true)"
  if [[ -n "$active" ]]; then
    echo "V45_COMPANION_CONCURRENT_RUN_GUARD=FAIL"
    printf '%s\n' "$active"
    exit 73
  fi
  echo "V45_COMPANION_CONCURRENT_RUN_GUARD=PASS"

  ARRAY_SBATCH="$RUN_ROOT/v45_companion_array.sbatch"
  cat > "$ARRAY_SBATCH" <<EOF_ARRAY
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-comp
#SBATCH --array=0-10%4
#SBATCH --cpus-per-task=8
#SBATCH --mem=8G
#SBATCH --time=00:06:00
#SBATCH --output=$SLURM_ROOT/%x-%A_%a.out
#SBATCH --error=$SLURM_ROOT/%x-%A_%a.err
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
if "$VENV/bin/python" "$PACKAGE_ROOT/scripts/replay_v45_companion_aware_seed.py" \
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
 'status':'PASS' if int(sys.argv[3])==0 else ('SCIENTIFIC_REVIEW_REQUIRED' if int(sys.argv[3])==42 else 'INFRASTRUCTURE_REVIEW_REQUIRED'),
}
path.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY_TASK
exit "\$RC"
EOF_ARRAY

  MERGE_SBATCH="$RUN_ROOT/v45_companion_merge.sbatch"
  cat > "$MERGE_SBATCH" <<EOF_MERGE
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-comp-merge
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
#SBATCH --time=00:03:00
#SBATCH --output=$SLURM_ROOT/%x-%j.out
#SBATCH --error=$SLURM_ROOT/%x-%j.err
set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
if "$VENV/bin/python" "$PACKAGE_ROOT/scripts/merge_v45_companion_aware_development.py" \
    --task-root "$TASK_ROOT" \
    --campaign-run-root "$CAMPAIGN_RUN_ROOT" \
    --diagnosis-audit "$RUN_ROOT/local_audit/IMMUTABLE_FAILED_SEED_DIAGNOSIS_AUDIT.json" \
    --output-dir "$MERGED_ROOT" \
    >"$LOG_ROOT/merge_stdout.log" 2>"$LOG_ROOT/merge_stderr.log"; then
  RC=0
else
  RC=\$?
fi
printf '%s\n' "\$RC" >"$MERGED_ROOT/merge_exit_code.txt"
cat "$LOG_ROOT/merge_stdout.log"
if [[ -s "$LOG_ROOT/merge_stderr.log" ]]; then cat "$LOG_ROOT/merge_stderr.log" >&2; fi
exit "\$RC"
EOF_MERGE

  ARRAY_JOB_ID="$(sbatch --parsable --account=def-rsadve_cpu "$ARRAY_SBATCH")"
  MERGE_JOB_ID="$(sbatch --parsable --account=def-rsadve_cpu --dependency="afterany:$ARRAY_JOB_ID" "$MERGE_SBATCH")"
  cat > "$STATE_FILE" <<EOF_STATE
ARRAY_JOB_ID='$ARRAY_JOB_ID'
MERGE_JOB_ID='$MERGE_JOB_ID'
PACKAGE_ROOT='$PACKAGE_ROOT'
JOB_ROOT='$JOB_ROOT'
EOF_STATE
  printf '%s\n' \
    "V45_COMPANION_AWARE_SUBMISSION=PASS" \
    "ARRAY_JOB_ID=$ARRAY_JOB_ID" \
    "MERGE_JOB_ID=$MERGE_JOB_ID" \
    "WORKER_ARRAY=0-10%4"
fi

while squeue -h -j "$MERGE_JOB_ID" | grep -q .; do
  echo "V45_COMPANION_PROGRESS_BEGIN"
  squeue -j "$ARRAY_JOB_ID,$MERGE_JOB_ID" -o '%.24i %.24j %.12T %.12M %.28R' || true
  echo "V45_COMPANION_PROGRESS_END"
  sleep 20
done
sleep 3

sacct -X -j "$ARRAY_JOB_ID,$MERGE_JOB_ID" \
  --format=JobIDRaw,JobName,Account,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES,NodeList \
  --parsable2 | tee "$SLURM_ROOT/sacct_v45_companion.txt" || true

if "$VENV/bin/python" "$PACKAGE_ROOT/scripts/package_v45_companion_aware_return.py" \
    --run-root "$RUN_ROOT" \
    --package-root "$PACKAGE_ROOT" \
    --array-job-id "$ARRAY_JOB_ID" \
    --merge-job-id "$MERGE_JOB_ID" \
    --output-dir "$RETURN_ROOT" \
    >"$LOG_ROOT/return_packaging.log" 2>&1; then
  PACKAGING_RC=0
else
  PACKAGING_RC=$?
fi
cat "$LOG_ROOT/return_packaging.log" || true

if [[ "$PACKAGING_RC" -eq 0 ]]; then
  RETURN_ZIP="$(grep '^REMOTE_RETURN_ZIP=' "$LOG_ROOT/return_packaging.log" | tail -n 1 | cut -d= -f2-)"
  RETURN_SHA="$(grep '^REMOTE_RETURN_ZIP_SHA256=' "$LOG_ROOT/return_packaging.log" | tail -n 1 | cut -d= -f2-)"
else
  echo "PRIMARY_RETURN_PACKAGING_EXIT_CODE=$PACKAGING_RC"
  mapfile -t EMERGENCY_VALUES < <(
    "$VENV/bin/python" - \
      "$RUN_ROOT" "$PACKAGE_ROOT" "$RETURN_ROOT" \
      "$ARRAY_JOB_ID" "$MERGE_JOB_ID" "$PACKAGING_RC" <<'PY_EMERGENCY'
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

run_root=Path(sys.argv[1]).resolve()
package_root=Path(sys.argv[2]).resolve()
return_root=Path(sys.argv[3]).resolve()
array_job_id=sys.argv[4]
merge_job_id=sys.argv[5]
packaging_rc=int(sys.argv[6])
name=f"FR3_RORQUAL_V4_5_COMPANION_AWARE_DEVELOPMENT_{array_job_id}_EMERGENCY"
stage=return_root/name
if stage.exists():
    shutil.rmtree(stage)
stage.mkdir(parents=True)

def copy_path(source: Path, relative: str) -> None:
    if source.is_file():
        target=stage/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
    elif source.is_dir():
        shutil.copytree(source,stage/relative,dirs_exist_ok=True)

for source,relative in (
    (package_root/'PACKAGE_VERSION.json','bindings/PACKAGE_VERSION.json'),
    (package_root/'config/V45_COMPANION_AWARE_DEVELOPMENT_CONTRACT.json','bindings/V45_COMPANION_AWARE_DEVELOPMENT_CONTRACT.json'),
    (run_root/'local_audit','audits'),
    (run_root/'merged','merged'),
    (run_root/'logs','logs'),
    (run_root/'slurm','slurm'),
    (run_root/'tasks','tasks'),
):
    copy_path(source,relative)
status={
    'schema_version':1,
    'status':'EMERGENCY_RETURN_PRIMARY_PACKAGING_FAILED',
    'created_utc':datetime.now(timezone.utc).isoformat(),
    'primary_packaging_exit_code':packaging_rc,
    'array_job_id':array_job_id,
    'merge_job_id':merge_job_id,
    'channel_regenerated':False,
    'gpu_requested':False,
    'campaign_rerun_authorized':False,
}
(stage/'EMERGENCY_RETURN_STATUS.json').write_text(
    json.dumps(status,indent=2,sort_keys=True)+'\n',encoding='utf-8'
)

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()
manifest=[]
for path in sorted(stage.rglob('*')):
    if path.is_file() and path.name!='RETURN_MANIFEST.sha256':
        manifest.append(f"{digest(path)}  {path.relative_to(stage).as_posix()}")
(stage/'RETURN_MANIFEST.sha256').write_text('\n'.join(manifest)+'\n',encoding='utf-8')
archive=return_root/f'{name}.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zf:
    for path in sorted(stage.rglob('*')):
        if path.is_file():
            zf.write(path,arcname=f'{name}/{path.relative_to(stage).as_posix()}')
with zipfile.ZipFile(archive) as zf:
    bad=zf.testzip()
    if bad is not None:
        raise RuntimeError(f'emergency ZIP CRC failure: {bad}')
archive_digest=digest(archive)
Path(str(archive)+'.sha256').write_text(
    f'{archive_digest}  {archive.name}\n',encoding='utf-8'
)
shutil.rmtree(stage)
print(str(archive))
print(archive_digest)
PY_EMERGENCY
  )
  RETURN_ZIP="${EMERGENCY_VALUES[0]:-}"
  RETURN_SHA="${EMERGENCY_VALUES[1]:-}"
  echo "EMERGENCY_REMOTE_RETURN_PACKAGING=PASS"
fi
[[ -f "$RETURN_ZIP" && -f "$RETURN_ZIP.sha256" ]]

SUMMARY="$MERGED_ROOT/V45_COMPANION_AWARE_DEVELOPMENT_SUMMARY.json"
if [[ -f "$SUMMARY" ]]; then
  "$VENV/bin/python" - "$SUMMARY" <<'PY_SUMMARY'
import json,sys
j=json.load(open(sys.argv[1],encoding='utf-8'))
for key in (
 'status','failed_seed_hard_gate_pass_count','failed_seed_bounded_scope_pass_count',
 'original_v4_3_unresolved_interval_count','scheduling_success_interval_count',
 'scheduling_failure_interval_count','candidate_floor_violation_user_seconds',
 'candidate_long_eess_violation_seconds','candidate_short_eess_violation_seconds',
 'maximum_protected_subband_scheduled_fraction','maximum_schedule_mutable_sector_count',
 'all30_development_primary_candidate_minus_static','next_repair_decision','next_gate'):
 print(f"{key}={j.get(key)}")
PY_SUMMARY
  SCIENTIFIC_RC="$($VENV/bin/python - "$SUMMARY" <<'PY_RC'
import json,sys
status=str(json.load(open(sys.argv[1],encoding='utf-8')).get('status',''))
print(0 if status.startswith('PASS_') else 42)
PY_RC
)"
else
  SCIENTIFIC_RC=20
fi
if [[ "$PACKAGING_RC" -ne 0 ]]; then
  SCIENTIFIC_RC=90
fi

MERGE_STATE="$(sacct -X -n -j "$MERGE_JOB_ID" --format=State | head -n1 | xargs || true)"
MERGE_EXIT_CODE="$(sacct -X -n -j "$MERGE_JOB_ID" --format=ExitCode | head -n1 | xargs || true)"
printf '%s\n' \
  "REMOTE_RETURN_ZIP=$RETURN_ZIP" \
  "REMOTE_RETURN_ZIP_SHA256=$RETURN_SHA" \
  "ARRAY_JOB_ID=$ARRAY_JOB_ID" \
  "MERGE_JOB_ID=$MERGE_JOB_ID" \
  "MERGE_STATE=${MERGE_STATE:-UNKNOWN}" \
  "MERGE_EXIT_CODE=${MERGE_EXIT_CODE:-UNKNOWN}" \
  "CHANNEL_REGENERATION=NO" \
  "GPU_REQUESTED=NO" \
  "WORKER_WALLTIME=00:06:00" \
  "WORKER_MEMORY=8G" \
  "MERGE_WALLTIME=00:03:00" \
  "MERGE_MEMORY=4G" \
  "REMOTE_WRAPPER_EXIT_CODE=$SCIENTIFIC_RC"
exit "$SCIENTIFIC_RC"
