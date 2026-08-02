#!/usr/bin/env bash
set -Eeuo pipefail
: "${FR3_RUN_ROOT:?}"
: "${FR3_JOB_PACKAGE_ROOT:?}"
: "${FR3_EXECUTION_PACKAGE_ROOT:?}"
: "${FR3_AUTHORIZATION_CONTRACT:?}"
: "${FR3_AUTHORIZATION_TOKEN:?}"
: "${FR3_AUTHORIZATION_PACKAGE_SHA256:?}"
: "${FR3_ARRAY_JOB_ID:?}"
: "${FR3_MERGE_JOB_ID:?}"
FR3_FINALIZER_JOB_ID="${FR3_FINALIZER_JOB_ID:-${SLURM_JOB_ID:-UNKNOWN}}"
: "${FR3_PHASE1_VENV:?}"
RUN="$FR3_RUN_ROOT"; JOB="$FR3_JOB_PACKAGE_ROOT"; EXEC="$FR3_EXECUTION_PACKAGE_ROOT"
TOKEN="$FR3_AUTHORIZATION_TOKEN"; STATUS="$RUN/status"; RETURN="$RUN/return"
mkdir -p "$STATUS" "$RETURN" "$RUN/logs" "$RUN/slurm"
module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$FR3_PHASE1_VENV/bin/activate"
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1

sacct -j "${FR3_ARRAY_JOB_ID},${FR3_MERGE_JOB_ID},${FR3_FINALIZER_JOB_ID}" \
  --format=JobIDRaw,JobName%34,Account,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES%100,NodeList%32 \
  -P > "$RUN/slurm/sacct_holdout.txt" || true

python - "$TOKEN" "$RUN/private/AUTHORIZATION_PUBLIC_METADATA.json" <<'PY'
from pathlib import Path
import hashlib,json,sys
src=Path(sys.argv[1]); out=Path(sys.argv[2])
h=hashlib.sha256(src.read_bytes()).hexdigest()
v=json.loads(src.read_text())
public={
 'authorization_token_sha256':h,
 'token_public_fields':{
  'authorization_package_sha256':v.get('authorization_package_sha256'),
  'execution_stage':v.get('execution_stage'),
  'package_id':v.get('package_id'),
  'allowed_seeds':v.get('allowed_seeds'),
  'authorization_expires_utc':v.get('authorization_expires_utc'),
  'automatic_extra_seed_or_algorithm_tuning_authorized':False,
 }
}
out.write_text(json.dumps(public,indent=2,sort_keys=True)+'\n')
PY

if python "$EXEC/scripts/package_fresh_holdout_return.py" \
  --run-root "$RUN" \
  --job-package-root "$JOB" \
  --authorization-contract "$FR3_AUTHORIZATION_CONTRACT" \
  --authorization-token-metadata "$RUN/private/AUTHORIZATION_PUBLIC_METADATA.json" \
  --authorization-package-sha256 "$FR3_AUTHORIZATION_PACKAGE_SHA256" \
  --array-job-id "$FR3_ARRAY_JOB_ID" \
  --merge-job-id "$FR3_MERGE_JOB_ID" \
  --finalizer-job-id "$FR3_FINALIZER_JOB_ID" \
  --output-dir "$RETURN" > "$RUN/logs/return_packaging.log" 2>&1; then
  PACKAGE_RC=0
else
  PACKAGE_RC=$?
fi
cat "$RUN/logs/return_packaging.log"
RETURN_ZIP="$(grep '^HOLDOUT_RETURN_ZIP=' "$RUN/logs/return_packaging.log" | tail -1 | cut -d= -f2-)"
RETURN_SHA="$(grep '^HOLDOUT_RETURN_ZIP_SHA256=' "$RUN/logs/return_packaging.log" | tail -1 | cut -d= -f2-)"
RETURN_STATUS="$(grep '^HOLDOUT_RETURN_STATUS=' "$RUN/logs/return_packaging.log" | tail -1 | cut -d= -f2-)"
[[ -f "$RETURN_ZIP" && -f "$RETURN_ZIP.sha256" ]]
rm -f "$TOKEN"
TOKEN_PRESENT=NO
[[ ! -e "$TOKEN" ]]
cat > "$RETURN/RETURN_READY.env.tmp" <<EOF
HOLDOUT_RETURN_ZIP='$RETURN_ZIP'
HOLDOUT_RETURN_ZIP_SHA256='$RETURN_SHA'
HOLDOUT_RETURN_STATUS='$RETURN_STATUS'
HOLDOUT_RETURN_PACKAGE_EXIT_CODE='$PACKAGE_RC'
AUTHORIZATION_TOKEN_PRESENT_AFTER_FINALIZER='$TOKEN_PRESENT'
EOF
mv "$RETURN/RETURN_READY.env.tmp" "$RETURN/RETURN_READY.env"
printf '%s\n' \
 "HOLDOUT_FINALIZER=COMPLETE" \
 "HOLDOUT_RETURN_ZIP=$RETURN_ZIP" \
 "HOLDOUT_RETURN_ZIP_SHA256=$RETURN_SHA" \
 "HOLDOUT_RETURN_STATUS=$RETURN_STATUS" \
 "HOLDOUT_RETURN_PACKAGE_EXIT_CODE=$PACKAGE_RC" \
 "AUTHORIZATION_TOKEN_PRESENT_AFTER_FINALIZER=$TOKEN_PRESENT" \
 "AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO"
exit 0
