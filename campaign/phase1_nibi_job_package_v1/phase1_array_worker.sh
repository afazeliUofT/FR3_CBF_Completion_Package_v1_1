#!/usr/bin/env bash
set -Eeuo pipefail

: "${PHASE1_PACKAGE_ROOT:?PHASE1_PACKAGE_ROOT is required}"
: "${PHASE1_RUN_ROOT:?PHASE1_RUN_ROOT is required}"
: "${PHASE1_VENV:?PHASE1_VENV is required}"
: "${PHASE1_AUTHORIZATION_FILE:?PHASE1_AUTHORIZATION_FILE is required}"
: "${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID is required}"

ROOT="$PHASE1_PACKAGE_ROOT"
RUN="$PHASE1_RUN_ROOT"
VENV="$PHASE1_VENV"

module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export CUDA_CACHE_PATH="$RUN/cache/cuda"
export XDG_CACHE_HOME="$RUN/cache/xdg"
export TMPDIR="$RUN/cache/tmp"
export TORCH_HOME="$RUN/cache/torch"
export TORCH_EXTENSIONS_DIR="$RUN/cache/torch_extensions"
export MPLCONFIGDIR="$RUN/cache/matplotlib"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"

mkdir -p \
  "$RUN/results" "$RUN/cache/cuda" "$RUN/cache/xdg" "$RUN/cache/tmp"

nvidia-smi
python - <<'PY'
import torch
assert torch.cuda.is_available()
name = torch.cuda.get_device_name(0)
memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
assert "H100" in name, name
assert memory >= 75.0, memory
print("PHASE-1 H100 PROBE: PASS")
print("GPU:", name)
print("Memory GiB:", memory)
PY

python "$ROOT/phase1_seed_worker.py" \
  --array-index "$SLURM_ARRAY_TASK_ID" \
  --output-root "$RUN/results"

SEED="$((44000 + SLURM_ARRAY_TASK_ID))"
python "$ROOT/validate_seed_result.py" \
  --result-dir "$RUN/results/seed_${SEED}/result" \
  --package-contract "$ROOT/JOB_PACKAGE_CONTRACT.json"

echo "PHASE-1 ARRAY WORKER: PASS"
