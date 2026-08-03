#!/usr/bin/env bash
set -Eeuo pipefail

REMOTE_ARCHIVE="$1"
EXPECTED_ARCHIVE_SHA256="$2"
SCRATCH_LINK="${FR3_RORQUAL_SCRATCH_LINK:-/home/rsadve1/links/scratch}"
ORIGINAL_RUN="/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813"
ORIGINAL_JOB="$ORIGINAL_RUN/job_package"
VENV="/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
REMOTE_ROOT="$SCRATCH_LINK/FR3_V45_HOLDOUT_COMPLETION_R1_${STAMP}"
SOURCE_EXTRACT="$REMOTE_ROOT/source_extract"
COMPLETION="$ORIGINAL_RUN/holdout_completion_r1"
SLURM_DIR="$COMPLETION/slurm"
MERGED_ROOT="$COMPLETION/merged"
RETURN_DIR="$COMPLETION/return"
TOKEN="$COMPLETION/private/SEED44052_COMPLETION_AUTHORIZATION.json"
STATE_FILE="$COMPLETION/ACTIVE_COMPLETION.env"
REPAIR_JOB="$COMPLETION/repair_job_package"

mkdir -p "$REMOTE_ROOT" "$SOURCE_EXTRACT" "$SLURM_DIR" "$RETURN_DIR" "$COMPLETION/private"

remote_failure() {
  local rc=$?
  trap - ERR
  set +e
  local preserve_token=NO
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE" 2>/dev/null || true
    if [[ -n "${SEED_JOB_ID:-}" ]] && squeue -h -j "$SEED_JOB_ID" 2>/dev/null | grep -q .; then
      preserve_token=YES
    fi
  fi
  if [[ "$preserve_token" != YES ]]; then
    rm -f "$TOKEN"
  fi
  local archive="$RETURN_DIR/FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R1_PREJOB_FAILURE.zip"
  python3 - "$archive" "$REMOTE_ROOT" "$COMPLETION" "$ORIGINAL_RUN" "$rc" <<'PY_REMOTE_FAILURE'
from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile

archive=Path(sys.argv[1])
remote_root=Path(sys.argv[2])
completion=Path(sys.argv[3])
original_run=Path(sys.argv[4])
exit_code=int(sys.argv[5])
name=archive.stem
archive.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='fr3-v45-remote-failure-') as td:
    payload=Path(td)/name
    payload.mkdir()
    metadata={
        'schema_version':1,
        'status':'REMOTE_HOLDOUT_COMPLETION_ORCHESTRATION_FAILURE',
        'exit_code':exit_code,
        'seed_rerun_list':[44052],
        'channel_regenerated':False,
        'gpu_requested':False,
        'automatic_extra_seeds_authorized':False,
        'authorization_token_included':False,
    }
    (payload/'FAILURE_METADATA.json').write_text(
        json.dumps(metadata,indent=2,sort_keys=True)+'\n', encoding='utf-8'
    )
    candidates=[]
    for root in (remote_root, completion/'slurm', original_run/'results'/'seed_44052'):
        if root.is_dir():
            for source in sorted(root.rglob('*')):
                if not source.is_file() or source.suffix in {'.npy','.npz'}:
                    continue
                if source.name == 'SEED44052_COMPLETION_AUTHORIZATION.json':
                    continue
                candidates.append((root,source))
    seen=set()
    for root,source in candidates:
        rel=(Path(root.name)/source.relative_to(root)).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        target=payload/'diagnostics'/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        try:
            shutil.copy2(source,target)
        except OSError:
            pass
    lines=[]
    for source in sorted(payload.rglob('*')):
        if source.is_file() and source.name!='RETURN_MANIFEST.sha256':
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            lines.append(f'{digest}  {source.relative_to(payload).as_posix()}\n')
    (payload/'RETURN_MANIFEST.sha256').write_text(''.join(lines), encoding='utf-8')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zf:
        for source in sorted(payload.rglob('*')):
            if source.is_file():
                zf.write(source,source.relative_to(Path(td)).as_posix())
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
Path(str(archive)+'.sha256').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
print('REMOTE_FAILURE_RETURN_PACKAGING=PASS')
print('REMOTE_HOLDOUT_COMPLETION_RETURN_ZIP='+str(archive))
print('REMOTE_HOLDOUT_COMPLETION_RETURN_ZIP_SHA256='+digest)
PY_REMOTE_FAILURE
  printf '%s\n' \
    "REMOTE_WRAPPER_UNEXPECTED_EXIT_CODE=$rc" \
    "AUTHORIZATION_TOKEN_PRESERVED_FOR_ACTIVE_JOB=$preserve_token" \
    "AUTHORIZATION_TOKEN_PRESENT_AFTER_FAILURE=$([[ -e "$TOKEN" ]] && echo YES || echo NO)" \
    'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO' \
    'NEXT_GATE=REVIEW_COMPLETION_FAILURE_WITHOUT_AUTOMATIC_EXTRA_PROBES'
  exit "$rc"
}
trap remote_failure ERR

