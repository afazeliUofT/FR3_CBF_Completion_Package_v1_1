#!/usr/bin/env bash
set -Eeuo pipefail

: "${1:?remote authorization/execution package ZIP is required}"
: "${2:?expected package SHA-256 is required}"
PACKAGE_ARCHIVE="$(realpath "$1")"
EXPECTED_SHA256="$2"
SCRATCH_LINK="${3:-/home/rsadve1/links/scratch}"
SCRATCH="$(realpath "$SCRATCH_LINK")"
PACKAGE_NAME="FR3_CBF_v1_1_Candidate_v4_3_Rorqual_30Seed_Campaign_Authorization_Execution_DropIn_v1_2026-08-02"
PACKAGE_SHORT="8473d5504e69"
ACTIVE_LINK="$SCRATCH/FR3_PHASE1_RORQUAL_CAMPAIGN_V4_3_R2_${PACKAGE_SHORT}_ACTIVE"

module --force purge
module load StdEnv/2023
module load python/3.12.4

printf '%s\n' \
  "REMOTE_HOST=$(hostname -f)" \
  "REMOTE_SCRATCH=$SCRATCH" \
  "EXECUTION_CLUSTER=rorqual" \
  "EXECUTION_STAGE=FULL_30_SEED_CONFIRMATORY_CAMPAIGN" \
  "CAMPAIGN_SEEDS=44000-44029" \
  "SLURM_ARRAY=0-29%8" \
  "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=YES_EXACT_R2_PACKAGE_ONLY"

ACTUAL_SHA256="$(sha256sum "$PACKAGE_ARCHIVE" | awk '{print $1}')"
echo "EXPECTED_AUTHORIZATION_PACKAGE_SHA256=$EXPECTED_SHA256"
echo "ACTUAL_AUTHORIZATION_PACKAGE_SHA256=$ACTUAL_SHA256"
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]]
echo "REMOTE_AUTHORIZATION_PACKAGE_SHA256_GATE=PASS"

attach_or_create_run() {
  if [[ -L "$ACTIVE_LINK" || -d "$ACTIVE_LINK" ]]; then
    RUN_ROOT="$(realpath "$ACTIVE_LINK")"
    echo "EXISTING_CAMPAIGN_RUN_ATTACHED=YES"
    echo "CAMPAIGN_RUN_ROOT=$RUN_ROOT"
    return 0
  fi
  local stamp candidate
  stamp="$(date -u +%Y%m%d_%H%M%S)"
  candidate="$SCRATCH/FR3_PHASE1_RORQUAL_CAMPAIGN_V4_3_R2_${PACKAGE_SHORT}_${stamp}"
  mkdir -p "$candidate"
  if ln -s "$candidate" "$ACTIVE_LINK" 2>/dev/null; then
    RUN_ROOT="$candidate"
    echo "EXISTING_CAMPAIGN_RUN_ATTACHED=NO"
    echo "CAMPAIGN_RUN_ROOT=$RUN_ROOT"
  else
    rm -rf "$candidate"
    RUN_ROOT="$(realpath "$ACTIVE_LINK")"
    echo "EXISTING_CAMPAIGN_RUN_ATTACHED=YES_RACE_SAFE"
    echo "CAMPAIGN_RUN_ROOT=$RUN_ROOT"
  fi
}
attach_or_create_run
mkdir -p "$RUN_ROOT"/{input,source,job_package,private,slurm,logs,status,results,merged,return,cache}
STATE_FILE="$RUN_ROOT/status/CAMPAIGN_STATE.env"
RETURN_READY="$RUN_ROOT/return/RETURN_READY.env"

