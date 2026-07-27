#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
BASE="${FR3_NARVAL_BASE:-$SCRATCH/FR3_DLP_RZF_NARVAL_PILOT_v1}"
mkdir -p "$BASE/logs"

HOSTNAME_FULL="$(hostname -f 2>/dev/null || hostname)"
[[ "$HOSTNAME_FULL" == *narval* ]] || {
  echo "ERROR: this master must be run on Narval, not on $HOSTNAME_FULL"
  exit 2
}

echo "================================================================="
echo "FR3 ONE-SEED 57-SECTOR / 4-USER DLP-RZF NARVAL PILOT"
echo "================================================================="
echo "Root: $ROOT"
echo "Base: $BASE"
echo "User: $USER"
echo "Host: $HOSTNAME_FULL"

bash "$ROOT/setup_environment.sh"

if [[ -n "${SLURM_ACCOUNT:-}" ]]; then
  ACCOUNT="$SLURM_ACCOUNT"
else
  mapfile -t ASSOCIATIONS < <(
    sacctmgr -nP show assoc user="$USER" cluster=narval format=Account 2>/dev/null \
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
  sacctmgr -nP show assoc user="$USER" cluster=narval \
    format=Account,Partition,QOS || true
  exit 3
}
echo "Selected Slurm account: $ACCOUNT"

JOB_ID="$(
  sbatch \
    --parsable \
    --account="$ACCOUNT" \
    --nodes=1 \
    --ntasks=1 \
    --gpus-per-node=a100:1 \
    --cpus-per-task=12 \
    --mem=124G \
    --time=04:00:00 \
    --job-name=fr3-dlp-narval \
    --output="$BASE/logs/pilot-%j.out" \
    --error="$BASE/logs/pilot-%j.err" \
    "$ROOT/pilot_worker.sh"
)"
echo "Submitted Narval job: $JOB_ID"
printf '%s\n' "$JOB_ID" > "$BASE/job_id.txt"

while squeue -h -j "$JOB_ID" | grep -q .; do
  squeue -j "$JOB_ID" -o '%.18i %.10T %.10M %.30R'
  sleep 30
done

sacct -j "$JOB_ID" \
  --format=JobID,JobName%24,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocTRES \
  -P > "$BASE/logs/sacct-${JOB_ID}.txt"
cat "$BASE/logs/sacct-${JOB_ID}.txt"

STATE="$(
  sacct -n -X -j "$JOB_ID" --format=State -P \
    | head -n1 | cut -d'|' -f1 | xargs
)"
[[ "$STATE" == "COMPLETED" ]] || {
  echo "ERROR: Narval job state is $STATE"
  tail -n 240 "$BASE/logs/pilot-${JOB_ID}.out" || true
  tail -n 240 "$BASE/logs/pilot-${JOB_ID}.err" || true
  exit 4
}

VENV="${FR3_NARVAL_VENV:-$HOME/.venvs/fr3-sionna2-2.0.1-narval-cu128}"
source "$VENV/bin/activate"
python "$ROOT/validate_gpu_pilot.py"

RETURN="$BASE/FR3_DLP_RZF_NARVAL_PILOT_RETURN_${JOB_ID}.zip"
rm -f "$RETURN" "$RETURN.sha256"
python - <<PY
from pathlib import Path
import zipfile

root = Path(${ROOT@Q})
base = Path(${BASE@Q})
out = Path(${RETURN@Q})
files = []
for path in sorted((root / "output").rglob("*")):
    if path.is_file():
        files.append((path, path.relative_to(root).as_posix()))
for path in [
    base / "job_id.txt",
    base / "pip_freeze.txt",
    base / "logs" / f"sacct-${JOB_ID}.txt",
    base / "logs" / f"pilot-${JOB_ID}.out",
    base / "logs" / f"pilot-${JOB_ID}.err",
]:
    if path.is_file():
        files.append((path, f"runtime/{path.name}"))
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path, arcname in files:
        zf.write(path, arcname)
print("Return bundle:", out)
print("Members:", len(files))
PY

sha256sum "$RETURN" > "$RETURN.sha256"
unzip -t "$RETURN"
sha256sum -c "$RETURN.sha256"

echo "================================================================="
echo "NARVAL ONE-SEED DLP-RZF PILOT: PASS"
echo "Job ID: $JOB_ID"
echo "Return ZIP: $RETURN"
echo "Checksum: $RETURN.sha256"
echo "================================================================="
