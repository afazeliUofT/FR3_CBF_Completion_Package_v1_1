#!/usr/bin/env bash
# Runs on the Nibi login node. It sets up/finalizes one excluded H100 smoke job.
set -Eeuo pipefail

: "${JOB_ZIP_NAME:?JOB_ZIP_NAME is required}"
: "${SMOKE_ZIP_NAME:?SMOKE_ZIP_NAME is required}"
: "${EXPECTED_JOB_SHA256:?EXPECTED_JOB_SHA256 is required}"
: "${EXPECTED_SMOKE_SHA256:?EXPECTED_SMOKE_SHA256 is required}"
: "${EXPECTED_PACKAGE_ID:?EXPECTED_PACKAGE_ID is required}"
: "${TRANSFER_ABS:?TRANSFER_ABS is required}"
: "${RETURN_ABS:?RETURN_ABS is required}"
: "${RUN_ROOT_ABS:?RUN_ROOT_ABS is required}"
: "${ENV_ROOT_ABS:?ENV_ROOT_ABS is required}"
: "${SMOKE_SOURCE_COMMIT:?SMOKE_SOURCE_COMMIT is required}"
: "${SMOKE_SEED:?SMOKE_SEED is required}"
: "${TOKEN_TTL_HOURS:?TOKEN_TTL_HOURS is required}"

HOST_FULL="$(hostname -f 2>/dev/null || hostname)"
[[ "$HOST_FULL" == *nibi* ]] || {
  echo "ERROR: remote host is not Nibi: $HOST_FULL"
  exit 20
}
[[ -n "${SCRATCH:-}" ]] || {
  echo "ERROR: SCRATCH is not defined on Nibi"
  exit 21
}

TRANSFER="$TRANSFER_ABS"
RETURN_HOME="$RETURN_ABS"
RUN_ROOT="$RUN_ROOT_ABS"
ENV_ROOT="$ENV_ROOT_ABS"
VENV="$ENV_ROOT/venv"
JOB_ROOT="$RUN_ROOT/job_package"
SMOKE_ROOT="$RUN_ROOT/smoke_package"
PROVENANCE="$RUN_ROOT/provenance"
LOGS="$RUN_ROOT/logs"
JOB_ZIP="$TRANSFER/$JOB_ZIP_NAME"
SMOKE_ZIP="$TRANSFER/$SMOKE_ZIP_NAME"
JOB_ID="not_submitted"
STATE="NOT_SUBMITTED"

