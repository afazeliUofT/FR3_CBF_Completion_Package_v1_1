#!/usr/bin/env bash
set -Eeuo pipefail
echo "ERROR: phase-1 Nibi campaign execution is not authorized"
echo "Missing: independent job-package PASS and explicit execution authorization token"
exit 64