emit_merged_markers() {
  if [[ -f "$MERGED_ROOT/PHASE1_MERGED_AUDIT.json" ]]; then
    python3 - "$MERGED_ROOT/PHASE1_MERGED_AUDIT.json" <<'PY_MARKERS'
import json,sys
v=json.load(open(sys.argv[1], encoding='utf-8'))
p=v['primary_bootstrap']
print('HOLDOUT_RETURN_STATUS='+v['status'])
print('HOLDOUT_VALID_RESULT='+str(v['valid_holdout_result']))
print('HOLDOUT_SEED_RETURN_COUNT='+str(v['seed_count']))
print('HOLDOUT_SEED_SAFETY_PASS_COUNT='+('30' if v['safety_gates_pass'] else 'UNKNOWN'))
print('HOLDOUT_SEED_ZERO_FLOOR_PASS_COUNT='+str(v['seed_hard_gate_pass_count']))
print('HOLDOUT_PRIMARY_SUPERIORITY_MET='+str(v['primary_superiority_met']))
print('HOLDOUT_FLOOR_ZERO='+str(v['floor_zero']))
print('PRIMARY_POINT_ESTIMATE='+str(p['point_estimate']))
print('PRIMARY_LOWER_95='+str(p['lower_95']))
print('PRIMARY_UPPER_95='+str(p['upper_95']))
print('PAPER_WRITING_AUTHORIZED='+str(v['paper_writing_authorized']))
PY_MARKERS
  fi
}

ACTUAL_ARCHIVE_SHA256="$(sha256sum "$REMOTE_ARCHIVE" | awk '{print $1}')"
[[ "$ACTUAL_ARCHIVE_SHA256" == "$EXPECTED_ARCHIVE_SHA256" ]]
echo "REMOTE_COMPLETION_PACKAGE_SHA256_GATE=PASS"

unzip -q "$REMOTE_ARCHIVE" -d "$SOURCE_EXTRACT"
SOURCE_ROOT="$(find "$SOURCE_EXTRACT" -mindepth 1 -maxdepth 1 -type d | head -n1)"
[[ -n "$SOURCE_ROOT" && -d "$SOURCE_ROOT" ]]
(
  cd "$SOURCE_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo "REMOTE_COMPLETION_PACKAGE_MANIFEST_VERIFICATION=PASS"

CONTRACT="$SOURCE_ROOT/config/HOLDOUT_COMPLETION_REPAIR_CONTRACT.json"
[[ -d "$ORIGINAL_RUN" && -d "$ORIGINAL_JOB" && -x "$VENV/bin/python" ]]
(
  cd "$ORIGINAL_JOB"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
)
echo "ORIGINAL_HOLDOUT_JOB_PACKAGE_MANIFEST=PASS"

EXPECTED_CHANNEL_RECORD_SHA="$(python3 - "$CONTRACT" <<'PY_CHANNEL_RECORD'
import json,sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['seed44052_completion']['channel_record_file_sha256'])
PY_CHANNEL_RECORD
)"
EXPECTED_FREQUENCY_SHA="$(python3 - "$CONTRACT" <<'PY_FREQUENCY'
import json,sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['seed44052_completion']['frequency_response_array_sha256'])
PY_FREQUENCY
)"
CHANNEL_RECORD="$ORIGINAL_RUN/results/seed_44052/channel/CHANNEL_RECORD.json"
[[ -f "$CHANNEL_RECORD" ]]
[[ "$(sha256sum "$CHANNEL_RECORD" | awk '{print $1}')" == "$EXPECTED_CHANNEL_RECORD_SHA" ]]
ACTUAL_FREQUENCY_SHA="$(python3 - "$CHANNEL_RECORD" <<'PY_ACTUAL_FREQUENCY'
import json,sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['frequency_response_sha256_array_bytes'])
PY_ACTUAL_FREQUENCY
)"
[[ "$ACTUAL_FREQUENCY_SHA" == "$EXPECTED_FREQUENCY_SHA" ]]
echo "SEED44052_PRESERVED_CHANNEL_BINDING=PASS"
echo "CHANNEL_REGENERATION=NO"
echo "GPU_REQUESTED=NO"

