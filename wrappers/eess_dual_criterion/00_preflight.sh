#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"; source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]]
git merge-base --is-ancestor 9c00f3c9cacc2a817cae8f45a154cf069b778306 HEAD
git diff --cached --quiet || { echo "ERROR: staged changes"; git diff --cached --name-status; exit 2; }
python3 -m pytest -q -p no:cacheprovider tests/test_eess_dual_criterion_audit.py
echo "EESS DUAL-CRITERION PREFLIGHT: PASS"
