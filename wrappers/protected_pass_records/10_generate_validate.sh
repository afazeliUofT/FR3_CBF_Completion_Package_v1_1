#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/45_0_generate_protected_pass_records.py \
  --config config/protected_pass_records_phase1_v1.json

python3 scripts/45_1_validate_protected_pass_records.py \
  --config config/protected_pass_records_phase1_v1.json

echo "PROTECTED-PASS GENERATION/VALIDATION: PASS"
