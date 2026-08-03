#!/usr/bin/env bash
set -Eeuo pipefail

REMOTE_ARCHIVE="$1"
EXPECTED_ARCHIVE_SHA256="$2"
SCRATCH_LINK="${FR3_RORQUAL_SCRATCH_LINK:-/home/rsadve1/links/scratch}"
ORIGINAL_RUN="/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_00a3561864f8_20260802_214813"
ORIGINAL_JOB="$ORIGINAL_RUN/job_package"
VENV="/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_ENV_5037b4e33448/.venv"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
REMOTE_ROOT="$SCRATCH_LINK/FR3_V45_HOLDOUT_COMPLETION_R2_UPLOAD_${STAMP}"
SOURCE_EXTRACT="$REMOTE_ROOT/source_extract"
COMPLETION="$ORIGINAL_RUN/holdout_completion_r2_pass_parallel"
PASS_OUTPUT_ROOT="$COMPLETION/pass_outputs"
SLURM_DIR="$COMPLETION/slurm"
MERGED_ROOT="$COMPLETION/merged"
RETURN_DIR="$COMPLETION/return"
TOKEN="$COMPLETION/private/SEED44052_R2_AUTHORIZATION.json"
STATE_FILE="$COMPLETION/ACTIVE_COMPLETION_R2.env"
REPAIR_JOB="$COMPLETION/repair_job_package"
SEED_ROOT="$ORIGINAL_RUN/results/seed_44052"

mkdir -p "$REMOTE_ROOT" "$SOURCE_EXTRACT" "$PASS_OUTPUT_ROOT" \
  "$SLURM_DIR" "$RETURN_DIR" "$COMPLETION/private"

write_incomplete_audit() {
  local status="$1"
  local detail="$2"
  python3 - "$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json" "$status" "$detail" <<'PY'
import json,sys
from pathlib import Path
path=Path(sys.argv[1])
path.parent.mkdir(parents=True,exist_ok=True)
value={
  'schema_version':1,
  'status':sys.argv[2],
  'detail':sys.argv[3],
  'seed':44052,
  'automatic_extra_seeds_authorized':False,
  'automatic_algorithm_tuning_authorized':False,
  'channel_regenerated':False,
  'gpu_requested':False,
  'next_gate':'REVIEW_ONLY_FAILED_PASS_WITHOUT_NEW_SEEDS_OR_ALGORITHM_TUNING',
}
path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY
  printf '%% Holdout completion R2 did not produce a complete 30-seed merged audit.\n' \
    > "$COMPLETION/holdout_key_results.tex"
}

package_partial_return() {
  local pass_id="${PASS_ARRAY_JOB_ID:-PREJOB}"
  local assembly_id="${ASSEMBLY_JOB_ID:-PREJOB}"
  if [[ -n "${SOURCE_ROOT:-}" && -x "$VENV/bin/python" && \
        -f "$SOURCE_ROOT/scripts/package_completion_r2_return.py" ]]; then
    "$VENV/bin/python" "$SOURCE_ROOT/scripts/package_completion_r2_return.py" \
      --run-root "$ORIGINAL_RUN" \
      --package-root "$SOURCE_ROOT" \
      --completion-root "$COMPLETION" \
      --pass-array-job-id "$pass_id" \
      --assembly-job-id "$assembly_id" \
      --output-dir "$RETURN_DIR" || true
  fi
}

