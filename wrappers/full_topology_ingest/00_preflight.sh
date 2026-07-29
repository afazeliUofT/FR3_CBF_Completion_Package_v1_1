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
git merge-base --is-ancestor \
  30800585889d7d8ea127e00dde7de06d9762cce8 HEAD
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

: "${FR3_FULL_ZIP:?FR3_FULL_ZIP is required}"
: "${FR3_REVIEW_ZIP:?FR3_REVIEW_ZIP is required}"

[[ "$(sha256sum "$FR3_FULL_ZIP" | awk '{print $1}')" == \
  "e9ac40e3839e9c5ff6e0fdc9a13145af988a9cfd1b2fbcb48368845e7b9aa42a" ]]
[[ "$(sha256sum "$FR3_REVIEW_ZIP" | awk '{print $1}')" == \
  "b1c2dd5866b1b39b7336e1adba1255b8374ddf10d9b8509e349e7802b5c7c1bf" ]]

unzip -t "$FR3_FULL_ZIP" >/dev/null
unzip -t "$FR3_REVIEW_ZIP" >/dev/null

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_full_topology_dynamic_readiness.py

echo "FULL-TOPOLOGY INGEST PREFLIGHT: PASS"
