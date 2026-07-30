#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/36_0_run_fairness_policy_audit.py \
  --config config/fairness_policy_audit_v1.json

python3 scripts/36_1_validate_fairness_policy_audit.py \
  --config config/fairness_policy_audit_v1.json

echo "FAIRNESS POLICY AUDIT RUN/VALIDATION: PASS"
