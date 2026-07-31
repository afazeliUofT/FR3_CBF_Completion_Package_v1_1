#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: expected branch e3-first-sector-p452"
  exit 2
}

git merge-base --is-ancestor \
  20d65eeb0fcc53f649a4f3f716fa2780406b4810 HEAD

git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

for path in \
  campaign/phase1_nibi_job_package_v1/JOB_PACKAGE_CONTRACT.json \
  campaign/phase1_nibi_job_package_v1/PACKAGE_MANIFEST.sha256 \
  campaign/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip \
  campaign/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip.sha256 \
  evidence/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_REVIEW_v1.zip \
  evidence/phase1_nibi_job_package_v1/EXACT_SLOT0_ALL8_METHOD_SMOKE_AUDIT.json
do
  [[ -f "$path" ]] || {
    echo "ERROR: required job-package review input is missing: $path"
    exit 4
  }
  echo "OK      $path"
done

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_phase1_job_package_independent_review.py

echo "PHASE-1 JOB-PACKAGE INDEPENDENT REVIEW PREFLIGHT: PASS"