EXISTING_RETURN="$(find "$RETURN_DIR" -maxdepth 1 -type f -name 'FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R1_*.zip' ! -name '*PREJOB_FAILURE*' -print | sort | tail -n1 || true)"
if [[ -n "$EXISTING_RETURN" && -f "$EXISTING_RETURN.sha256" ]]; then
  echo 'EXISTING_HOLDOUT_COMPLETION_RUN_ATTACHED=YES'
  echo "REMOTE_HOLDOUT_COMPLETION_RETURN_ZIP=$EXISTING_RETURN"
  echo "REMOTE_HOLDOUT_COMPLETION_RETURN_ZIP_SHA256=$(sha256sum "$EXISTING_RETURN" | awk '{print $1}')"
  emit_merged_markers
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    printf '%s\n' "SEED44052_JOB_ID=${SEED_JOB_ID:-UNKNOWN}" "MERGE_JOB_ID=${MERGE_JOB_ID:-UNKNOWN}"
  fi
  echo 'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO'
  echo 'NEXT_GATE=FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION'
  exit 0
fi

ATTACHED=NO
if [[ -f "$STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  [[ "${COMPLETION_PACKAGE_SHA256:-}" == "$EXPECTED_ARCHIVE_SHA256" ]]
  [[ -n "${SEED_JOB_ID:-}" && -n "${MERGE_JOB_ID:-}" ]]
  [[ -d "$REPAIR_JOB" ]]
  ATTACHED=YES
  echo 'EXISTING_HOLDOUT_COMPLETION_RUN_ATTACHED=YES'
else
  if squeue -h -u "$USER" -n fr3-v45-s44052-r1,fr3-v45-complete-merge 2>/dev/null | grep -q .; then
    echo 'RORQUAL_CONCURRENT_COMPLETION_GUARD=FAIL_UNBOUND_ACTIVE_JOB'
    false
  fi
  echo 'RORQUAL_CONCURRENT_COMPLETION_GUARD=PASS'
  rm -rf "$REPAIR_JOB" "$MERGED_ROOT"
  cp -a "$ORIGINAL_JOB" "$REPAIR_JOB"
  cp "$SOURCE_ROOT/scripts/validate_seed_result_repaired.py" "$REPAIR_JOB/validate_seed_result.py"
  cp "$SOURCE_ROOT/scripts/validator_contract.py" "$REPAIR_JOB/validator_contract.py"

  "$VENV/bin/python" "$SOURCE_ROOT/scripts/issue_seed44052_completion_authorization.py" \
    --job-package-root "$ORIGINAL_JOB" \
    --completion-contract "$CONTRACT" \
    --output "$TOKEN"

  SEED_SBATCH="$SLURM_DIR/v45_seed44052_completion.sbatch"
  cat > "$SEED_SBATCH" <<EOF_SEED
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-s44052-r1
#SBATCH --account=def-rsadve_cpu
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=00:12:00
#SBATCH --output=$SLURM_DIR/%x-%j.out
#SBATCH --error=$SLURM_DIR/%x-%j.err
set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source '$VENV/bin/activate'
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export PHASE1_AUTHORIZATION_FILE='$TOKEN'
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
SEED_ROOT='$ORIGINAL_RUN/results/seed_44052'
mkdir -p "\$SEED_ROOT"
if '$VENV/bin/python' '$SOURCE_ROOT/scripts/run_seed44052_capacity_completion.py' \
    --job-package-root '$ORIGINAL_JOB' \
    --output-root '$ORIGINAL_RUN/results' \
    --completion-contract '$CONTRACT' \
    >"\$SEED_ROOT/worker_stdout.log" 2>"\$SEED_ROOT/worker_stderr.log"; then
  WORKER_RC=0
else
  WORKER_RC=\$?
fi
if '$VENV/bin/python' '$REPAIR_JOB/validate_seed_result.py' \
    --result-dir "\$SEED_ROOT/result" \
    --package-contract '$REPAIR_JOB/JOB_PACKAGE_CONTRACT.json' \
    >"\$SEED_ROOT/repaired_validator_stdout.log" \
    2>"\$SEED_ROOT/repaired_validator_stderr.log"; then
  VALIDATOR_RC=0
else
  VALIDATOR_RC=\$?
fi
PACKAGE_ID="\$('$VENV/bin/python' - '$ORIGINAL_JOB/JOB_PACKAGE_CONTRACT.json' <<'PY_PACKAGE_ID'
import json,sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['package_id'])
PY_PACKAGE_ID
)"
'$VENV/bin/python' '$ORIGINAL_JOB/package_seed_result.py' \
  --seed-root "\$SEED_ROOT" --seed 44052 --package-id "\$PACKAGE_ID" \
  --worker-exit-code "\$WORKER_RC" --validator-exit-code "\$VALIDATOR_RC"
