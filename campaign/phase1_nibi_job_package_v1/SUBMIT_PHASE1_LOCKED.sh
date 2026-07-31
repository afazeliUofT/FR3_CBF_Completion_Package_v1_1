#!/usr/bin/env bash
set -Eeuo pipefail
echo "ERROR: Slurm submission is locked"
echo "Review the immutable templates; do not submit before a separate authorization token is issued"
exit 64
