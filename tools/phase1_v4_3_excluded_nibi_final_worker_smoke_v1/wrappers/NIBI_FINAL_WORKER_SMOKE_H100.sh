#!/usr/bin/env bash
set -Eeuo pipefail

: "${FR3_JOB_ROOT:?FR3_JOB_ROOT is required}"
: "${FR3_SMOKE_ROOT:?FR3_SMOKE_ROOT is required}"
: "${FR3_RUN_ROOT:?FR3_RUN_ROOT is required}"
: "${FR3_VENV:?FR3_VENV is required}"
: "${PHASE1_AUTHORIZATION_FILE:?PHASE1_AUTHORIZATION_FILE is required}"
: "${FR3_AUTHORIZATION_RECORD:?FR3_AUTHORIZATION_RECORD is required}"

JOB_ROOT="$FR3_JOB_ROOT"
SMOKE_ROOT="$FR3_SMOKE_ROOT"
RUN_ROOT="$FR3_RUN_ROOT"
VENV="$FR3_VENV"
SEED=43999
SEED_ROOT="$RUN_ROOT/results/seed_${SEED}"
PROVENANCE="$RUN_ROOT/provenance"
LOGS="$RUN_ROOT/logs"

mkdir -p \
  "$SEED_ROOT" "$PROVENANCE" "$LOGS" \
  "$RUN_ROOT/cache/cuda" "$RUN_ROOT/cache/xdg" "$RUN_ROOT/cache/tmp" \
  "$RUN_ROOT/cache/torch" "$RUN_ROOT/cache/torch_extensions" \
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