printf '%s\n' \
  "SEED44052_WORKER_EXIT_CODE=\$WORKER_RC" \
  "SEED44052_REPAIRED_VALIDATOR_EXIT_CODE=\$VALIDATOR_RC" \
  'CHANNEL_REGENERATION=NO' \
  'GPU_REQUESTED=NO'
if [[ "\$VALIDATOR_RC" -ne 0 ]]; then exit "\$VALIDATOR_RC"; fi
exit "\$WORKER_RC"
EOF_SEED
  chmod +x "$SEED_SBATCH"

  MERGE_SBATCH="$SLURM_DIR/v45_holdout_completion_merge.sbatch"
  cat > "$MERGE_SBATCH" <<EOF_MERGE
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-complete-merge
#SBATCH --account=def-rsadve_cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:05:00
#SBATCH --output=$SLURM_DIR/%x-%j.out
#SBATCH --error=$SLURM_DIR/%x-%j.err
set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source '$VENV/bin/activate'
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
rm -rf '$MERGED_ROOT'
if '$VENV/bin/python' '$REPAIR_JOB/merge_phase1_results.py' \
    --seed-root '$ORIGINAL_RUN/results' \
    --package-root '$REPAIR_JOB' \
    --output-root '$MERGED_ROOT'; then
  MERGE_RC=0
else
  MERGE_RC=\$?
fi
if [[ -f '$MERGED_ROOT/PHASE1_MERGED_AUDIT.json' ]]; then
  if '$VENV/bin/python' '$SOURCE_ROOT/scripts/audit_completed_holdout.py' \
      --merged-root '$MERGED_ROOT' \
      --seed44052-result-root '$ORIGINAL_RUN/results/seed_44052/result' \
      --output-json '$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json' \
      --output-tex '$COMPLETION/holdout_key_results.tex'; then
    AUDIT_RC=0
  else
    AUDIT_RC=\$?
  fi
else
  AUDIT_RC=42
  '$VENV/bin/python' - '$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json' "\$MERGE_RC" <<'PY_INCOMPLETE_AUDIT'
import json,sys
json.dump({
 'schema_version':1,
 'status':'INCOMPLETE_HOLDOUT_COMPLETION_REVIEW_REQUIRED',
 'merge_exit_code':int(sys.argv[2]),
 'automatic_extra_seeds_authorized':False,
 'next_gate':'REVIEW_COMPLETION_FAILURE_WITHOUT_AUTOMATIC_EXTRA_PROBES'
}, open(sys.argv[1],'w'), indent=2, sort_keys=True)
open(sys.argv[1],'a').write('\n')
PY_INCOMPLETE_AUDIT
  printf '%% Holdout completion did not produce a complete merged audit.\n' > '$COMPLETION/holdout_key_results.tex'
fi
printf '%s\n' "HOLDOUT_COMPLETION_MERGE_EXIT_CODE=\$MERGE_RC" "HOLDOUT_COMPLETION_AUDIT_EXIT_CODE=\$AUDIT_RC"
if [[ "\$MERGE_RC" -ne 0 ]]; then exit "\$MERGE_RC"; fi
exit "\$AUDIT_RC"
EOF_MERGE
  chmod +x "$MERGE_SBATCH"

  SEED_JOB_ID="$(sbatch --parsable "$SEED_SBATCH")"
  MERGE_JOB_ID="$(sbatch --parsable --dependency=afterany:"$SEED_JOB_ID" "$MERGE_SBATCH")"
  cat > "$STATE_FILE" <<EOF_STATE
COMPLETION_PACKAGE_SHA256=$EXPECTED_ARCHIVE_SHA256
SEED_JOB_ID=$SEED_JOB_ID
MERGE_JOB_ID=$MERGE_JOB_ID
EOF_STATE
  chmod 600 "$STATE_FILE"
  echo 'HOLDOUT_COMPLETION_SUBMISSION=PASS'
fi

printf '%s\n' \
  "SEED44052_JOB_ID=$SEED_JOB_ID" \
  "MERGE_JOB_ID=$MERGE_JOB_ID" \
  "EXISTING_HOLDOUT_COMPLETION_RUN_ATTACHED=$ATTACHED" \
  'SEED_WORKER_WALLTIME=00:12:00' \
  'SEED_WORKER_MEMORY=16G' \
  'MERGE_WALLTIME=00:05:00' \
  'MERGE_MEMORY=8G'