remote_failure() {
  local rc=$?
  trap - ERR
  set +e
  local active=NO
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE" 2>/dev/null || true
    if [[ -n "${PASS_ARRAY_JOB_ID:-}" ]] && \
       squeue -h -j "$PASS_ARRAY_JOB_ID" 2>/dev/null | grep -q .; then
      active=YES
    fi
    if [[ -n "${ASSEMBLY_JOB_ID:-}" ]] && \
       squeue -h -j "$ASSEMBLY_JOB_ID" 2>/dev/null | grep -q .; then
      active=YES
    fi
  fi
  if [[ "$active" != YES ]]; then
    rm -f "$TOKEN"
  fi
  [[ -f "$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json" ]] || \
    write_incomplete_audit \
      "REMOTE_HOLDOUT_COMPLETION_R2_ORCHESTRATION_FAILURE" \
      "remote wrapper exit code $rc"
  package_partial_return
  local archive
  archive="$(find "$RETURN_DIR" -maxdepth 1 -type f \
    -name 'FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R2_*.zip' \
    -print | sort | tail -n1 || true)"
  if [[ -n "$archive" ]]; then
    echo "REMOTE_HOLDOUT_COMPLETION_R2_RETURN_ZIP=$archive"
    echo "REMOTE_HOLDOUT_COMPLETION_R2_RETURN_ZIP_SHA256=$(sha256sum "$archive" | awk '{print $1}')"
  fi
  printf '%s\n' \
    "REMOTE_WRAPPER_UNEXPECTED_EXIT_CODE=$rc" \
    "ACTIVE_JOB_PRESENT_AFTER_FAILURE=$active" \
    "AUTHORIZATION_TOKEN_PRESENT_AFTER_FAILURE=$([[ -e "$TOKEN" ]] && echo YES || echo NO)" \
    'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO' \
    'AUTOMATIC_ALGORITHM_TUNING_AUTHORIZED=NO' \
    'NEXT_GATE=REVIEW_ONLY_FAILED_PASS_WITHOUT_NEW_SEEDS_OR_ALGORITHM_TUNING'
  exit "$rc"
}
trap remote_failure ERR

emit_merged_markers() {
  if [[ -f "$MERGED_ROOT/PHASE1_MERGED_AUDIT.json" ]]; then
    python3 - "$MERGED_ROOT/PHASE1_MERGED_AUDIT.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
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
PY
  fi
}

ACTUAL_ARCHIVE_SHA256="$(sha256sum "$REMOTE_ARCHIVE" | awk '{print $1}')"
[[ "$ACTUAL_ARCHIVE_SHA256" == "$EXPECTED_ARCHIVE_SHA256" ]]
echo 'REMOTE_COMPLETION_R2_PACKAGE_SHA256_GATE=PASS'

unzip -q "$REMOTE_ARCHIVE" -d "$SOURCE_EXTRACT"
SOURCE_ROOT="$(find "$SOURCE_EXTRACT" -mindepth 1 -maxdepth 1 -type d | head -n1)"
[[ -n "$SOURCE_ROOT" && -d "$SOURCE_ROOT" ]]
(
  cd "$SOURCE_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo 'REMOTE_COMPLETION_R2_PACKAGE_MANIFEST_VERIFICATION=PASS'

CONTRACT="$SOURCE_ROOT/config/HOLDOUT_COMPLETION_R2_CONTRACT.json"
[[ -d "$ORIGINAL_RUN" && -d "$ORIGINAL_JOB" && -x "$VENV/bin/python" ]]
(
  cd "$ORIGINAL_JOB"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
)
echo 'ORIGINAL_HOLDOUT_JOB_PACKAGE_MANIFEST=PASS'

"$VENV/bin/python" "$SOURCE_ROOT/scripts/audit_r1_timeout.py" \
  --contract "$CONTRACT" \
  --r1-return "$SOURCE_ROOT/immutable_bindings/FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R1_18207112.zip" \
  --holdout-return "$SOURCE_ROOT/immutable_bindings/FR3_RORQUAL_V4_5_FRESH_HOLDOUT_18163102.zip" \
  --output-json "$COMPLETION/R1_TIMEOUT_AUDIT.json"

"$VENV/bin/python" "$SOURCE_ROOT/scripts/audit_pass_parallel_equivalence.py" \
  --job-package-root "$ORIGINAL_JOB" \
  --output-json "$COMPLETION/PASS_PARALLEL_EQUIVALENCE_AUDIT.json"

CHANNEL_RECORD="$SEED_ROOT/channel/CHANNEL_RECORD.json"
[[ -f "$CHANNEL_RECORD" ]]
EXPECTED_CHANNEL_RECORD_SHA="$(python3 - "$CONTRACT" <<'PY_CHAN_SHA'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['seed44052_channel_binding']['channel_record_file_sha256'])
PY_CHAN_SHA
)"
EXPECTED_FREQUENCY_SHA="$(python3 - "$CONTRACT" <<'PY_FREQ_SHA'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['seed44052_channel_binding']['frequency_response_array_sha256'])
PY_FREQ_SHA
)"
[[ "$(sha256sum "$CHANNEL_RECORD" | awk '{print $1}')" == "$EXPECTED_CHANNEL_RECORD_SHA" ]]
python3 - "$CHANNEL_RECORD" "$EXPECTED_FREQUENCY_SHA" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
assert int(v['campaign_seed']) == 44052
assert v['frequency_response_sha256_array_bytes'] == sys.argv[2]
print('SEED44052_PRESERVED_CHANNEL_BINDING=PASS')
print('CHANNEL_RECORD_SHA256='+__import__('hashlib').sha256(open(sys.argv[1],'rb').read()).hexdigest())
print('FREQUENCY_RESPONSE_ARRAY_SHA256='+v['frequency_response_sha256_array_bytes'])
print('CHANNEL_REGENERATION=NO')
print('GPU_REQUESTED=NO')
PY

