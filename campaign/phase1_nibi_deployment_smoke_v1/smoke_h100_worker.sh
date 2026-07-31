#!/usr/bin/env bash
set -Eeuo pipefail

: "${PHASE1_JOB_PACKAGE_ROOT:?PHASE1_JOB_PACKAGE_ROOT is required}"
: "${PHASE1_SMOKE_PACKAGE_ROOT:?PHASE1_SMOKE_PACKAGE_ROOT is required}"
: "${PHASE1_SMOKE_RUN_ROOT:?PHASE1_SMOKE_RUN_ROOT is required}"
: "${PHASE1_VENV:?PHASE1_VENV is required}"
: "${PHASE1_SMOKE_AUTHORIZATION_FILE:?PHASE1_SMOKE_AUTHORIZATION_FILE is required}"
: "${PHASE1_ENVIRONMENT_LOCK:?PHASE1_ENVIRONMENT_LOCK is required}"
: "${PHASE1_SMOKE_SOURCE_COMMIT:?PHASE1_SMOKE_SOURCE_COMMIT is required}"
: "${PHASE1_SMOKE_SEED:?PHASE1_SMOKE_SEED is required}"
: "${PHASE1_SMOKE_PACKAGE_SHA256:?PHASE1_SMOKE_PACKAGE_SHA256 is required}"

JOB_ROOT="$PHASE1_JOB_PACKAGE_ROOT"
SMOKE_ROOT="$PHASE1_SMOKE_PACKAGE_ROOT"
RUN_ROOT="$PHASE1_SMOKE_RUN_ROOT"
VENV="$PHASE1_VENV"
TOKEN="$PHASE1_SMOKE_AUTHORIZATION_FILE"
ENV_LOCK="$PHASE1_ENVIRONMENT_LOCK"
SEED="$PHASE1_SMOKE_SEED"

mkdir -p \
  "$RUN_ROOT/results" \
  "$RUN_ROOT/logs" \
  "$RUN_ROOT/provenance" \
  "$RUN_ROOT/cache/cuda" \
  "$RUN_ROOT/cache/xdg" \
  "$RUN_ROOT/cache/tmp" \
  "$RUN_ROOT/cache/torch" \
  "$RUN_ROOT/cache/torch_extensions" \
  "$RUN_ROOT/cache/matplotlib"

export CUDA_CACHE_PATH="$RUN_ROOT/cache/cuda"
export XDG_CACHE_HOME="$RUN_ROOT/cache/xdg"
export TMPDIR="$RUN_ROOT/cache/tmp"
export TORCH_HOME="$RUN_ROOT/cache/torch"
export TORCH_EXTENSIONS_DIR="$RUN_ROOT/cache/torch_extensions"
export MPLCONFIGDIR="$RUN_ROOT/cache/matplotlib"
export PYTHONPYCACHEPREFIX="$RUN_ROOT/cache/pycache"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export NUMEXPR_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"

module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"

failure() {
  code=$?
  trap - ERR
  {
    echo "status=FAIL"
    echo "exit_code=$code"
    echo "command=${BASH_COMMAND:-unknown}"
    echo "job_id=${SLURM_JOB_ID:-unknown}"
    echo "host=$(hostname -f 2>/dev/null || hostname)"
    date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
  } > "$RUN_ROOT/provenance/SMOKE_JOB_FAILURE.txt"
  exit "$code"
}
trap failure ERR

python "$SMOKE_ROOT/validate_smoke_token.py" \
  --token "$TOKEN" \
  --environment-lock "$ENV_LOCK" \
  --contract "$SMOKE_ROOT/SMOKE_PACKAGE_CONTRACT.json" \
  --source-commit "$PHASE1_SMOKE_SOURCE_COMMIT" \
  --smoke-package-sha256 "$PHASE1_SMOKE_PACKAGE_SHA256"

python "$SMOKE_ROOT/capture_gpu_runtime.py" \
  --output "$RUN_ROOT/provenance/GPU_RUNTIME.json" \
  --environment-lock "$ENV_LOCK" \
  --token "$TOKEN"

python "$SMOKE_ROOT/run_noncampaign_smoke.py" \
  --job-package-root "$JOB_ROOT" \
  --smoke-contract "$SMOKE_ROOT/SMOKE_PACKAGE_CONTRACT.json" \
  --token "$TOKEN" \
  --environment-lock "$ENV_LOCK" \
  --source-commit "$PHASE1_SMOKE_SOURCE_COMMIT" \
  --smoke-package-sha256 "$PHASE1_SMOKE_PACKAGE_SHA256" \
  --output-root "$RUN_ROOT/results" \
  --smoke-seed "$SEED"

RESULT_DIR="$RUN_ROOT/results/noncampaign_smoke_seed_${SEED}/result"
python "$SMOKE_ROOT/validate_noncampaign_smoke.py" \
  --result-dir "$RESULT_DIR" \
  --smoke-contract "$SMOKE_ROOT/SMOKE_PACKAGE_CONTRACT.json" \
  --environment-lock "$ENV_LOCK" \
  --token "$TOKEN"

{
  echo "status=PASS"
  echo "job_id=${SLURM_JOB_ID:-unknown}"
  echo "smoke_seed=$SEED"
  echo "analysis_scope=EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
  echo "full_campaign_execution_authorized=NO"
  echo "merge_authorized=NO"
  date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
} > "$RUN_ROOT/provenance/SMOKE_JOB_SUCCESS.txt"

echo "PHASE-1 NONCAMPAIGN NIBI DEPLOYMENT SMOKE WORKER: PASS"