while squeue -h -j "$MERGE_JOB_ID" 2>/dev/null | grep -q .; do
  squeue -j "$SEED_JOB_ID,$MERGE_JOB_ID" -o '%.18i %.28j %.10T %.10M %R' || true
  sleep 15
done
sleep 2
sacct -j "$SEED_JOB_ID,$MERGE_JOB_ID" \
  --format=JobID,JobName,Account,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES%90 \
  -P > "$SLURM_DIR/sacct_completion.txt" || true
cat "$SLURM_DIR/sacct_completion.txt"

SEED_ROOT="$ORIGINAL_RUN/results/seed_44052"
for report in "$SEED_ROOT/worker_stdout.log" "$SEED_ROOT/repaired_validator_stdout.log"; do
  if [[ -f "$report" ]]; then
    grep -E '^(SEED44052_CAPACITY_COMPLETION|ORIGINAL_MODE_COUNT_GUARD|OBSERVED_REQUIRED_MODE_COUNT|REPAIRED_MODE_COUNT_GUARD|SCIENTIFIC_SOURCE_FILES_MODIFIED|ACTION_LIBRARY_DEFINITION_CHANGED|CHANNEL_REUSED|SEED44052_SCIENTIFIC_EXIT_CODE|PAYLOAD_LOWER_BOUND_CONTRACT_REPAIR|FRESH_V4_5_HOLDOUT_SEED_STRUCTURAL_VALIDATION|CANDIDATE_HARD_GATES|SCIENTIFIC_EXIT_CODE)=' "$report" || true
  fi
done

rm -f "$TOKEN"
echo "AUTHORIZATION_TOKEN_PRESENT_AFTER_COMPLETION=$([[ -e "$TOKEN" ]] && echo YES || echo NO)"

if [[ ! -f "$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json" ]]; then
  python3 - "$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json" <<'PY_MISSING_AUDIT'
import json,sys
json.dump({
 'schema_version':1,
 'status':'COMPLETION_AUDIT_MISSING',
 'automatic_extra_seeds_authorized':False
},open(sys.argv[1],'w'),indent=2,sort_keys=True)
open(sys.argv[1],'a').write('\n')
PY_MISSING_AUDIT
fi
[[ -f "$COMPLETION/holdout_key_results.tex" ]] || printf '%% unavailable\n' > "$COMPLETION/holdout_key_results.tex"

"$VENV/bin/python" "$SOURCE_ROOT/scripts/package_completion_return.py" \
  --run-root "$ORIGINAL_RUN" \
  --repair-package-root "$SOURCE_ROOT" \
  --merged-root "$MERGED_ROOT" \
  --completion-audit "$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json" \
  --completion-tex "$COMPLETION/holdout_key_results.tex" \
  --seed-job-id "$SEED_JOB_ID" \
  --merge-job-id "$MERGE_JOB_ID" \
  --output-dir "$RETURN_DIR"

RETURN_ZIP="$(find "$RETURN_DIR" -maxdepth 1 -type f -name "FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R1_${SEED_JOB_ID}.zip" -print -quit)"
[[ -f "$RETURN_ZIP" && -f "$RETURN_ZIP.sha256" ]]
echo "REMOTE_HOLDOUT_COMPLETION_RETURN_ZIP=$RETURN_ZIP"
echo "REMOTE_HOLDOUT_COMPLETION_RETURN_ZIP_SHA256=$(sha256sum "$RETURN_ZIP" | awk '{print $1}')"

SEED_STATE="$(sacct -n -X -j "$SEED_JOB_ID" --format=State | awk 'NF{print $1; exit}')"
MERGE_STATE="$(sacct -n -X -j "$MERGE_JOB_ID" --format=State | awk 'NF{print $1; exit}')"
SEED_EXIT="$(sacct -n -X -j "$SEED_JOB_ID" --format=ExitCode | awk 'NF{print $1; exit}')"
MERGE_EXIT="$(sacct -n -X -j "$MERGE_JOB_ID" --format=ExitCode | awk 'NF{print $1; exit}')"
printf '%s\n' \
  "SEED44052_STATE=${SEED_STATE:-UNKNOWN}" \
  "SEED44052_SLURM_EXIT_CODE=${SEED_EXIT:-UNKNOWN}" \
  "MERGE_STATE=${MERGE_STATE:-UNKNOWN}" \
  "MERGE_SLURM_EXIT_CODE=${MERGE_EXIT:-UNKNOWN}" \
  'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO' \
  'NEXT_GATE=FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION'

emit_merged_markers
FINAL_RC="${MERGE_EXIT%%:*}"
[[ "$FINAL_RC" =~ ^[0-9]+$ ]] || FINAL_RC=1
exit "$FINAL_RC"
