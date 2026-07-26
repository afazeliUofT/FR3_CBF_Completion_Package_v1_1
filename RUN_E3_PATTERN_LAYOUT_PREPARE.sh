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
python3 scripts/23_0_fetch_sa509.py 2>&1 | tee logs/23_0_fetch_sa509.log
python3 scripts/23_1_rebuild_e3_intake_evidence.py 2>&1 | tee logs/23_1_rebuild_e3_intake_evidence.log
python3 -m pytest -q -p no:cacheprovider tests/test_e3_pattern_layout.py 2>&1 | tee logs/23_pattern_layout_tests.log
python3 scripts/23_2_prepare_e3_pattern_layout.py --config config/e3_pattern_layout.yaml 2>&1 | tee logs/23_2_prepare_e3_pattern_layout.log
printf '\nE3 PATTERN/LAYOUT PREPARATION WRAPPER: PASS\n'
printf 'Stop for manual review. Do not run --confirm until every checklist item has been reviewed.\n'
