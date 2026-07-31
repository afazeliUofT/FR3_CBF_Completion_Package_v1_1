#!/usr/bin/env bash
set -Eeuo pipefail

: "${PHASE1_BASE:?PHASE1_BASE is required}"
: "${PHASE1_VENV:?PHASE1_VENV is required}"

BASE="$PHASE1_BASE"
VENV="$PHASE1_VENV"
CACHE="$BASE/cache"
WHEELS="$BASE/wheels"
mkdir -p \
  "$BASE" "$WHEELS" "$CACHE/pip" "$CACHE/xdg" "$CACHE/tmp" \
  "$CACHE/torch" "$CACHE/torch_extensions" "$CACHE/matplotlib" \
  "$CACHE/cuda" "$(dirname "$VENV")"

export PIP_CACHE_DIR="$CACHE/pip"
export XDG_CACHE_HOME="$CACHE/xdg"
export TMPDIR="$CACHE/tmp"
export TORCH_HOME="$CACHE/torch"
export TORCH_EXTENSIONS_DIR="$CACHE/torch_extensions"
export MPLCONFIGDIR="$CACHE/matplotlib"
export CUDA_CACHE_PATH="$CACHE/cuda"
export PYTHONPYCACHEPREFIX="$CACHE/pycache"

module --force purge
module load StdEnv/2023
module load python/3.12.4

environment_matches() {
  [[ -x "$VENV/bin/python" ]] || return 1
  "$VENV/bin/python" - <<'PY' >/dev/null 2>&1
import importlib.metadata
import torch
assert importlib.metadata.version("torch").split("+", 1)[0] == "2.9.1"
assert importlib.metadata.version("sionna-no-rt") == "2.0.1"
assert torch.version.cuda is not None
PY
}

if environment_matches; then
  echo "PHASE-1 EXISTING SCRATCH ENVIRONMENT REUSE: PASS"
  "$VENV/bin/python" -m pip check
  "$VENV/bin/python" -m pip freeze --all > "$BASE/pip_freeze.txt"
  exit 0
fi

if [[ -d "$VENV" ]]; then
  mv "$VENV" "${VENV}_incompatible_$(date -u +%Y%m%d_%H%M%S)"
fi
python -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel

SIONNA_SHA256="62e919c8db9e6c046ba2abb96345bbb3ff0385318c4a54d5b1a413a6b8da8b01"
"$VENV/bin/python" -m pip download \
  --no-deps --only-binary=:all: --dest "$WHEELS" \
  "sionna-no-rt==2.0.1"
SIONNA_WHEEL="$WHEELS/sionna_no_rt-2.0.1-py3-none-any.whl"
[[ "$(sha256sum "$SIONNA_WHEEL" | awk '{print $1}')" == "$SIONNA_SHA256" ]]

"$VENV/bin/python" -m pip install \
  --index-url https://download.pytorch.org/whl/cu128 \
  "torch==2.9.1"
"$VENV/bin/python" -m pip install \
  "$SIONNA_WHEEL" \
  "pandas>=2.2,<3" \
  "numpy>=2.0,<3" \
  "scipy>=1.14,<2"

"$VENV/bin/python" -m pip check
"$VENV/bin/python" - <<'PY'
import importlib.metadata
import torch
assert importlib.metadata.version("torch").split("+", 1)[0] == "2.9.1"
assert importlib.metadata.version("sionna-no-rt") == "2.0.1"
assert torch.version.cuda is not None
print("PHASE-1 NIBI ENVIRONMENT: PASS")
print("Torch:", torch.__version__)
print("CUDA build:", torch.version.cuda)
print("Sionna:", importlib.metadata.version("sionna-no-rt"))
PY
"$VENV/bin/python" -m pip freeze --all > "$BASE/pip_freeze.txt"