if [[ ! -f "$STATE_FILE" ]]; then
  cp -f "$PACKAGE_ARCHIVE" "$RUN_ROOT/input/$(basename "$PACKAGE_ARCHIVE")"
  unzip -t "$PACKAGE_ARCHIVE" >/dev/null
  rm -rf "$RUN_ROOT/source/$PACKAGE_NAME"
  unzip -q "$PACKAGE_ARCHIVE" -d "$RUN_ROOT/source"
  EXEC_ROOT="$RUN_ROOT/source/$PACKAGE_NAME"
  [[ -d "$EXEC_ROOT" ]]
  (
    cd "$EXEC_ROOT"
    sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
    sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
  )
  echo "REMOTE_EXECUTION_PACKAGE_MANIFEST_VERIFICATION=PASS"
  "$EXEC_ROOT/scripts/audit_authorization_prerequisites.py" --package-root "$EXEC_ROOT"

  JOB_ZIP="$EXEC_ROOT/immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip"
  JOB_SIDECAR="$JOB_ZIP.sha256"
  (
    cd "$(dirname "$JOB_ZIP")"
    sha256sum -c "$(basename "$JOB_SIDECAR")" >/dev/null
  )
  unzip -t "$JOB_ZIP" >/dev/null
  rm -rf "$RUN_ROOT/job_package"
  mkdir -p "$RUN_ROOT/job_package"
  unzip -q "$JOB_ZIP" -d "$RUN_ROOT/job_package"
  (
    cd "$RUN_ROOT/job_package"
    sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  )
  echo "REMOTE_RORQUAL_R2_JOB_PACKAGE_MANIFEST_VERIFICATION=PASS"

  ACTIVE_JOBS="$(squeue -u "$USER" -h -o '%i|%j|%T' | grep -E '\|(fr3-v43-r2-p1|fr3-v43-r2-merge|fr3-v43-r2-finalize)\|' || true)"
  if [[ -n "$ACTIVE_JOBS" ]]; then
    echo "RORQUAL_CONCURRENT_CAMPAIGN_GUARD=FAIL"
    printf '%s\n' "$ACTIVE_JOBS"
    exit 73
  fi
  echo "RORQUAL_CONCURRENT_CAMPAIGN_GUARD=PASS"

  ENV_BASE="$SCRATCH/FR3_PHASE1_RORQUAL_ENV_5037b4e33448"
  PHASE1_VENV="$ENV_BASE/.venv"
  PHASE1_BASE="$ENV_BASE" PHASE1_VENV="$PHASE1_VENV" \
    bash "$RUN_ROOT/job_package/setup_environment.sh" \
    > "$RUN_ROOT/logs/setup_environment.log" 2>&1
  cat "$RUN_ROOT/logs/setup_environment.log"
  "$PHASE1_VENV/bin/python" -m pip check
  echo "RORQUAL_EXACT_REFERENCE_ENVIRONMENT_GATE=PASS"

  AUTH_CONTRACT="$EXEC_ROOT/config/FULL_CAMPAIGN_AUTHORIZATION_CONTRACT.json"
  AUTH_TOKEN="$RUN_ROOT/private/FULL_30_SEED_AUTHORIZATION.json"
  "$PHASE1_VENV/bin/python" "$EXEC_ROOT/scripts/issue_full_campaign_authorization.py" \
    --job-package-root "$RUN_ROOT/job_package" \
    --authorization-contract "$AUTH_CONTRACT" \
    --output "$AUTH_TOKEN" \
    --expiry-days 14 \
    --authorization-package-sha256 "$EXPECTED_SHA256" \
    > "$RUN_ROOT/logs/authorization_issue.log"
  cat "$RUN_ROOT/logs/authorization_issue.log"

  ARRAY_SBATCH="$RUN_ROOT/slurm/phase1_array.sbatch"
  cat > "$ARRAY_SBATCH" <<EOF
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v43-r2-p1
#SBATCH --account=def-rsadve_gpu
#SBATCH --array=0-29%8
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=124G
#SBATCH --time=04:00:00
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

  MERGE_SBATCH="$RUN_ROOT/slurm/phase1_merge.sbatch"
  cat > "$MERGE_SBATCH" <<EOF
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v43-r2-merge
#SBATCH --account=def-rsadve_cpu
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=01:00:00
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

  FINALIZER_SBATCH="$RUN_ROOT/slurm/phase1_finalizer.sbatch"
  cat > "$FINALIZER_SBATCH" <<EOF
#!/usr/bin/env bash
#SBATCH --job-name=fr3-v43-r2-finalize
#SBATCH --account=def-rsadve_cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
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
bash '$EXEC_ROOT/wrappers/RORQUAL_FINALIZE_V4_3_R2_CAMPAIGN.sh'
EOF
  chmod +x "$FINALIZER_SBATCH"
  FINALIZER_JOB_ID="$(sbatch --parsable --dependency=afterany:${MERGE_JOB_ID} "$FINALIZER_SBATCH")"

  TEMP_STATE="$STATE_FILE.tmp.$$"
  cat > "$TEMP_STATE" <<EOF
CAMPAIGN_RUN_ROOT='$RUN_ROOT'
EXEC_ROOT='$EXEC_ROOT'
JOB_PACKAGE_ROOT='$RUN_ROOT/job_package'
PHASE1_VENV='$PHASE1_VENV'
AUTH_CONTRACT='$AUTH_CONTRACT'
AUTH_TOKEN='$AUTH_TOKEN'
AUTHORIZATION_PACKAGE_SHA256='$EXPECTED_SHA256'
ARRAY_JOB_ID='$ARRAY_JOB_ID'
MERGE_JOB_ID='$MERGE_JOB_ID'
FINALIZER_JOB_ID='$FINALIZER_JOB_ID'
CAMPAIGN_PACKAGE_ID='8473d5504e69347a69a536c43dcae35bec9519a90bc55de3a0712f9e0fb97889'
EOF
  mv "$TEMP_STATE" "$STATE_FILE"
  chmod 600 "$STATE_FILE"
  printf '%s\n' \
    "RORQUAL_30SEED_CAMPAIGN_SUBMISSION=PASS" \
    "ARRAY_JOB_ID=$ARRAY_JOB_ID" \
    "MERGE_JOB_ID=$MERGE_JOB_ID" \
    "FINALIZER_JOB_ID=$FINALIZER_JOB_ID" \
    "SLURM_ARRAY=0-29%8" \
    "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=YES_EXACT_PACKAGE_AND_SEEDS_ONLY"
