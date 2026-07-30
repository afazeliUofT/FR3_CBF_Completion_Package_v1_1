#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)";cd "$ROOT";source .venv/bin/activate;export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}";export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
python3 scripts/44_0_run_practical_architecture_mapping.py --config config/practical_architecture_mapping_v1.json
python3 scripts/44_1_validate_practical_architecture_mapping.py --config config/practical_architecture_mapping_v1.json
echo 'PRACTICAL ARCHITECTURE RUN/VALIDATION: PASS'