mkdir -p "$TRANSFER" "$RETURN_HOME" "$ENV_ROOT"
rm -rf "$RUN_ROOT"
mkdir -p "$RUN_ROOT" "$PROVENANCE" "$LOGS"
rm -f "$RETURN_HOME"/*

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1

build_emergency_diagnostic() {
  local code="$1"
  local out="$RETURN_HOME/FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_DIAGNOSTIC_${JOB_ID}.zip"
  python3 - "$RUN_ROOT" "$out" "$code" "$JOB_ID" "$STATE" <<'PY' || true
from pathlib import Path
import sys
import zipfile

run = Path(sys.argv[1])
out = Path(sys.argv[2])
code, job_id, state = sys.argv[3:]
files = []
for root in [run / "logs", run / "provenance"]:
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files.append((path, path.relative_to(run).as_posix()))
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
    for path, relative in files:
        archive.write(path, relative)
    archive.writestr(
        "EMERGENCY_DIAGNOSTIC_STATUS.txt",
        f"exit_code={code}\njob_id={job_id}\nstate={state}\n",
    )
print(out)
PY
  if [[ -f "$out" ]]; then
    (
      cd "$RETURN_HOME"
      sha256sum "$(basename "$out")" > "$(basename "$out").sha256"
    )
  fi
}

remote_failure() {
  code=$?
  trap - ERR
  {
    echo "status=FAIL"
    echo "exit_code=$code"
    echo "command=${BASH_COMMAND:-unknown}"
    echo "job_id=$JOB_ID"
    echo "state=$STATE"
    echo "host=$HOST_FULL"
    echo "run_root=$RUN_ROOT"
    date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
  } > "$RETURN_HOME/REMOTE_FAILURE_STATUS.txt"
  build_emergency_diagnostic "$code"
  echo
  echo "================================================================="
  echo "REMOTE NONCAMPAIGN NIBI SMOKE ORCHESTRATION: FAIL"
  echo "Exit code: $code"
  echo "Job ID: $JOB_ID"
  echo "State: $STATE"
  echo "Return directory: $RETURN_HOME"
  echo "================================================================="
  exit "$code"
}
trap remote_failure ERR

echo "================================================================="
echo "REMOTE NONCAMPAIGN PHASE-1 NIBI DEPLOYMENT SMOKE"
echo "================================================================="
echo "Host: $HOST_FULL"
echo "Scratch: $SCRATCH"
echo "Smoke seed: $SMOKE_SEED"
echo "Confirmatory analysis included: NO"
echo "Full campaign authorized: NO"
echo "Run root: $RUN_ROOT"

for path in "$JOB_ZIP" "$SMOKE_ZIP"; do
  [[ -f "$path" ]] || {
    echo "ERROR: transferred file missing: $path"
    exit 22
  }
done
ACTUAL_JOB_SHA="$(sha256sum "$JOB_ZIP" | awk '{print $1}')"
ACTUAL_SMOKE_SHA="$(sha256sum "$SMOKE_ZIP" | awk '{print $1}')"
echo "Expected job ZIP SHA-256:   $EXPECTED_JOB_SHA256"
echo "Actual job ZIP SHA-256:     $ACTUAL_JOB_SHA"
echo "Expected smoke ZIP SHA-256: $EXPECTED_SMOKE_SHA256"
echo "Actual smoke ZIP SHA-256:   $ACTUAL_SMOKE_SHA"
[[ "$ACTUAL_JOB_SHA" == "$EXPECTED_JOB_SHA256" ]]
[[ "$ACTUAL_SMOKE_SHA" == "$EXPECTED_SMOKE_SHA256" ]]
unzip -t "$JOB_ZIP"
unzip -t "$SMOKE_ZIP"

mkdir -p "$JOB_ROOT" "$SMOKE_ROOT"
unzip -q "$JOB_ZIP" -d "$JOB_ROOT"
unzip -q "$SMOKE_ZIP" -d "$SMOKE_ROOT"

(
  cd "$JOB_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256
  [[ "$(cat PACKAGE_ID.txt)" == "$EXPECTED_PACKAGE_ID" ]]
)
(
  cd "$SMOKE_ROOT"
  sha256sum -c SMOKE_SOURCE_MANIFEST.sha256
)
echo "REMOTE PACKAGE EXTRACTION/MANIFESTS: PASS"

python3 - "$JOB_ROOT/JOB_PACKAGE_CONTRACT.json" \
  "$SMOKE_ROOT/SMOKE_PACKAGE_CONTRACT.json" \
  "$SMOKE_SEED" <<'PY'
from pathlib import Path
import json
import sys

job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
smoke = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
seed = int(sys.argv[3])
assert job["execution_authorized"] is False
assert job["submission_scripts_locked"] is True
assert smoke["execution_scope"] == "NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY"
assert smoke["full_campaign_execution_authorized"] is False
assert smoke["merge_authorized"] is False
assert seed == smoke["smoke_seed"]
assert seed not in job["campaign_seed_list"]
assert job["package_id"] == smoke["job_package_id"]
assert job["candidate_v3"]["zip_sha256"] == smoke["candidate_v3_sha256"]
print("REMOTE SMOKE CONTRACT BINDING: PASS")
PY

# Build or reuse the exact scratch environment.
export PHASE1_BASE="$ENV_ROOT"
export PHASE1_VENV="$VENV"
set +e
set -o pipefail
bash "$JOB_ROOT/setup_environment.sh" \
  2>&1 | tee "$PROVENANCE/environment_setup.log"
SETUP_EXIT=${PIPESTATUS[0]}
set +o pipefail
set -e
[[ "$SETUP_EXIT" -eq 0 ]] || {
  echo "ERROR: Nibi smoke environment setup failed"
  exit 23
}

module --force purge
module load StdEnv/2023
module load python/3.12.4
module -t list 2> "$PROVENANCE/module_list.txt" || true
source "$VENV/bin/activate"

python "$SMOKE_ROOT/freeze_environment.py" \
  --output "$PROVENANCE/ENVIRONMENT_LOCK.json" \
  --pip-freeze "$PROVENANCE/pip_freeze.txt" \
  --module-list "$PROVENANCE/module_list.txt" \
  --setup-log "$PROVENANCE/environment_setup.log" \
  --job-package-zip "$JOB_ZIP" \
  --smoke-package-zip "$SMOKE_ZIP" \
  --job-package-id "$EXPECTED_PACKAGE_ID" \
  --job-package-sha256 "$EXPECTED_JOB_SHA256" \
  --smoke-package-sha256 "$EXPECTED_SMOKE_SHA256" \
  --source-commit "$SMOKE_SOURCE_COMMIT" \
  --smoke-seed "$SMOKE_SEED"

python "$SMOKE_ROOT/make_smoke_token.py" \
  --contract "$SMOKE_ROOT/SMOKE_PACKAGE_CONTRACT.json" \
  --environment-lock "$PROVENANCE/ENVIRONMENT_LOCK.json" \
  --output "$PROVENANCE/SMOKE_AUTHORIZATION_TOKEN.json" \
  --source-commit "$SMOKE_SOURCE_COMMIT" \
  --smoke-package-sha256 "$EXPECTED_SMOKE_SHA256" \
  --ttl-hours "$TOKEN_TTL_HOURS"

python "$SMOKE_ROOT/validate_smoke_token.py" \
  --token "$PROVENANCE/SMOKE_AUTHORIZATION_TOKEN.json" \
  --environment-lock "$PROVENANCE/ENVIRONMENT_LOCK.json" \
  --contract "$SMOKE_ROOT/SMOKE_PACKAGE_CONTRACT.json" \
  --source-commit "$SMOKE_SOURCE_COMMIT" \
  --smoke-package-sha256 "$EXPECTED_SMOKE_SHA256"

cp -p \
  "$SMOKE_ROOT/SMOKE_PACKAGE_CONTRACT.json" \
  "$SMOKE_ROOT/SMOKE_SOURCE_MANIFEST.sha256" \
  "$SMOKE_ROOT/SMOKE_INDEPENDENT_REVIEW.json" \
  "$PROVENANCE/"

mapfile -t ASSOCIATIONS < <(
  sacctmgr -nP show assoc \
    user="$USER" \
    cluster=nibi \
    format=Account 2>/dev/null \
  | cut -d'|' -f1 \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | sed '/^$/d' \
  | sort -u
)
echo "Nibi account associations:"
printf '  %s\n' "${ASSOCIATIONS[@]:-<none>}"

ACCOUNT=""
if [[ -n "${FR3_ACCOUNT_OVERRIDE:-}" ]]; then
  ACCOUNT="$FR3_ACCOUNT_OVERRIDE"
else
  for preferred in def-rsadve_gpu def-rsadve def-rsadve_cpu; do
    for value in "${ASSOCIATIONS[@]}"; do
      if [[ "$value" == "$preferred" ]]; then
        ACCOUNT="$value"
        break 2
      fi
    done
  done
  if [[ -z "$ACCOUNT" && "${#ASSOCIATIONS[@]}" -gt 0 ]]; then
    ACCOUNT="${ASSOCIATIONS[0]}"
  fi
fi
[[ -n "$ACCOUNT" ]] || {
  echo "ERROR: no Nibi Slurm account could be selected"
  exit 24
}
echo "Selected Nibi Slurm account: $ACCOUNT"

TOKEN="$PROVENANCE/SMOKE_AUTHORIZATION_TOKEN.json"
ENV_LOCK="$PROVENANCE/ENVIRONMENT_LOCK.json"
JOB_ID="$(
  sbatch \
    --parsable \
    --account="$ACCOUNT" \
    --nodes=1 \
    --ntasks=1 \
    --gpus-per-node=h100:1 \
    --cpus-per-task=16 \
    --mem=124G \
    --time=04:00:00 \
    --job-name=fr3-p1-deploy-smoke \
    --output="$LOGS/smoke-%j.out" \
    --error="$LOGS/smoke-%j.err" \
    --export=ALL,PHASE1_JOB_PACKAGE_ROOT="$JOB_ROOT",PHASE1_SMOKE_PACKAGE_ROOT="$SMOKE_ROOT",PHASE1_SMOKE_RUN_ROOT="$RUN_ROOT",PHASE1_VENV="$VENV",PHASE1_SMOKE_AUTHORIZATION_FILE="$TOKEN",PHASE1_ENVIRONMENT_LOCK="$ENV_LOCK",PHASE1_SMOKE_SOURCE_COMMIT="$SMOKE_SOURCE_COMMIT",PHASE1_SMOKE_SEED="$SMOKE_SEED",PHASE1_SMOKE_PACKAGE_SHA256="$EXPECTED_SMOKE_SHA256" \
    "$SMOKE_ROOT/smoke_h100_worker.sh"
)"
printf '%s\n' "$JOB_ID" > "$PROVENANCE/job_id.txt"
printf '%s\n' "$ACCOUNT" > "$PROVENANCE/slurm_account.txt"
echo "Submitted one excluded Nibi H100 smoke job: $JOB_ID"
echo "Slurm array used: NO"

while squeue -h -j "$JOB_ID" 2>/dev/null | grep -q .; do
  squeue -j "$JOB_ID" -o '%.18i %.10T %.10M %.35R'
  sleep 30
done

for attempt in $(seq 1 30); do
  sacct -j "$JOB_ID" \
    --format=JobID,JobName%28,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES,NodeList \
    -P > "$LOGS/sacct-${JOB_ID}.txt" || true
  STATE="$(
    sacct -n -X -j "$JOB_ID" --format=State -P 2>/dev/null \
      | head -n1 | cut -d'|' -f1 | xargs
  )"
  [[ -n "$STATE" ]] && break
  sleep 10
done
cat "$LOGS/sacct-${JOB_ID}.txt" || true
echo "Final smoke job state: $STATE"

RETURN_NAME="FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_RETURN_${JOB_ID}.zip"
RETURN="$RUN_ROOT/$RETURN_NAME"
python "$SMOKE_ROOT/build_smoke_return.py" \
  --run-root "$RUN_ROOT" \
  --job-package-root "$JOB_ROOT" \
  --smoke-package-root "$SMOKE_ROOT" \
  --job-id "$JOB_ID" \
  --state "$STATE" \
  --smoke-seed "$SMOKE_SEED" \
  --output "$RETURN"

(
  cd "$RUN_ROOT"
  sha256sum -c "$RETURN_NAME.sha256"
  unzip -t "$RETURN_NAME"
)
cp -p "$RETURN" "$RETURN.sha256" "$RETURN_HOME/"

if [[ "$STATE" == COMPLETED* ]]; then
  {
    echo "status=PASS"
    echo "job_id=$JOB_ID"
    echo "state=$STATE"
    echo "smoke_seed=$SMOKE_SEED"
    echo "analysis_scope=EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
    echo "return_zip=$RETURN_HOME/$RETURN_NAME"
    echo "return_sha=$RETURN_HOME/$RETURN_NAME.sha256"
    echo "full_campaign_execution_authorized=NO"
    date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
  } > "$RETURN_HOME/REMOTE_SUCCESS_STATUS.txt"
  echo "REMOTE NONCAMPAIGN NIBI SMOKE ORCHESTRATION: PASS"
  echo "Job ID: $JOB_ID"
  echo "Return ZIP: $RETURN_HOME/$RETURN_NAME"
  exit 0
fi

{
  echo "status=FAIL"
  echo "job_id=$JOB_ID"
  echo "state=$STATE"
  echo "return_zip=$RETURN_HOME/$RETURN_NAME"
  echo "return_sha=$RETURN_HOME/$RETURN_NAME.sha256"
  date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
} > "$RETURN_HOME/REMOTE_FAILURE_STATUS.txt"
echo "ERROR: noncampaign Nibi smoke job did not complete"
tail -n 260 "$LOGS/smoke-${JOB_ID}.out" || true
tail -n 260 "$LOGS/smoke-${JOB_ID}.err" || true
exit 25