else
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  echo "CAMPAIGN_STATE_REUSE=PASS"
  echo "ARRAY_JOB_ID=$ARRAY_JOB_ID"
  echo "MERGE_JOB_ID=$MERGE_JOB_ID"
  echo "FINALIZER_JOB_ID=$FINALIZER_JOB_ID"
fi

# shellcheck disable=SC1090
source "$STATE_FILE"
[[ "$AUTHORIZATION_PACKAGE_SHA256" == "$EXPECTED_SHA256" ]] || {
  echo "ACTIVE_RUN_AUTHORIZATION_PACKAGE_BINDING=FAIL"
  exit 74
}
echo "ACTIVE_RUN_AUTHORIZATION_PACKAGE_BINDING=PASS"

poll_count=0
while squeue -h -j "$FINALIZER_JOB_ID" 2>/dev/null | grep -q .; do
  if (( poll_count % 2 == 0 )); then
    echo "RORQUAL_CAMPAIGN_PROGRESS_BEGIN"
    squeue -j "${ARRAY_JOB_ID},${MERGE_JOB_ID},${FINALIZER_JOB_ID}" \
      -o '%.24i %.28j %.10T %.12M %.24R' || true
    echo "RORQUAL_CAMPAIGN_PROGRESS_END"
  fi
  poll_count=$((poll_count + 1))
  sleep 30
done

sacct -j "${ARRAY_JOB_ID},${MERGE_JOB_ID},${FINALIZER_JOB_ID}" \
  --format=JobIDRaw,JobName%32,Account,State,ExitCode,Elapsed,MaxRSS,MaxVMSize,ReqMem,AllocTRES%120,NodeList%40 \
  -P > "$RUN_ROOT/slurm/sacct_final.txt" || true
cat "$RUN_ROOT/slurm/sacct_final.txt" || true

if [[ ! -f "$RETURN_READY" ]]; then
  echo "FINALIZER_RETURN_READY_MISSING=YES"
  if FR3_RUN_ROOT="$RUN_ROOT" \
     FR3_JOB_PACKAGE_ROOT="$JOB_PACKAGE_ROOT" \
     FR3_EXECUTION_PACKAGE_ROOT="$EXEC_ROOT" \
     FR3_AUTHORIZATION_CONTRACT="$AUTH_CONTRACT" \
     FR3_AUTHORIZATION_TOKEN="$AUTH_TOKEN" \
     FR3_AUTHORIZATION_PACKAGE_SHA256="$AUTHORIZATION_PACKAGE_SHA256" \
     FR3_ARRAY_JOB_ID="$ARRAY_JOB_ID" \
     FR3_MERGE_JOB_ID="$MERGE_JOB_ID" \
     FR3_PHASE1_VENV="$PHASE1_VENV" \
     SLURM_JOB_ID="EMERGENCY_LOGIN_FINALIZER" \
     bash "$EXEC_ROOT/wrappers/RORQUAL_FINALIZE_V4_3_R2_CAMPAIGN.sh"; then
    EMERGENCY_FINALIZER_RC=0
  else
    EMERGENCY_FINALIZER_RC=$?
  fi
  echo "EMERGENCY_FINALIZER_EXIT_CODE=$EMERGENCY_FINALIZER_RC"
fi

[[ -f "$RETURN_READY" ]]
# shellcheck disable=SC1090
source "$RETURN_READY"
[[ -f "$CAMPAIGN_RETURN_ZIP" ]]
[[ -f "$CAMPAIGN_RETURN_ZIP.sha256" ]]
(
  cd "$(dirname "$CAMPAIGN_RETURN_ZIP")"
  sha256sum -c "$(basename "$CAMPAIGN_RETURN_ZIP.sha256")" >/dev/null
)
unzip -t "$CAMPAIGN_RETURN_ZIP" >/dev/null

echo "CAMPAIGN_RETURN_RETRIEVABLE=YES"
echo "CAMPAIGN_RETURN_ZIP=$CAMPAIGN_RETURN_ZIP"
echo "CAMPAIGN_RETURN_ZIP_SHA256=$CAMPAIGN_RETURN_ZIP_SHA256"
echo "CAMPAIGN_RETURN_STATUS=$CAMPAIGN_RETURN_STATUS"
echo "CAMPAIGN_SCIENTIFIC_EXIT_CODE=$CAMPAIGN_SCIENTIFIC_EXIT_CODE"
echo "AUTHORIZATION_TOKEN_PRESENT_AFTER_FINALIZER=$([[ -e "$AUTH_TOKEN" ]] && echo YES || echo NO)"
echo "NEXT_GATE=INDEPENDENT_SCIENTIFIC_REVIEW_AND_TWC_RESULTS_MANUSCRIPT_INTEGRATION"
exit "$CAMPAIGN_SCIENTIFIC_EXIT_CODE"