(
  cd "$JOB_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
)
(
  cd "$SMOKE_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo "NIBI_JOB_PACKAGE_MANIFEST_VERIFICATION=PASS"
echo "NIBI_SMOKE_PACKAGE_MANIFEST_VERIFICATION=PASS"

echo "CHANNEL_GENERATED_ON_NIBI=YES"
echo "PRESERVED_CHANNEL_REUSED=NO"
echo "SLURM_ARRAY_USED=NO"
echo "MERGE_JOB_SUBMITTED=NO"
echo "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO"

nvidia-smi > "$PROVENANCE/nvidia_smi.txt" 2>&1
python "$SMOKE_ROOT/scripts/capture_nibi_h100_environment.py" \
  --output "$PROVENANCE/NIBI_H100_ENVIRONMENT.json"

if "$VENV/bin/python" "$JOB_ROOT/phase1_seed_worker.py" \
    --seed "$SEED" \
    --output-root "$RUN_ROOT/results" \
    > "$SEED_ROOT/worker_stdout.log" \
    2> "$SEED_ROOT/worker_stderr.log"
then
  WORKER_RC=0
else
  WORKER_RC=$?
fi

STRUCTURAL_RC=99
PASS_VALIDATOR_RC=99
if [[ -d "$SEED_ROOT/result" ]]; then
  if "$VENV/bin/python" "$JOB_ROOT/validate_seed_result.py" \
      --result-dir "$SEED_ROOT/result" \
      --package-contract "$JOB_ROOT/JOB_PACKAGE_CONTRACT.json" \
      > "$PROVENANCE/structural_validator_stdout.log" \
      2> "$PROVENANCE/structural_validator_stderr.log"
  then
    STRUCTURAL_RC=0
  else
    STRUCTURAL_RC=$?
  fi

  if "$VENV/bin/python" "$JOB_ROOT/validate_seed_result.py" \
      --result-dir "$SEED_ROOT/result" \
      --package-contract "$JOB_ROOT/JOB_PACKAGE_CONTRACT.json" \
      --require-scientific-pass \
      > "$PROVENANCE/pass_validator_stdout.log" \
      2> "$PROVENANCE/pass_validator_stderr.log"
  then
    PASS_VALIDATOR_RC=0
  else
    PASS_VALIDATOR_RC=$?
  fi
fi

PACKAGE_SEED_RC=99
PACKAGE_ID="$(cat "$JOB_ROOT/PACKAGE_ID.txt")"
if "$VENV/bin/python" "$JOB_ROOT/package_seed_result.py" \
    --seed-root "$SEED_ROOT" \
    --seed "$SEED" \
    --package-id "$PACKAGE_ID" \
    --worker-exit-code "$WORKER_RC" \
    --validator-exit-code "$STRUCTURAL_RC" \
    > "$PROVENANCE/seed_return_packaging_stdout.log" \
    2> "$PROVENANCE/seed_return_packaging_stderr.log"
then
  PACKAGE_SEED_RC=0
else
  PACKAGE_SEED_RC=$?
fi

AUDIT_RC=99
if [[ -d "$SEED_ROOT/result" && -f "$SEED_ROOT/channel/CHANNEL_RECORD.json" ]]; then
  if "$VENV/bin/python" "$SMOKE_ROOT/scripts/audit_final_worker_smoke_result.py" \
      --seed-root "$SEED_ROOT" \
      --job-root "$JOB_ROOT" \
      --reference-root "$SMOKE_ROOT/immutable_bindings/reference_seed43999" \
      --authorization-record "$FR3_AUTHORIZATION_RECORD" \
      --environment "$PROVENANCE/NIBI_H100_ENVIRONMENT.json" \
      --output "$PROVENANCE/FINAL_WORKER_SMOKE_AUDIT.json" \
      > "$PROVENANCE/independent_audit_stdout.log" \
      2> "$PROVENANCE/independent_audit_stderr.log"
  then
    AUDIT_RC=0
  else
    AUDIT_RC=$?
  fi
fi

{
  echo "CAMPAIGN_SEED=$SEED"
  echo "FINAL_WORKER_EXIT_CODE=$WORKER_RC"
  echo "STRUCTURAL_VALIDATOR_EXIT_CODE=$STRUCTURAL_RC"
  echo "SCIENTIFIC_PASS_VALIDATOR_EXIT_CODE=$PASS_VALIDATOR_RC"
  echo "SEED_RETURN_PACKAGING_EXIT_CODE=$PACKAGE_SEED_RC"
  echo "INDEPENDENT_AUDIT_EXIT_CODE=$AUDIT_RC"
  echo "SLURM_JOB_ID=${SLURM_JOB_ID:-unknown}"
  echo "SLURM_ACCOUNT=${SLURM_JOB_ACCOUNT:-unknown}"
  echo "SLURM_NODE=${SLURMD_NODENAME:-unknown}"
  echo "CHANNEL_GENERATED_ON_NIBI=YES"
  echo "PRESERVED_CHANNEL_REUSED=NO"
  echo "SLURM_ARRAY_USED=NO"
  echo "MERGE_JOB_SUBMITTED=NO"
  echo "FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO"
} > "$PROVENANCE/JOB_EXIT_SUMMARY.env"

cat "$PROVENANCE/JOB_EXIT_SUMMARY.env"
[[ -f "$PROVENANCE/FINAL_WORKER_SMOKE_AUDIT.json" ]] && \
  cat "$PROVENANCE/independent_audit_stdout.log" || true

if [[ "$WORKER_RC" -eq 0 \
   && "$STRUCTURAL_RC" -eq 0 \
   && "$PASS_VALIDATOR_RC" -eq 0 \
   && "$PACKAGE_SEED_RC" -eq 0 \
   && "$AUDIT_RC" -eq 0 ]]
then
  echo "NIBI_FINAL_WORKER_SMOKE_JOB=PASS"
  exit 0
fi

if [[ "$WORKER_RC" -eq 42 || "$AUDIT_RC" -eq 42 ]]; then
  echo "NIBI_FINAL_WORKER_SMOKE_JOB=SCIENTIFIC_FAIL_RETURN_READY"
  exit 42
fi

echo "NIBI_FINAL_WORKER_SMOKE_JOB=INFRASTRUCTURE_OR_VALIDATION_FAIL_RETURN_READY"
for code in "$WORKER_RC" "$STRUCTURAL_RC" "$PASS_VALIDATOR_RC" "$PACKAGE_SEED_RC" "$AUDIT_RC"; do
  if [[ "$code" -ne 0 && "$code" -ne 99 ]]; then
    exit "$code"
  fi
done
exit 99
