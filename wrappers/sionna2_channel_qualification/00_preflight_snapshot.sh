#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/scripts:$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong Git branch"
  exit 2
}
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]] || {
  echo "ERROR: unexpected Git origin: $ORIGIN"
  exit 2
}
git merge-base --is-ancestor 871a3da5b5136e62c2d554ad9516b3a80986fb2c HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes detected"
  git diff --cached --name-status
  exit 2
}

REQ=(
  evidence/fr3_channel_baseline_snapshot/SNAPSHOT_METADATA.json
  evidence/fr3_channel_baseline_snapshot/SOURCE_INVENTORY.csv
  evidence/fr3_channel_baseline_snapshot/BINARY_CANDIDATES.csv
  evidence/fr3_channel_baseline_snapshot/source
)
for path in "${REQ[@]}"; do
  [[ -e "$path" ]] || { echo "MISSING $path"; exit 3; }
  echo "OK      $path"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_sionna2_channel_qualification_static.py

mkdir -p data/real/sionna2_channel_qualification
PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/29_0_close_channel_snapshot_review.py \
  --config config/sionna2_channel_qualification.json

echo "WRAPPER 00 PREFLIGHT/SNAPSHOT REVIEW: PASS"
