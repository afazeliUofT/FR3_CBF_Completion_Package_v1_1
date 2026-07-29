#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${FR3_EXPORT_BASE:-$SCRATCH/FR3_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_v1}"
VENV="${FR3_EXPORT_VENV:-$SCRATCH/FR3_DLP_RZF_NIBI_ENV_ca9b33c_nibi_v1/venv}"
mkdir -p "$BASE/logs"

export FR3_EXPORT_BASE="$BASE"
export FR3_EXPORT_VENV="$VENV"
bash "$ROOT/setup_environment.sh"

ACCOUNT="${SLURM_ACCOUNT:-}"
if [[ -z "$ACCOUNT" ]]; then
  mapfile -t ASSOCIATIONS < <(
    sacctmgr -nP show assoc user="$USER" cluster=nibi format=Account 2>/dev/null \
      | cut -d'|' -f1 | sed '/^$/d' | sort -u
  )
  for preferred in def-rsadve_gpu def-rsadve def-rsadve_cpu; do
    for value in "${ASSOCIATIONS[@]}"; do
      [[ "$value" == "$preferred" ]] && ACCOUNT="$value" && break 2
    done
  done
fi
[[ -n "$ACCOUNT" ]] || {
  echo "ERROR: no Nibi Slurm account selected"
  exit 2
}

JOB_ID="$(
  sbatch \
    --parsable \
    --account="$ACCOUNT" \
    --nodes=1 \
    --ntasks=1 \
    --gpus=h100:1 \
    --cpus-per-task=16 \
    --mem=192G \
    --time=04:00:00 \
    --job-name=fr3-fulltopo-export-v1 \
    --output="$BASE/logs/export-%j.out" \
    --error="$BASE/logs/export-%j.err" \
    --export=ALL,FR3_PACKAGE_ROOT="$ROOT",FR3_EXPORT_BASE="$BASE",FR3_EXPORT_VENV="$VENV" \
    "$ROOT/export_worker.sh"
)"
echo "Submitted Nibi full-topology export job: $JOB_ID"
