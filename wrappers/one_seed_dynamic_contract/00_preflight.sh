#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong Git branch"
  exit 2
}
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected Git origin: $ORIGIN"
  exit 2
}
git merge-base --is-ancestor ca9b33ced8c9040438389ebd793f35020e8c54c2 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 2
}

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_one_seed_dynamic_contract.py

echo "ONE-SEED/DYNAMIC-CONTRACT PREFLIGHT: PASS"