EXISTING_RETURN="$(find "$RETURN_DIR" -maxdepth 1 -type f \
  -name 'FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R2_*.zip' \
  -print | sort | tail -n1 || true)"
if [[ -n "$EXISTING_RETURN" && -f "$EXISTING_RETURN.sha256" ]]; then
  echo 'EXISTING_HOLDOUT_COMPLETION_R2_RUN_ATTACHED=YES'
  echo "REMOTE_HOLDOUT_COMPLETION_R2_RETURN_ZIP=$EXISTING_RETURN"
  echo "REMOTE_HOLDOUT_COMPLETION_R2_RETURN_ZIP_SHA256=$(sha256sum "$EXISTING_RETURN" | awk '{print $1}')"
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    echo "PASS_ARRAY_JOB_ID=${PASS_ARRAY_JOB_ID:-UNKNOWN}"
    echo "ASSEMBLY_JOB_ID=${ASSEMBLY_JOB_ID:-UNKNOWN}"
  fi
  emit_merged_markers
  echo 'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO'
  echo 'NEXT_GATE=FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION'
  exit 0
fi

ATTACHED=NO
if [[ -f "$STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  [[ "${COMPLETION_PACKAGE_SHA256:-}" == "$EXPECTED_ARCHIVE_SHA256" ]]
  [[ -n "${PASS_ARRAY_JOB_ID:-}" && -n "${ASSEMBLY_JOB_ID:-}" ]]
  ATTACHED=YES
  echo 'EXISTING_HOLDOUT_COMPLETION_R2_RUN_ATTACHED=YES'
else
  if squeue -h -u "$USER" -n fr3-v45-s44052-pass-r2,fr3-v45-s44052-assemble-r2 \
      2>/dev/null | grep -q .; then
    echo 'RORQUAL_CONCURRENT_COMPLETION_R2_GUARD=FAIL_UNBOUND_ACTIVE_JOB'
    false
  fi
  echo 'RORQUAL_CONCURRENT_COMPLETION_R2_GUARD=PASS'
  rm -rf "$PASS_OUTPUT_ROOT" "$MERGED_ROOT" "$REPAIR_JOB"
  mkdir -p "$PASS_OUTPUT_ROOT" "$MERGED_ROOT"
  cp -a "$ORIGINAL_JOB" "$REPAIR_JOB"
  cp "$SOURCE_ROOT/scripts/validate_seed_result_repaired.py" \
    "$REPAIR_JOB/validate_seed_result.py"
  cp "$SOURCE_ROOT/scripts/validator_contract.py" \
    "$REPAIR_JOB/validator_contract.py"

  "$VENV/bin/python" "$SOURCE_ROOT/scripts/issue_seed44052_r2_authorization.py" \
    --job-package-root "$ORIGINAL_JOB" \
    --completion-contract "$CONTRACT" \
    --output "$TOKEN"

  PASS_SBATCH="$SLURM_DIR/v45_seed44052_pass_parallel_r2.sbatch"
  cat > "$PASS_SBATCH" <<EOF_PASS
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-s44052-pass-r2
#SBATCH --account=def-rsadve_cpu
#SBATCH --array=0-4%5
#SBATCH --cpus-per-task=8
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=$SLURM_DIR/%x-%A_%a.out
#SBATCH --error=$SLURM_DIR/%x-%A_%a.err
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
PASS_SLOT="\${SLURM_ARRAY_TASK_ID}"
'$VENV/bin/python' '$SOURCE_ROOT/scripts/run_seed44052_pass.py' \
  --job-package-root '$ORIGINAL_JOB' \
  --seed-root '$SEED_ROOT' \
  --pass-output-root '$PASS_OUTPUT_ROOT' \
  --pass-slot "\$PASS_SLOT" \
  --completion-contract '$CONTRACT' \
  --authorization-file '$TOKEN'
EOF_PASS
  chmod +x "$PASS_SBATCH"

  ASSEMBLY_SBATCH="$SLURM_DIR/v45_seed44052_assembly_r2.sbatch"
  cat > "$ASSEMBLY_SBATCH" <<EOF_ASSEMBLY
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-s44052-assemble-r2
#SBATCH --account=def-rsadve_cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
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
export PHASE1_AUTHORIZATION_FILE='$TOKEN'
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
mkdir -p '$SEED_ROOT'
if '$VENV/bin/python' '$SOURCE_ROOT/scripts/assemble_seed44052.py' \
  --job-package-root '$ORIGINAL_JOB' \
  --seed-root '$SEED_ROOT' \
  --pass-output-root '$PASS_OUTPUT_ROOT' \
  --completion-contract '$CONTRACT' \
  --authorization-file '$TOKEN' \
  > '$SEED_ROOT/worker_stdout.log' \
  2> '$SEED_ROOT/worker_stderr.log'; then
  ASSEMBLY_RC=0
else
  ASSEMBLY_RC=\$?
fi
VALIDATOR_RC=99
SCIENTIFIC_RC=99
MERGE_RC=99
AUDIT_RC=99
if [[ "\$ASSEMBLY_RC" -eq 0 ]]; then
  if '$VENV/bin/python' '$REPAIR_JOB/validate_seed_result.py' \
    --result-dir '$SEED_ROOT/result' \
    --package-contract '$REPAIR_JOB/JOB_PACKAGE_CONTRACT.json' \
    > '$SEED_ROOT/repaired_validator_stdout.log' \
    2> '$SEED_ROOT/repaired_validator_stderr.log'; then
    VALIDATOR_RC=0
  else
    VALIDATOR_RC=\$?
  fi
  SCIENTIFIC_RC="\$('$VENV/bin/python' - '$SEED_ROOT/result/SEED_RESULT.json' <<'PY_SCI'
import json,sys
print(int(json.load(open(sys.argv[1],encoding='utf-8'))['scientific_exit_code']))
PY_SCI
)"
  PACKAGE_ID="\$('$VENV/bin/python' - '$ORIGINAL_JOB/JOB_PACKAGE_CONTRACT.json' <<'PY_ID'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['package_id'])
PY_ID
)"
  '$VENV/bin/python' '$ORIGINAL_JOB/package_seed_result.py' \
    --seed-root '$SEED_ROOT' \
    --seed 44052 \
    --package-id "\$PACKAGE_ID" \
    --worker-exit-code "\$SCIENTIFIC_RC" \
    --validator-exit-code "\$VALIDATOR_RC"
