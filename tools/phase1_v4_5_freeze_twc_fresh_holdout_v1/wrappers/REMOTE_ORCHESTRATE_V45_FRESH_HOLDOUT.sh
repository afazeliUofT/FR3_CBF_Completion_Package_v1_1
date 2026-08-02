#!/usr/bin/env bash
set -Eeuo pipefail
: "${1:?remote execution package ZIP is required}"
: "${2:?expected package SHA-256 is required}"
PACKAGE_ARCHIVE="$(realpath "$1")"
EXPECTED_SHA256="$2"
SCRATCH_LINK="${3:-/home/rsadve1/links/scratch}"
SCRATCH="$(realpath "$SCRATCH_LINK")"
PACKAGE_NAME="FR3_CBF_v1_1_Candidate_v4_5_Freeze_TWC_Draft_Fresh_Holdout_DropIn_v1_2026-08-02"
PACKAGE_SHORT="00a3561864f8"
ACTIVE_LINK="$SCRATCH/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_${PACKAGE_SHORT}_ACTIVE"
module --force purge
module load StdEnv/2023
module load python/3.12.4
printf '%s\n' \
 "REMOTE_HOST=$(hostname -f)" \
 "REMOTE_SCRATCH=$SCRATCH" \
 "EXECUTION_CLUSTER=rorqual" \
 "EXECUTION_STAGE=FRESH_V4_5_HOLDOUT_30_SEED" \
 "HOLDOUT_SEEDS=44030-44059" \
 "SLURM_ARRAY=0-29%8" \
 "WORKER_WALLTIME=00:10:00" \
 "WORKER_MEMORY=16G" \
 "MERGE_WALLTIME=00:05:00" \
 "MERGE_MEMORY=8G" \
 "AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO"
ACTUAL_SHA256="$(sha256sum "$PACKAGE_ARCHIVE" | awk '{print $1}')"
echo "EXPECTED_EXECUTION_PACKAGE_SHA256=$EXPECTED_SHA256"
echo "ACTUAL_EXECUTION_PACKAGE_SHA256=$ACTUAL_SHA256"
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]]
echo "REMOTE_EXECUTION_PACKAGE_SHA256_GATE=PASS"

attach_or_create_run() {
 if [[ -L "$ACTIVE_LINK" || -d "$ACTIVE_LINK" ]]; then
  RUN_ROOT="$(realpath "$ACTIVE_LINK")"; echo "EXISTING_HOLDOUT_RUN_ATTACHED=YES"; echo "HOLDOUT_RUN_ROOT=$RUN_ROOT"; return
 fi
 local stamp candidate
 stamp="$(date -u +%Y%m%d_%H%M%S)"
 candidate="$SCRATCH/FR3_PHASE1_RORQUAL_V45_FRESH_HOLDOUT_${PACKAGE_SHORT}_${stamp}"
 mkdir -p "$candidate"
 if ln -s "$candidate" "$ACTIVE_LINK" 2>/dev/null; then
  RUN_ROOT="$candidate"; echo "EXISTING_HOLDOUT_RUN_ATTACHED=NO"; echo "HOLDOUT_RUN_ROOT=$RUN_ROOT"
 else
  rm -rf "$candidate"; RUN_ROOT="$(realpath "$ACTIVE_LINK")"; echo "EXISTING_HOLDOUT_RUN_ATTACHED=YES_RACE_SAFE"; echo "HOLDOUT_RUN_ROOT=$RUN_ROOT"
 fi
}
attach_or_create_run
mkdir -p "$RUN_ROOT"/{input,source,job_package,private,slurm,logs,status,results,merged,return,cache}
STATE_FILE="$RUN_ROOT/status/HOLDOUT_STATE.env"
RETURN_READY="$RUN_ROOT/return/RETURN_READY.env"

