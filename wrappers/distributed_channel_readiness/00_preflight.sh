#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong branch"
  exit 2
}
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected origin: $ORIGIN"
  exit 2
}
git merge-base --is-ancestor 6d6a589ad0dc08c052f51eb669aeeb9a37c77b14 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 2
}

REQ=(
  data/real/distributed_ia_rzf_architecture/DISTRIBUTED_IA_RZF_ARCHITECTURE_DECISION.json
  data/real/distributed_ia_rzf_architecture/DISTRIBUTED_IA_RZF_PROTOTYPE_AUDIT.json
  data/real/distributed_ia_rzf_architecture/DISTRIBUTED_IA_RZF_VALIDATION.json
  data/real/distributed_ia_rzf_architecture/prototype_time_summary.csv
  src/fr3_cbf/distributed_precoding.py
)
for file in "${REQ[@]}"; do
  [[ -f "$file" ]] || { echo "MISSING $file"; exit 3; }
  echo "OK      $file"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_distributed_precoding.py \
  tests/test_distributed_channel_readiness.py

echo "WRAPPER 00 PREFLIGHT: PASS"
