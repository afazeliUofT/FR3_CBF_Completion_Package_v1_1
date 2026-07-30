#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]]
git merge-base --is-ancestor \
  ec0ac888fd5ec922fcf9cee0611f322d71df7afb HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 2
}

DATA="data/real/full_topology_export_18696267_validated_v4/output"
[[ -f "$DATA/USER_TOPOLOGY.csv" ]]
[[ -f "$DATA/common_scale_user_rate.npy" ]]

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_fairness_policy_audit.py

echo "FAIRNESS POLICY AUDIT PREFLIGHT: PASS"