if [[ ! -f "$STATE_FILE" ]]; then
 cp -f "$PACKAGE_ARCHIVE" "$RUN_ROOT/input/$(basename "$PACKAGE_ARCHIVE")"
 unzip -t "$PACKAGE_ARCHIVE" >/dev/null
 rm -rf "$RUN_ROOT/source/$PACKAGE_NAME"
 unzip -q "$PACKAGE_ARCHIVE" -d "$RUN_ROOT/source"
 EXEC_ROOT="$RUN_ROOT/source/$PACKAGE_NAME"
 [[ -d "$EXEC_ROOT" ]]
 (cd "$EXEC_ROOT" && sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null && sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null)
 echo "REMOTE_EXECUTION_PACKAGE_MANIFEST_VERIFICATION=PASS"
 "$EXEC_ROOT/scripts/audit_and_freeze_v45.py" --package-root "$EXEC_ROOT" --output-dir "$RUN_ROOT/logs/freeze_audit"

 JOB_ZIP="$EXEC_ROOT/immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip"
 (cd "$(dirname "$JOB_ZIP")" && sha256sum -c "$(basename "$JOB_ZIP.sha256")" >/dev/null)
 unzip -t "$JOB_ZIP" >/dev/null
 rm -rf "$RUN_ROOT/job_package"; mkdir -p "$RUN_ROOT/job_package"
 unzip -q "$JOB_ZIP" -d "$RUN_ROOT/job_package"
 (cd "$RUN_ROOT/job_package" && sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null)
 echo "REMOTE_HOLDOUT_JOB_PACKAGE_MANIFEST_VERIFICATION=PASS"

 ACTIVE_JOBS="$(squeue -u "$USER" -h -o '%i|%j|%T' | grep -E '\|(fr3-v45-holdout|fr3-v45-holdout-merge|fr3-v45-holdout-finalize)\|' || true)"
 if [[ -n "$ACTIVE_JOBS" ]]; then echo "RORQUAL_CONCURRENT_HOLDOUT_GUARD=FAIL"; printf '%s\n' "$ACTIVE_JOBS"; exit 73; fi
 echo "RORQUAL_CONCURRENT_HOLDOUT_GUARD=PASS"

 ENV_BASE="$SCRATCH/FR3_PHASE1_RORQUAL_ENV_5037b4e33448"
 PHASE1_VENV="$ENV_BASE/.venv"
 PHASE1_BASE="$ENV_BASE" PHASE1_VENV="$PHASE1_VENV" bash "$RUN_ROOT/job_package/setup_environment.sh" > "$RUN_ROOT/logs/setup_environment.log" 2>&1
 cat "$RUN_ROOT/logs/setup_environment.log"
 "$PHASE1_VENV/bin/python" -m pip check
 echo "RORQUAL_EXACT_REFERENCE_ENVIRONMENT_GATE=PASS"

 AUTH_CONTRACT="$EXEC_ROOT/config/FREEZE_HOLDOUT_CONTRACT.json"
 AUTH_TOKEN="$RUN_ROOT/private/FRESH_V45_HOLDOUT_AUTHORIZATION.json"
 "$PHASE1_VENV/bin/python" "$EXEC_ROOT/scripts/issue_fresh_holdout_authorization.py" \
  --job-package-root "$RUN_ROOT/job_package" --authorization-contract "$AUTH_CONTRACT" --output "$AUTH_TOKEN" \
  --expiry-days 7 --authorization-package-sha256 "$EXPECTED_SHA256" > "$RUN_ROOT/logs/authorization_issue.log"
 cat "$RUN_ROOT/logs/authorization_issue.log"

 ARRAY_SBATCH="$RUN_ROOT/slurm/v45_holdout_array.sbatch"
 cat > "$ARRAY_SBATCH" <<EOF
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-holdout
#SBATCH --account=def-rsadve_gpu
#SBATCH --array=0-29%8
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=16G
#SBATCH --time=00:10:00
#SBATCH --output=$RUN_ROOT/slurm/%x-%A_%a.out
#SBATCH --error=$RUN_ROOT/slurm/%x-%A_%a.err
set -Eeuo pipefail
export PHASE1_PACKAGE_ROOT='$RUN_ROOT/job_package'
export PHASE1_RUN_ROOT='$RUN_ROOT'
export PHASE1_VENV='$PHASE1_VENV'
export PHASE1_AUTHORIZATION_FILE='$AUTH_TOKEN'
export PHASE1_REUSE_CHANNEL=0
bash '$RUN_ROOT/job_package/phase1_array_worker.sh'
EOF
 chmod +x "$ARRAY_SBATCH"

 MERGE_SBATCH="$RUN_ROOT/slurm/v45_holdout_merge.sbatch"
 cat > "$MERGE_SBATCH" <<EOF
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-holdout-merge
#SBATCH --account=def-rsadve_cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:05:00
#SBATCH --output=$RUN_ROOT/slurm/%x-%j.out
#SBATCH --error=$RUN_ROOT/slurm/%x-%j.err
set -Eeuo pipefail
export PHASE1_PACKAGE_ROOT='$RUN_ROOT/job_package'
export PHASE1_RUN_ROOT='$RUN_ROOT'
export PHASE1_VENV='$PHASE1_VENV'
bash '$RUN_ROOT/job_package/phase1_merge_worker.sh'
EOF
 chmod +x "$MERGE_SBATCH"
 ARRAY_JOB_ID="$(sbatch --parsable "$ARRAY_SBATCH")"
 MERGE_JOB_ID="$(sbatch --parsable --dependency=afterany:${ARRAY_JOB_ID} "$MERGE_SBATCH")"

 FINALIZER_SBATCH="$RUN_ROOT/slurm/v45_holdout_finalizer.sbatch"
 cat > "$FINALIZER_SBATCH" <<EOF
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v45-holdout-finalize
#SBATCH --account=def-rsadve_cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:05:00
#SBATCH --output=$RUN_ROOT/slurm/%x-%j.out
#SBATCH --error=$RUN_ROOT/slurm/%x-%j.err
set -Eeuo pipefail
export FR3_RUN_ROOT='$RUN_ROOT'
export FR3_JOB_PACKAGE_ROOT='$RUN_ROOT/job_package'
export FR3_EXECUTION_PACKAGE_ROOT='$EXEC_ROOT'
export FR3_AUTHORIZATION_CONTRACT='$AUTH_CONTRACT'
export FR3_AUTHORIZATION_TOKEN='$AUTH_TOKEN'
export FR3_AUTHORIZATION_PACKAGE_SHA256='$EXPECTED_SHA256'
export FR3_ARRAY_JOB_ID='$ARRAY_JOB_ID'
export FR3_MERGE_JOB_ID='$MERGE_JOB_ID'
export FR3_PHASE1_VENV='$PHASE1_VENV'
bash '$EXEC_ROOT/wrappers/RORQUAL_FINALIZE_V45_FRESH_HOLDOUT.sh'
EOF
 chmod +x "$FINALIZER_SBATCH"
 FINALIZER_JOB_ID="$(sbatch --parsable --dependency=afterany:${MERGE_JOB_ID} "$FINALIZER_SBATCH")"
 cat > "$STATE_FILE.tmp" <<EOF
