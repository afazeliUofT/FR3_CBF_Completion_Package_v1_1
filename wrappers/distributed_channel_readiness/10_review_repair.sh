#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

STAMP="$(date -u +%Y%m%d_%H%M%S)"
mkdir -p "backups/distributed_architecture_manifest_before_${STAMP}"
cp -p DISTRIBUTED_IA_RZF_ARCHITECTURE_MANIFEST.sha256 \
  "backups/distributed_architecture_manifest_before_${STAMP}/" \
  2>/dev/null || true

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/28_0_review_distributed_architecture.py \
  --config config/distributed_channel_readiness.yaml

PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/28_1_repair_architecture_manifest.py

sha256sum -c DISTRIBUTED_IA_RZF_ARCHITECTURE_MANIFEST.sha256

if grep -E '__pycache__|\.pytest_cache|\.pyc($| )|\.pyo($| )' \
    DISTRIBUTED_IA_RZF_ARCHITECTURE_MANIFEST.sha256; then
  echo "ERROR: prohibited cache entry remains in architecture manifest"
  exit 4
fi

echo
cat data/real/distributed_channel_readiness/DISTRIBUTED_ARCHITECTURE_INDEPENDENT_REVIEW.md
echo "WRAPPER 10 ARCHITECTURE REVIEW/MANIFEST REPAIR: PASS"
