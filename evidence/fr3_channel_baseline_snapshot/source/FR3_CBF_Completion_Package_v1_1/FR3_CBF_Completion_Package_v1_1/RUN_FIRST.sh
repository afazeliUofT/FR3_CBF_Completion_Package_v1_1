#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-core.txt
python -m pip install -e . --no-build-isolation
python scripts/00_validate_package.py
python -m pytest
python scripts/01_run_smoke_test.py

echo
echo "Software gate passed. Next run: python scripts/02_download_p530_products.py"
echo "Then follow NEXT_IMMEDIATE_STEP.md to build real paired fixed links."