fi
if [[ "\$ASSEMBLY_RC" -eq 0 && "\$VALIDATOR_RC" -eq 0 ]]; then
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
      --seed44052-result-root '$SEED_ROOT/result' \
      --output-json '$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json' \
      --output-tex '$COMPLETION/holdout_key_results.tex'; then
      AUDIT_RC=0
    else
      AUDIT_RC=\$?
    fi
  fi
fi
if [[ ! -f '$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json' ]]; then
  '$VENV/bin/python' - '$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json' \
    "\$ASSEMBLY_RC" "\$VALIDATOR_RC" "\$MERGE_RC" "\$AUDIT_RC" <<'PY_INCOMPLETE'
import json,sys
value={
  'schema_version':1,
  'status':'INCOMPLETE_HOLDOUT_COMPLETION_R2_REVIEW_REQUIRED',
  'assembly_exit_code':int(sys.argv[2]),
  'validator_exit_code':int(sys.argv[3]),
  'merge_exit_code':int(sys.argv[4]),
  'audit_exit_code':int(sys.argv[5]),
  'automatic_extra_seeds_authorized':False,
  'automatic_algorithm_tuning_authorized':False,
  'next_gate':'REVIEW_ONLY_FAILED_PASS_WITHOUT_NEW_SEEDS_OR_ALGORITHM_TUNING',
}
json.dump(value,open(sys.argv[1],'w'),indent=2,sort_keys=True)
open(sys.argv[1],'a').write('\n')
PY_INCOMPLETE
  printf '%% Holdout completion R2 incomplete.\n' > '$COMPLETION/holdout_key_results.tex'
