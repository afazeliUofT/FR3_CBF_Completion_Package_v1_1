#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
BASE="${FR3_NIBI_BASE:-$SCRATCH/FR3_DLP_RZF_NIBI_PILOT_v1}"
mkdir -p "$BASE/logs"

echo "================================================================="
echo "FR3 ONE-SEED 57-SECTOR / 4-USER DLP-RZF NIBI PILOT"
echo "================================================================="
echo "Root: $ROOT"
echo "Base: $BASE"
echo "User: $USER"
echo "Host: $(hostname)"

bash "$ROOT/setup_environment.sh"

if [[ -n "${SLURM_ACCOUNT:-}" ]]; then
  ACCOUNT="$SLURM_ACCOUNT"
else
  mapfile -t ASSOCIATIONS < <(
    sacctmgr -nP show assoc user="$USER" cluster=nibi format=Account 2>/dev/null \
      | sed '/^$/d' | sort -u
  )
  ACCOUNT=""
  for preferred in def-rsadve_gpu def-rsadve def-rsadve_cpu; do
    for value in "${ASSOCIATIONS[@]}"; do
      if [[ "$value" == "$preferred" ]]; then
        ACCOUNT="$value"
        break 2
      fi
    done
  done
  if [[ -z "$ACCOUNT" ]] && [[ "${#ASSOCIATIONS[@]}" -gt 0 ]]; then
    ACCOUNT="${ASSOCIATIONS[0]}"
  fi
fi
[[ -n "$ACCOUNT" ]] || {
  echo "ERROR: no Slurm account could be selected"
  sacctmgr -nP show assoc user="$USER" cluster=nibi format=Account,Partition,QOS || true
  exit 2
}
echo "Selected Slurm account: $ACCOUNT"

JOB_ID="$(
  sbatch \
    --parsable \
    --account="$ACCOUNT" \
    --gpus=h100:1 \
    --cpus-per-task=16 \
    --mem=128G \
    --time=04:00:00 \
    --job-name=fr3-dlp-pilot \
    --output="$BASE/logs/pilot-%j.out" \
    --error="$BASE/logs/pilot-%j.err" \
    "$ROOT/pilot_worker.sh"
)"
echo "Submitted job: $JOB_ID"
printf '%s\n' "$JOB_ID" > "$BASE/job_id.txt"

while squeue -h -j "$JOB_ID" | grep -q .; do
  squeue -j "$JOB_ID" -o '%.18i %.10T %.10M %.20R'
  sleep 30
done

sacct -j "$JOB_ID" --format=JobID,JobName%24,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES -P \
  > "$BASE/logs/sacct-${JOB_ID}.txt"
cat "$BASE/logs/sacct-${JOB_ID}.txt"
STATE="$(sacct -n -X -j "$JOB_ID" --format=State -P | head -n1 | cut -d'|' -f1 | xargs)"
[[ "$STATE" == "COMPLETED" ]] || {
  echo "ERROR: job state is $STATE"
  tail -n 200 "$BASE/logs/pilot-${JOB_ID}.out" || true
  tail -n 200 "$BASE/logs/pilot-${JOB_ID}.err" || true
  exit 3
}

source "$BASE/venv/bin/activate"
python "$ROOT/validate_gpu_pilot.py"

RETURN="$BASE/FR3_DLP_RZF_NIBI_PILOT_RETURN_${JOB_ID}.zip"
rm -f "$RETURN" "$RETURN.sha256"
python - <<PY
from pathlib import Path
import zipfile
root = Path(${ROOT@Q})
base = Path(${BASE@Q})
out = Path(${RETURN@Q})
files = []
for path in sorted((root/"output").rglob("*")):
    if path.is_file():
        files.append((path, path.relative_to(root).as_posix()))
for path in [
    base/"job_id.txt",
    base/"pip_freeze.txt",
    base/"logs"/f"sacct-${JOB_ID}.txt",
    base/"logs"/f"pilot-${JOB_ID}.out",
    base/"logs"/f"pilot-${JOB_ID}.err",
]:
    if path.is_file():
        files.append((path, f"runtime/{path.name}"))
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path, arc in files:
        zf.write(path, arc)
print("Return bundle:", out)
print("Members:", len(files))
PY
sha256sum "$RETURN" > "$RETURN.sha256"
unzip -t "$RETURN"
sha256sum -c "$RETURN.sha256"

echo "================================================================="
echo "NIBI ONE-SEED DLP-RZF PILOT: PASS"
echo "Job ID: $JOB_ID"
echo "Return ZIP: $RETURN"
echo "Checksum: $RETURN.sha256"
echo "================================================================="
