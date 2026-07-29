#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong Git branch"
  exit 2
}
git merge-base --is-ancestor 11b705b684461fa23e279dc3f3e57557b8488849 HEAD
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected Git origin: $ORIGIN"
  exit 3
}
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 4
}

: "${FR3_REVIEW_ZIP:?FR3_REVIEW_ZIP is required}"
[[ "$(sha256sum "$FR3_REVIEW_ZIP" | awk '{print $1}')" == \
  "8981873eff57575e40d12df40b845f781c4863de3168edc27d1473dad3d4f10e" ]]

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src:$ROOT/scripts" \
python3 -m pytest -q -p no:cacheprovider \
  tests/test_full_topology_export_prep.py

echo "FULL-TOPOLOGY EXPORT PREP PREFLIGHT: PASS"
