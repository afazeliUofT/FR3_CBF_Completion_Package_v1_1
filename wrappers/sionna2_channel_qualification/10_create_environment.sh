#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

CONFIG="config/sionna2_channel_qualification.json"
VENV="$HOME/.venvs/fr3-sionna2-2.0.1-cpu"
WHEEL_DIR="data/external/sionna2_qualification/wheels"
WORK="data/real/sionna2_channel_qualification"
EXPECTED_SIONNA_SHA="62e919c8db9e6c046ba2abb96345bbb3ff0385318c4a54d5b1a413a6b8da8b01"

mkdir -p "$HOME/.venvs" "$WHEEL_DIR" "$WORK"

if [[ -d "$VENV" ]]; then
  MATCH="$(
    "$VENV/bin/python" - <<'PY' 2>/dev/null || true
import importlib.metadata
try:
    print(
        "yes"
        if importlib.metadata.version("torch").split("+", 1)[0] == "2.9.1"
        and importlib.metadata.version("sionna-no-rt") == "2.0.1"
        else "no"
    )
except Exception:
    print("no")
PY
  )"
  if [[ "$MATCH" != "yes" ]]; then
    STAMP="$(date -u +%Y%m%d_%H%M%S)"
    mv "$VENV" "${VENV}_before_${STAMP}"
    echo "Archived incompatible prior environment."
  fi
fi

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
fi

rm -f "$WHEEL_DIR"/sionna_no_rt-2.0.1-py3-none-any.whl
"$VENV/bin/python" -m pip download \
  --no-deps \
  --only-binary=:all: \
  --dest "$WHEEL_DIR" \
  "sionna-no-rt==2.0.1"

SIONNA_WHEEL="$WHEEL_DIR/sionna_no_rt-2.0.1-py3-none-any.whl"
[[ -f "$SIONNA_WHEEL" ]] || {
  echo "ERROR: expected Sionna wheel was not downloaded"
  exit 4
}
ACTUAL_SIONNA_SHA="$(sha256sum "$SIONNA_WHEEL" | awk '{print $1}')"
[[ "$ACTUAL_SIONNA_SHA" == "$EXPECTED_SIONNA_SHA" ]] || {
  echo "ERROR: Sionna wheel SHA-256 mismatch"
  echo "Expected: $EXPECTED_SIONNA_SHA"
  echo "Actual:   $ACTUAL_SIONNA_SHA"
  exit 5
}

"$VENV/bin/python" -m pip install \
  --index-url https://download.pytorch.org/whl/cpu \
  "torch==2.9.1"

"$VENV/bin/python" -m pip install "$SIONNA_WHEEL"
"$VENV/bin/python" -m pip check

"$VENV/bin/python" - <<'PY'
import importlib.metadata
import sys
import torch
import sionna
assert importlib.metadata.version("torch").split("+", 1)[0] == "2.9.1"
assert importlib.metadata.version("sionna-no-rt") == "2.0.1"
print("SIONNA ENVIRONMENT IMPORT: PASS")
print("Python:", sys.version)
print("Torch:", torch.__version__)
print("Sionna distribution:", importlib.metadata.version("sionna-no-rt"))
print("CUDA available:", torch.cuda.is_available())
PY

printf '%s\n' "$VENV" > "$WORK/VENV_PATH.txt"
printf '%s  %s\n' "$ACTUAL_SIONNA_SHA" "$SIONNA_WHEEL" \
  > "$WORK/SIONNA_TOP_LEVEL_WHEEL.sha256"
"$VENV/bin/python" -m pip freeze --all \
  > "$WORK/PIP_FREEZE.txt"
"$VENV/bin/python" -m pip list --format=json \
  > "$WORK/PIP_LIST.json"
"$VENV/bin/python" -m pip check \
  > "$WORK/PIP_CHECK.txt"

echo "SIONNA 2.0.1 ISOLATED ENVIRONMENT: PASS"
echo "Environment: $VENV"
echo "Sionna wheel SHA-256: $ACTUAL_SIONNA_SHA"
echo "WRAPPER 10 CREATE ENVIRONMENT: PASS"
