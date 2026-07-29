#!/usr/bin/env bash
set -Eeuo pipefail

: "${FR3_PACKAGE_ROOT:?FR3_PACKAGE_ROOT is required}"
: "${FR3_EXPORT_BASE:?FR3_EXPORT_BASE is required}"
: "${FR3_EXPORT_VENV:?FR3_EXPORT_VENV is required}"

ROOT="$FR3_PACKAGE_ROOT"
BASE="$FR3_EXPORT_BASE"
VENV="$FR3_EXPORT_VENV"

module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export CUDA_CACHE_PATH="$BASE/cache/cuda"
export XDG_CACHE_HOME="$BASE/cache/xdg"
export TMPDIR="$BASE/cache/tmp"
export TORCH_HOME="$BASE/cache/torch"
export TORCH_EXTENSIONS_DIR="$BASE/cache/torch_extensions"
export MPLCONFIGDIR="$BASE/cache/matplotlib"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"

mkdir -p "$ROOT/output" "$CUDA_CACHE_PATH" "$TMPDIR"

nvidia-smi
python - <<'PY'
import torch
assert torch.cuda.is_available()
name = torch.cuda.get_device_name(0)
memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
assert "H100" in name, name
assert memory >= 75.0, memory
print("FULL-TOPOLOGY H100 PROBE: PASS")
print("GPU:", name)
print("Memory GiB:", memory)
PY

python "$ROOT/run_full_topology_export.py"
python "$ROOT/validate_full_topology_export.py"
echo "FULL-TOPOLOGY EXPORT WORKER: PASS"