fi
printf '%s\n' \
  "SEED44052_PASS_PARALLEL_ASSEMBLY_EXIT_CODE=\$ASSEMBLY_RC" \
  "SEED44052_REPAIRED_VALIDATOR_EXIT_CODE=\$VALIDATOR_RC" \
  "SEED44052_SCIENTIFIC_EXIT_CODE=\$SCIENTIFIC_RC" \
  "HOLDOUT_COMPLETION_MERGE_EXIT_CODE=\$MERGE_RC" \
  "HOLDOUT_COMPLETION_AUDIT_EXIT_CODE=\$AUDIT_RC"
if [[ "\$ASSEMBLY_RC" -ne 0 ]]; then exit "\$ASSEMBLY_RC"; fi
if [[ "\$VALIDATOR_RC" -ne 0 ]]; then exit "\$VALIDATOR_RC"; fi
if [[ "\$MERGE_RC" -ne 0 ]]; then exit "\$MERGE_RC"; fi
exit "\$AUDIT_RC"
EOF_ASSEMBLY
  chmod +x "$ASSEMBLY_SBATCH"

  PASS_ARRAY_JOB_ID="$(sbatch --parsable "$PASS_SBATCH")"
  ASSEMBLY_JOB_ID="$(sbatch --parsable --dependency=afterany:"$PASS_ARRAY_JOB_ID" "$ASSEMBLY_SBATCH")"
  cat > "$STATE_FILE" <<EOF_STATE
COMPLETION_PACKAGE_SHA256=$EXPECTED_ARCHIVE_SHA256
PASS_ARRAY_JOB_ID=$PASS_ARRAY_JOB_ID
ASSEMBLY_JOB_ID=$ASSEMBLY_JOB_ID
EOF_STATE
  chmod 600 "$STATE_FILE"
  echo 'HOLDOUT_COMPLETION_R2_SUBMISSION=PASS'
fi

printf '%s\n' \
  "PASS_ARRAY_JOB_ID=$PASS_ARRAY_JOB_ID" \
  "ASSEMBLY_JOB_ID=$ASSEMBLY_JOB_ID" \
  "EXISTING_HOLDOUT_COMPLETION_R2_RUN_ATTACHED=$ATTACHED" \
  'PASS_WORKER_ARRAY=0-4%5' \
  'PASS_WORKER_CPUS=8' \
  'PASS_WORKER_MEMORY=4G' \
  'PASS_WORKER_WALLTIME=00:20:00' \
  'ASSEMBLY_CPUS=4' \
  'ASSEMBLY_MEMORY=4G' \
  'ASSEMBLY_WALLTIME=00:05:00'

while squeue -h -j "$ASSEMBLY_JOB_ID" 2>/dev/null | grep -q .; do
  squeue -j "$PASS_ARRAY_JOB_ID,$ASSEMBLY_JOB_ID" \
    -o '%.24i %.32j %.10T %.10M %R' || true
  sleep 20
done
sleep 2
sacct -j "$PASS_ARRAY_JOB_ID,$ASSEMBLY_JOB_ID" \
  --format=JobID,JobName,Account,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES%100 \
  -P > "$SLURM_DIR/sacct_completion_r2.txt" || true
cat "$SLURM_DIR/sacct_completion_r2.txt"

rm -f "$TOKEN"
echo "AUTHORIZATION_TOKEN_PRESENT_AFTER_COMPLETION=$([[ -e "$TOKEN" ]] && echo YES || echo NO)"

[[ -f "$COMPLETION/HOLDOUT_COMPLETION_AUDIT.json" ]] || \
  write_incomplete_audit \
    'INCOMPLETE_HOLDOUT_COMPLETION_R2_REVIEW_REQUIRED' \
    'completion audit missing after assembly job'
