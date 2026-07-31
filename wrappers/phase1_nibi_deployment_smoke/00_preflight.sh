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
  74d7ae7354903b9fcade76515b0765286309f7ca HEAD

git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

for path in \
  campaign/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip \
  campaign/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip.sha256 \
  evidence/phase1_nibi_job_package_independent_review_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_v1.zip \
  evidence/phase1_nibi_job_package_independent_review_v1/PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_VERDICT.json \
  config/phase1_nibi_deployment_smoke_v1.json
do
  [[ -f "$path" ]] || {
    echo "ERROR: required smoke-preparation input is missing: $path"
    exit 4
  }
  echo "OK      $path"
done

JOB_SHA="$(
  sha256sum \
    campaign/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip \
  | awk '{print $1}'
)"
[[ "$JOB_SHA" == \
  "a81f1808f75119e64a0f7f631a54230f3e722efa8d17dcf032ee1296f2bb76be" ]]

REVIEW_SHA="$(
  sha256sum \
    evidence/phase1_nibi_job_package_independent_review_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_v1.zip \
  | awk '{print $1}'
)"
[[ "$REVIEW_SHA" == \
  "c42bc8ae5d0772a6dc1c1fc40792d0d10fdb2f9780019d8ea0a089f319767afe" ]]

python3 - <<'PY'
from pathlib import Path
import json
verdict = json.loads(
    Path(
        "evidence/phase1_nibi_job_package_independent_review_v1/"
        "PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_VERDICT.json"
    ).read_text(encoding="utf-8")
)
assert verdict["verdict"] == (
    "PASS_FOR_NIBI_DEPLOYMENT_SMOKE_PREPARATION_"
    "NOT_FULL_CAMPAIGN_EXECUTION"
)
assert verdict["full_30_seed_execution_authorized"] is False
print("JOB-PACKAGE INDEPENDENT REVIEW GATE: PASS")
PY

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_phase1_nibi_deployment_smoke.py

echo "NONCAMPAIGN NIBI DEPLOYMENT SMOKE PREFLIGHT: PASS"
