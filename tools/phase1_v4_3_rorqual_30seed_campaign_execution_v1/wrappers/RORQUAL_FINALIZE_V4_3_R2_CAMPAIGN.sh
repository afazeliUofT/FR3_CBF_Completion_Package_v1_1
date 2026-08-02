#!/usr/bin/env bash
set -Eeuo pipefail

: "${FR3_RUN_ROOT:?FR3_RUN_ROOT is required}"
: "${FR3_JOB_PACKAGE_ROOT:?FR3_JOB_PACKAGE_ROOT is required}"
: "${FR3_EXECUTION_PACKAGE_ROOT:?FR3_EXECUTION_PACKAGE_ROOT is required}"
: "${FR3_AUTHORIZATION_CONTRACT:?FR3_AUTHORIZATION_CONTRACT is required}"
: "${FR3_AUTHORIZATION_TOKEN:?FR3_AUTHORIZATION_TOKEN is required}"
: "${FR3_AUTHORIZATION_PACKAGE_SHA256:?FR3_AUTHORIZATION_PACKAGE_SHA256 is required}"
: "${FR3_ARRAY_JOB_ID:?FR3_ARRAY_JOB_ID is required}"
: "${FR3_MERGE_JOB_ID:?FR3_MERGE_JOB_ID is required}"
: "${FR3_PHASE1_VENV:?FR3_PHASE1_VENV is required}"

RUN="$FR3_RUN_ROOT"
JOB="$FR3_JOB_PACKAGE_ROOT"
EXEC="$FR3_EXECUTION_PACKAGE_ROOT"
STATUS="$RUN/status"
RETURN="$RUN/return"
TOKEN="$FR3_AUTHORIZATION_TOKEN"
mkdir -p "$STATUS" "$RETURN" "$RUN/logs" "$RUN/slurm"

module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$FR3_PHASE1_VENV/bin/activate"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1

for SACCT_ATTEMPT in $(seq 1 12); do
  sacct -j "${FR3_ARRAY_JOB_ID},${FR3_MERGE_JOB_ID}" \
    --format=JobIDRaw,JobName%32,Account,State,ExitCode,Elapsed,MaxRSS,MaxVMSize,ReqMem,AllocTRES%120,NodeList%40 \
    -P > "$RUN/slurm/sacct_campaign.txt" || true
  ARRAY_TASK_RECORD_COUNT="$($FR3_PHASE1_VENV/bin/python - "$RUN/slurm/sacct_campaign.txt" "$FR3_ARRAY_JOB_ID" <<'PY_COUNT'
from pathlib import Path
import csv,re,sys
path=Path(sys.argv[1]); array_id=sys.argv[2]; count=0
if path.is_file():
    with path.open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f,delimiter='|'):
            if re.fullmatch(re.escape(array_id)+r'_\d+',row.get('JobIDRaw','')): count+=1
print(count)
PY_COUNT
)"
  if [[ "$ARRAY_TASK_RECORD_COUNT" -ge 30 ]]; then
    break
  fi
  sleep 10
done
echo "SACCT_ARRAY_TASK_RECORD_COUNT=$ARRAY_TASK_RECORD_COUNT"

python - "$RUN/slurm/sacct_campaign.txt" "$FR3_ARRAY_JOB_ID" "$STATUS/ARRAY_SUMMARY.json" "$STATUS/ARRAY_SUMMARY_EXIT_CODE.txt" <<'PY'
from pathlib import Path
import csv, json, re, sys
source=Path(sys.argv[1]); array_id=sys.argv[2]; out=Path(sys.argv[3]); rc_path=Path(sys.argv[4])
rows=[]
with source.open(newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f, delimiter='|'):
        if re.fullmatch(re.escape(array_id)+r'_\d+', row.get('JobIDRaw','')):
            rows.append(row)
states={}
for row in rows:
    state=row.get('State','').split()[0]
    states[state]=states.get(state,0)+1
all_ok=len(rows)==30 and all(row.get('State','').startswith('COMPLETED') and row.get('ExitCode')=='0:0' for row in rows)
value={'array_job_id':array_id,'task_record_count':len(rows),'state_counts':states,'all_30_tasks_completed_zero':all_ok,'task_rows':rows}
out.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
rc_path.write_text(('0' if all_ok else '42')+'\n')
print('ARRAY_TASK_RECORD_COUNT='+str(len(rows)))
print('ARRAY_ALL_30_TASKS_COMPLETED_ZERO='+('YES' if all_ok else 'NO'))
print('ARRAY_STATE_COUNTS='+json.dumps(states,sort_keys=True,separators=(',',':')))
PY

