#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)";cd "$ROOT";source .venv/bin/activate;export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]];git merge-base --is-ancestor e69265eb43106e6875d28e80de449b148b73008f HEAD;git diff --cached --quiet || { echo 'ERROR: pre-existing staged changes';git diff --cached --name-status;exit 2; }
for p in data/real/full_topology_export_18696267_validated_v4/output/frequency_response.npy data/real/eess_dual_criterion_audit_v1/kappa_long_p20_single.npy evidence/sector_selective_backoff_v1/SECTOR_BACKOFF_GATE_DECISION.json source_inputs/practical_architecture_mapping_v1/SIONNA_8X8_DUAL_PORT_ORDER.csv;do [[ -f "$p" ]]||{ echo "MISSING $p";exit 3;};echo "OK      $p";done
python3 -m pytest -q -p no:cacheprovider tests/test_practical_architecture_mapping.py
echo 'PRACTICAL ARCHITECTURE PREFLIGHT: PASS'
