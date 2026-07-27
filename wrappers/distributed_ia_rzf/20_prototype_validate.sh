#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/27_1_run_distributed_ia_rzf_prototype.py \
  --config config/distributed_ia_rzf_architecture.yaml

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/27_2_validate_distributed_ia_rzf.py \
  --config config/distributed_ia_rzf_architecture.yaml

echo
cat data/real/distributed_ia_rzf_architecture/DISTRIBUTED_IA_RZF_VALIDATION.md
echo "WRAPPER 20 PROTOTYPE/VALIDATE: PASS"
