$ErrorActionPreference = "Stop"
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-core.txt
python -m pip install -e . --no-build-isolation
python scripts/00_validate_package.py
python -m pytest
python scripts/01_run_smoke_test.py
Write-Host ""
Write-Host "Software gate passed. Next run: python scripts/02_download_p530_products.py"
Write-Host "Then follow NEXT_IMMEDIATE_STEP.md to build real paired fixed links."