[[ -f "$COMPLETION/holdout_key_results.tex" ]] || \
  printf '%% unavailable\n' > "$COMPLETION/holdout_key_results.tex"

"$VENV/bin/python" "$SOURCE_ROOT/scripts/package_completion_r2_return.py" \
  --run-root "$ORIGINAL_RUN" \
  --package-root "$SOURCE_ROOT" \
  --completion-root "$COMPLETION" \
  --pass-array-job-id "$PASS_ARRAY_JOB_ID" \
  --assembly-job-id "$ASSEMBLY_JOB_ID" \
  --output-dir "$RETURN_DIR"

RETURN_ZIP="$(find "$RETURN_DIR" -maxdepth 1 -type f \
  -name "FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R2_${PASS_ARRAY_JOB_ID}.zip" \
  -print -quit)"
[[ -f "$RETURN_ZIP" && -f "$RETURN_ZIP.sha256" ]]
echo "REMOTE_HOLDOUT_COMPLETION_R2_RETURN_ZIP=$RETURN_ZIP"
echo "REMOTE_HOLDOUT_COMPLETION_R2_RETURN_ZIP_SHA256=$(sha256sum "$RETURN_ZIP" | awk '{print $1}')"

PASS_TASK_RECORD_COUNT="$(sacct -n -X -j "$PASS_ARRAY_JOB_ID" --format=JobID | \
  awk -v id="$PASS_ARRAY_JOB_ID" '$1 ~ ("^" id "_[0-4]$"){n++} END{print n+0}')"
PASS_TASK_COMPLETED_COUNT="$(sacct -n -X -j "$PASS_ARRAY_JOB_ID" --format=JobID,State | \
  awk -v id="$PASS_ARRAY_JOB_ID" '$1 ~ ("^" id "_[0-4]$") && $2=="COMPLETED"{n++} END{print n+0}')"
ASSEMBLY_STATE="$(sacct -n -X -j "$ASSEMBLY_JOB_ID" --format=State | awk 'NF{print $1;exit}')"
ASSEMBLY_EXIT="$(sacct -n -X -j "$ASSEMBLY_JOB_ID" --format=ExitCode | awk 'NF{print $1;exit}')"
printf '%s\n' \
  "PASS_TASK_RECORD_COUNT=$PASS_TASK_RECORD_COUNT" \
  "PASS_TASK_COMPLETED_COUNT=$PASS_TASK_COMPLETED_COUNT" \
  "ASSEMBLY_STATE=${ASSEMBLY_STATE:-UNKNOWN}" \
  "ASSEMBLY_SLURM_EXIT_CODE=${ASSEMBLY_EXIT:-UNKNOWN}" \
  'CHANNEL_REGENERATION=NO' \
  'GPU_REQUESTED=NO' \
  'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO' \
  'AUTOMATIC_ALGORITHM_TUNING_AUTHORIZED=NO'

for report in "$SEED_ROOT/worker_stdout.log" \
              "$SEED_ROOT/repaired_validator_stdout.log"; do
  if [[ -f "$report" ]]; then
    grep -E '^(SEED44052_PASS_PARALLEL_ASSEMBLY|SEED44052_PASS_RESULT_COUNT|SEED44052_CELL_COUNT|SEED44052_SCIENTIFIC_EXIT_CODE|SEED44052_CANDIDATE_HARD_GATES_PASS|FRESH_V4_5_HOLDOUT_SEED_STRUCTURAL_VALIDATION|CANDIDATE_HARD_GATES|SCIENTIFIC_EXIT_CODE)=' \
      "$report" || true
  fi
done

emit_merged_markers
if [[ -f "$MERGED_ROOT/PHASE1_MERGED_AUDIT.json" ]]; then
  echo 'NEXT_GATE=FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION'
else
  echo 'NEXT_GATE=REVIEW_ONLY_FAILED_PASS_WITHOUT_NEW_SEEDS_OR_ALGORITHM_TUNING'
fi

FINAL_RC="${ASSEMBLY_EXIT%%:*}"
[[ "$FINAL_RC" =~ ^[0-9]+$ ]] || FINAL_RC=1
exit "$FINAL_RC"
