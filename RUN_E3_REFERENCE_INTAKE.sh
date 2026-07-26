#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -z "${VIRTUAL_ENV:-}" ]] || [[ "$VIRTUAL_ENV" != "$ROOT/.venv" ]]; then
  echo "ERROR: activate $ROOT/.venv before running this wrapper" >&2
  exit 2
fi
export PYTHONDONTWRITEBYTECODE=1
mkdir -p logs
python3 scripts/22_0_rebuild_p452_pilot_evidence.py \
  2>&1 | tee logs/22_0_rebuild_p452_pilot_evidence.log
python3 scripts/22_1_prepare_e3_station.py --config config/e3_reference_intake.yaml \
  2>&1 | tee logs/22_1_prepare_e3_station.log
python3 scripts/22_2_fetch_validate_e3_tle.py --config config/e3_reference_intake.yaml \
  2>&1 | tee logs/22_2_fetch_validate_e3_tle.log
python3 scripts/22_3_generate_select_e3_pass.py --config config/e3_reference_intake.yaml \
  2>&1 | tee logs/22_3_generate_select_e3_pass.log
printf '\nE3 REFERENCE INTAKE: PASS\n'
printf 'Stop here. Do not run the final E3 controller until antenna pattern, cellular layout, and sector P.452 couplings are frozen.\n'
