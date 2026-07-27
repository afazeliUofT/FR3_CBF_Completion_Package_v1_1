#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

STAMP="$(date -u +%Y%m%d_%H%M%S)"
if [[ -d data/real/distributed_ia_rzf_architecture ]]; then
  mv data/real/distributed_ia_rzf_architecture \
    "data/real/distributed_ia_rzf_architecture_before_${STAMP}"
fi
if [[ -d results/distributed_ia_rzf_architecture ]]; then
  mv results/distributed_ia_rzf_architecture \
    "results/distributed_ia_rzf_architecture_before_${STAMP}"
fi
mkdir -p data/real/distributed_ia_rzf_architecture \
  results/distributed_ia_rzf_architecture

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/27_0_freeze_distributed_ia_rzf_architecture.py \
  --config config/distributed_ia_rzf_architecture.yaml

echo
cat docs/DISTRIBUTED_IA_RZF_ARCHITECTURE.md
echo "WRAPPER 10 ARCHITECTURE FREEZE: PASS"
