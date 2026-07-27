#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong branch"
  exit 2
}
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected Git origin: $ORIGIN"
  exit 2
}
git merge-base --is-ancestor 95ba554e31b7505b97f09cb6ed23c6ba115ad653 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 2
}

REQ=(
  evidence/sionna2_channel_qualification/SIONNA2_API_QUALIFICATION_AUDIT.json
  evidence/sionna2_channel_qualification/CHANNEL_IMPLEMENTATION_DECISION.json
  data/real/bs_sites.csv
  data/real/bs_sectors.csv
)
for path in "${REQ[@]}"; do
  [[ -f "$path" ]] || { echo "MISSING $path"; exit 3; }
  echo "OK      $path"
done

VENV="$HOME/.venvs/fr3-sionna2-2.0.1-cpu"
[[ -x "$VENV/bin/python" ]] || {
  echo "ERROR: qualified Sionna environment is missing"
  exit 4
}

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_sionna2_topology_readiness_static.py

echo "WRAPPER 00 PREFLIGHT: PASS"