python - "$RUN/slurm/sacct_campaign.txt" "$FR3_MERGE_JOB_ID" "$STATUS/MERGE_WORKER_EXIT_CODE.txt" <<'PY'
from pathlib import Path
import csv, sys
source=Path(sys.argv[1]); merge_id=sys.argv[2]; out=Path(sys.argv[3]); rc=99; state='NOT_FOUND'; exit_code='99:0'
with source.open(newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f, delimiter='|'):
        if row.get('JobIDRaw')==merge_id:
            state=row.get('State',''); exit_code=row.get('ExitCode','99:0')
            try: rc=int(exit_code.split(':',1)[0])
            except Exception: rc=99
            break
out.write_text(str(rc)+'\n')
print('MERGE_JOB_STATE='+state)
print('MERGE_JOB_EXIT_CODE='+exit_code)
print('MERGE_WORKER_EXIT_CODE='+str(rc))
PY

MERGED_VALIDATOR_RC=99
if [[ -f "$RUN/merged/PHASE1_MERGED_AUDIT.json" ]]; then
  if "$FR3_PHASE1_VENV/bin/python" "$JOB/validate_merged_results.py" \
      --merged-dir "$RUN/merged" \
      > "$RUN/logs/merged_validator_stdout.log" \
      2> "$RUN/logs/merged_validator_stderr.log"; then
    MERGED_VALIDATOR_RC=0
  else
    MERGED_VALIDATOR_RC=$?
  fi
fi
printf '%s\n' "$MERGED_VALIDATOR_RC" > "$STATUS/MERGED_VALIDATOR_EXIT_CODE.txt"
echo "MERGED_VALIDATOR_EXIT_CODE=$MERGED_VALIDATOR_RC"

TOKEN_META="$STATUS/AUTHORIZATION_TOKEN_METADATA.json"
python - "$TOKEN" "$TOKEN_META" <<'PY'
from pathlib import Path
import hashlib, json, sys
source=Path(sys.argv[1]); target=Path(sys.argv[2]); raw=source.read_bytes(); token=json.loads(raw)
public={key:value for key,value in token.items() if key not in {'authorization'}}
value={'schema_version':1,'authorization_token_sha256':hashlib.sha256(raw).hexdigest(),'token_public_fields':public,'authorization_token_included':False}
target.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
PY
rm -f -- "$TOKEN"
if [[ -e "$TOKEN" ]]; then
  echo "AUTHORIZATION_TOKEN_DELETED_AFTER_CAMPAIGN=FAIL"
else
  echo "AUTHORIZATION_TOKEN_DELETED_AFTER_CAMPAIGN=PASS"
  printf '%s\n' PASS > "$STATUS/AUTHORIZATION_TOKEN_DELETED.txt"
fi

PIP_FREEZE="$(dirname "$FR3_PHASE1_VENV")/pip_freeze.txt"
if [[ ! -f "$PIP_FREEZE" ]]; then
  PIP_FREEZE=""
fi

PACKAGER_ARGS=(
  "$FR3_PHASE1_VENV/bin/python"
  "$EXEC/scripts/package_campaign_return.py"
  --run-root "$RUN"
  --job-package-root "$JOB"
  --authorization-contract "$FR3_AUTHORIZATION_CONTRACT"
  --authorization-token-metadata "$TOKEN_META"
  --authorization-package-sha256 "$FR3_AUTHORIZATION_PACKAGE_SHA256"
  --array-job-id "$FR3_ARRAY_JOB_ID"
  --merge-job-id "$FR3_MERGE_JOB_ID"
  --finalizer-job-id "${SLURM_JOB_ID:-UNKNOWN}"
  --output-dir "$RETURN"
)
if [[ -n "$PIP_FREEZE" ]]; then
  PACKAGER_ARGS+=(--pip-freeze "$PIP_FREEZE")
fi

if "${PACKAGER_ARGS[@]}" \
    > "$RUN/logs/campaign_return_packager_stdout.log" \
    2> "$RUN/logs/campaign_return_packager_stderr.log"; then
  PACKAGER_RC=0
else
  PACKAGER_RC=$?
fi
cat "$RUN/logs/campaign_return_packager_stdout.log" || true
cat "$RUN/logs/campaign_return_packager_stderr.log" >&2 || true
printf '%s\n' "$PACKAGER_RC" > "$STATUS/FINALIZER_PACKAGER_EXIT_CODE.txt"
echo "FINALIZER_PACKAGER_EXIT_CODE=$PACKAGER_RC"
exit "$PACKAGER_RC"
