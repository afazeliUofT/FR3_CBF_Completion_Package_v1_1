#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${FR3_NIBI_BASE:-$SCRATCH/FR3_DLP_RZF_NIBI_PILOT_v1}"
VENV="$BASE/venv"

module --force purge
module load StdEnv/2023
module load python/3.12.4

source "$VENV/bin/activate"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export CUDA_CACHE_PATH="$BASE/cuda_cache"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
mkdir -p "$CUDA_CACHE_PATH" "$ROOT/output"

nvidia-smi
python - <<'PY'
import torch
assert torch.cuda.is_available()
print("GPU:", torch.cuda.get_device_name(0))
print("Capability:", torch.cuda.get_device_capability(0))
print("Memory GiB:", torch.cuda.get_device_properties(0).total_memory/1024**3)
PY

python "$ROOT/run_gpu_pilot.py"
python "$ROOT/validate_gpu_pilot.py"
echo "NIBI GPU PILOT WORKER: PASS"
