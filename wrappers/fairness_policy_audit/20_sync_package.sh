#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/36_2_sync_fairness_policy_status.py \
  --config config/fairness_policy_audit_v1.json

python3 scripts/36_3_build_fairness_review_bundle.py \
  --config config/fairness_policy_audit_v1.json

echo
python3 -m json.tool \
  evidence/fairness_policy_audit_v1/FAIRNESS_POLICY_DECISION.json
echo
python3 -m json.tool \
  results/fairness_policy_audit_v1/FAIRNESS_POLICY_AUDIT.json \
  | tail -n 160

echo "FAIRNESS POLICY STATUS/PACKAGE: PASS"
