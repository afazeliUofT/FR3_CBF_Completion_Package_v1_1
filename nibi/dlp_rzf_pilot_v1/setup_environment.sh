#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${FR3_NIBI_BASE:-$SCRATCH/FR3_DLP_RZF_NIBI_PILOT_v1}"
VENV="$BASE/venv"
WHEELS="$BASE/wheels"
mkdir -p "$BASE" "$WHEELS"

module --force purge
module load StdEnv/2023
module load python/3.12.4

if [[ ! -x "$VENV/bin/python" ]]; then
  python -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
fi

SIONNA_SHA256="62e919c8db9e6c046ba2abb96345bbb3ff0385318c4a54d5b1a413a6b8da8b01"
rm -f "$WHEELS"/sionna_no_rt-2.0.1-py3-none-any.whl
"$VENV/bin/python" -m pip download \
  --no-deps \
  --only-binary=:all: \
  --dest "$WHEELS" \
  "sionna-no-rt==2.0.1"
SIONNA_WHEEL="$WHEELS/sionna_no_rt-2.0.1-py3-none-any.whl"
[[ -f "$SIONNA_WHEEL" ]] || {
  echo "ERROR: Sionna 2.0.1 wheel was not downloaded"
  exit 4
}
ACTUAL_SIONNA_SHA256="$(sha256sum "$SIONNA_WHEEL" | awk '{print $1}')"
[[ "$ACTUAL_SIONNA_SHA256" == "$SIONNA_SHA256" ]] || {
  echo "ERROR: Sionna wheel SHA-256 mismatch"
  echo "Expected: $SIONNA_SHA256"
  echo "Actual:   $ACTUAL_SIONNA_SHA256"
  exit 5
}

"$VENV/bin/python" -m pip install \
  --index-url https://download.pytorch.org/whl/cu128 \
  "torch==2.9.1"

"$VENV/bin/python" -m pip install \
  "$SIONNA_WHEEL" \
  "pandas>=2.2,<3" \
  "numpy>=2.0,<3" \
  "scipy>=1.14,<2" \
  "pyproj>=3.6,<4"
printf '%s  %s\n' "$ACTUAL_SIONNA_SHA256" "$SIONNA_WHEEL" \
  > "$BASE/sionna_top_level_wheel.sha256"

"$VENV/bin/python" -m pip check
"$VENV/bin/python" - <<'PY'
import importlib.metadata
import torch
assert importlib.metadata.version("torch").split("+",1)[0] == "2.9.1"
assert importlib.metadata.version("sionna-no-rt") == "2.0.1"
print("NIBI PILOT ENVIRONMENT SETUP: PASS")
print("Torch:", torch.__version__)
print("CUDA build:", torch.version.cuda)
print("CUDA visible on login:", torch.cuda.is_available())
from sionna.phy.channel.tr38901 import PanelArray
array = PanelArray(
    num_rows_per_panel=8,
    num_cols_per_panel=8,
    polarization="dual",
    polarization_type="cross",
    antenna_pattern="38.901",
    carrier_frequency=8.15e9,
    element_vertical_spacing=0.5,
    element_horizontal_spacing=0.5,
    precision="single",
    device="cpu",
)
assert array.num_ant == 128
print("NIBI PANELARRAY API PROBE: PASS")
PY
"$VENV/bin/python" -m pip freeze --all > "$BASE/pip_freeze.txt"
printf '%s\n' "$VENV" > "$BASE/venv_path.txt"
echo "Environment: $VENV"
