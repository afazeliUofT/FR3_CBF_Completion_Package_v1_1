#!/usr/bin/env bash
set -Eeuo pipefail
echo "ERROR: complete phase-1 candidate is not authorized for execution"
echo "Missing: independent PASS and execution authorization token"
exit 64
