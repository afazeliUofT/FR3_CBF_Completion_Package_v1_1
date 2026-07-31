#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

bash \
  campaign/phase1_nibi_deployment_smoke_v1/RUN_PHASE1_NIBI_DEPLOYMENT_SMOKE_FROM_WSL.sh \
  "${FR3_NIBI_HOST:-rsadve1@nibi.alliancecan.ca}"

echo "NONCAMPAIGN NIBI DEPLOYMENT SMOKE EXECUTION WRAPPER: PASS"