HOLDOUT_RUN_ROOT='$RUN_ROOT'
EXEC_ROOT='$EXEC_ROOT'
JOB_PACKAGE_ROOT='$RUN_ROOT/job_package'
PHASE1_VENV='$PHASE1_VENV'
AUTH_CONTRACT='$AUTH_CONTRACT'
AUTH_TOKEN='$AUTH_TOKEN'
AUTHORIZATION_PACKAGE_SHA256='$EXPECTED_SHA256'
ARRAY_JOB_ID='$ARRAY_JOB_ID'
MERGE_JOB_ID='$MERGE_JOB_ID'
FINALIZER_JOB_ID='$FINALIZER_JOB_ID'
HOLDOUT_PACKAGE_ID='00a3561864f8adb8ad22cf1bd866ec0234043c16acbb25634d1d3502defc2cc6'
EOF
 mv "$STATE_FILE.tmp" "$STATE_FILE"; chmod 600 "$STATE_FILE"
 printf '%s\n' "FRESH_V45_HOLDOUT_SUBMISSION=PASS" "ARRAY_JOB_ID=$ARRAY_JOB_ID" "MERGE_JOB_ID=$MERGE_JOB_ID" "FINALIZER_JOB_ID=$FINALIZER_JOB_ID" "SLURM_ARRAY=0-29%8"
else
 source "$STATE_FILE"
 echo "HOLDOUT_STATE_REUSE=PASS"; echo "ARRAY_JOB_ID=$ARRAY_JOB_ID"; echo "MERGE_JOB_ID=$MERGE_JOB_ID"; echo "FINALIZER_JOB_ID=$FINALIZER_JOB_ID"
fi
source "$STATE_FILE"

for attempt in $(seq 1 1440); do
 if [[ -f "$RETURN_READY" ]]; then break; fi
 echo "FRESH_HOLDOUT_PROGRESS_BEGIN"
 squeue -j "${ARRAY_JOB_ID},${MERGE_JOB_ID},${FINALIZER_JOB_ID}" -o '%.22i %.30j %.10T %.12M %R' || true
 echo "FRESH_HOLDOUT_PROGRESS_END"
 sleep 30
done
if [[ ! -f "$RETURN_READY" ]]; then
 echo "HOLDOUT_RETURN_READY_TIMEOUT=YES"; exit 75
fi
source "$RETURN_READY"
[[ -f "$HOLDOUT_RETURN_ZIP" && -f "$HOLDOUT_RETURN_ZIP.sha256" ]]
cat "$RUN_ROOT/slurm/sacct_holdout.txt" 2>/dev/null || true
printf '%s\n' \
 "HOLDOUT_RETURN_ZIP=$HOLDOUT_RETURN_ZIP" \
 "HOLDOUT_RETURN_ZIP_SHA256=$HOLDOUT_RETURN_ZIP_SHA256" \
 "HOLDOUT_RETURN_STATUS=$HOLDOUT_RETURN_STATUS" \
 "HOLDOUT_RETURN_PACKAGE_EXIT_CODE=$HOLDOUT_RETURN_PACKAGE_EXIT_CODE" \
 "AUTHORIZATION_TOKEN_PRESENT_AFTER_FINALIZER=$AUTHORIZATION_TOKEN_PRESENT_AFTER_FINALIZER" \
 "ARRAY_JOB_ID=$ARRAY_JOB_ID" "MERGE_JOB_ID=$MERGE_JOB_ID" "FINALIZER_JOB_ID=$FINALIZER_JOB_ID" \
 "AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO"
exit "$HOLDOUT_RETURN_PACKAGE_EXIT_CODE"
