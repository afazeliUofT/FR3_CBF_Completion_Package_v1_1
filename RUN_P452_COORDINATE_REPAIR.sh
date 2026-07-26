#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv || ! -f config/p452_pilot.yaml ]]; then
  echo "ERROR: run this script from the FR3_CBF_Completion_Package_v1_1 repository root." >&2
  exit 2
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONDONTWRITEBYTECODE=1

python3 - <<'PY'
import sys
from pathlib import Path
import yaml

assert "/.venv/" in sys.executable, sys.executable
cfg = yaml.safe_load(Path("config/p452_pilot.yaml").read_text(encoding="utf-8"))
confirmations = cfg["manual_confirmations"]
missing = [name for name, value in confirmations.items() if value is not True]
if missing:
    raise SystemExit(
        "Manual confirmations are not all true. Review the existing pilot first: "
        + ", ".join(missing)
    )
if cfg["pilot"].get("polarization_override") is not None:
    raise SystemExit("polarization_override must remain null for the current G/G pilot")
print("REPAIR CONFIGURATION PREFLIGHT: PASS")
PY

STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p logs

OLD_PILOT=""
if [[ -d data/real/p452_pilot ]]; then
  OLD_PILOT="data/real/p452_pilot_invalid_wrapped_longitude_${STAMP}"
  mv data/real/p452_pilot "$OLD_PILOT"
  echo "Archived invalid pilot: $OLD_PILOT"
fi

TESTS=(tests/test_p452_pilot_coordinate_hotfix.py)
[[ -f tests/test_p452_pilot_role_hotfix.py ]] && TESTS+=(tests/test_p452_pilot_role_hotfix.py)
[[ -f tests/test_p452_pilot_polarization_hotfix.py ]] && TESTS+=(tests/test_p452_pilot_polarization_hotfix.py)
python3 -m pytest -q -p no:cacheprovider "${TESTS[@]}"

python3 -X faulthandler -u scripts/21_0_prepare_p452_pilot.py \
  --config config/p452_pilot.yaml \
  2>&1 | tee logs/21_0_p452_pilot_prepare_coordinate_fix.log

python3 - <<'PY'
import json
from pathlib import Path
import pandas as pd

root = Path("data/real/p452_pilot")
params = json.loads((root / "p452_pilot_parameters.json").read_text(encoding="utf-8"))
profile = pd.read_csv(root / "p452_pilot_profile.csv")
expected_convention = (
    "longitude_degrees_east_signed_-180_to_180;"
    "latitude_degrees_north_-90_to_90"
)
assert params["coordinate_convention"] == expected_convention
assert params["tl_p452_coordinate_argument_order"] == [
    "tx_longitude_deg", "tx_latitude_deg", "rx_longitude_deg", "rx_latitude_deg"
]
assert -180 <= float(params["tx_longitude_deg"]) <= 180
assert -180 <= float(params["rx_longitude_deg"]) <= 180
assert -90 <= float(params["tx_latitude_deg"]) <= 90
assert -90 <= float(params["rx_latitude_deg"]) <= 90
assert abs(float(params["tx_longitude_deg"]) - float(profile.longitude_deg.iloc[0])) <= 1e-7
assert abs(float(params["tx_latitude_deg"]) - float(profile.latitude_deg.iloc[0])) <= 1e-7
assert abs(float(params["rx_longitude_deg"]) - float(profile.longitude_deg.iloc[-1])) <= 1e-7
assert abs(float(params["rx_latitude_deg"]) - float(profile.latitude_deg.iloc[-1])) <= 1e-7
print("SIGNED-LONGITUDE PARAMETER CHECK: PASS")
print("Tx lon/lat:", params["tx_longitude_deg"], params["tx_latitude_deg"])
print("Rx lon/lat:", params["rx_longitude_deg"], params["rx_latitude_deg"])
PY

if [[ -n "$OLD_PILOT" ]]; then
  cmp -s "$OLD_PILOT/p452_pilot_profile.csv" data/real/p452_pilot/p452_pilot_profile.csv || {
    echo "ERROR: regenerated terrain profile differs from the reviewed profile." >&2
    exit 3
  }
  cmp -s "$OLD_PILOT/p452_pilot_path.geojson" data/real/p452_pilot/p452_pilot_path.geojson || {
    echo "ERROR: regenerated path geometry differs from the reviewed geometry." >&2
    exit 4
  }
  echo "REVIEWED PROFILE/GEOMETRY REUSE CHECK: PASS"
fi

python3 -X faulthandler -u scripts/21_0_prepare_p452_pilot.py \
  --config config/p452_pilot.yaml \
  --confirm \
  2>&1 | tee logs/21_0_p452_pilot_freeze_coordinate_fix.log

python3 scripts/21_2_preflight_p452_pilot_inputs.py \
  --pilot-dir data/real/p452_pilot \
  2>&1 | tee logs/21_2_p452_pilot_input_preflight.log

find scripts tests src -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests src -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

echo
echo "P.452 PILOT COORDINATE REPAIR: PASS"
echo "The frozen pilot now uses signed western longitudes and has passed the pre-MATLAB gate."
echo "Next: copy the pilot and MATLAB runner to the validated Windows folder, then run MATLAB."
