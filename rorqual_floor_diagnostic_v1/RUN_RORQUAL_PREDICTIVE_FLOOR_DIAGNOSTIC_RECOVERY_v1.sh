#!/usr/bin/env bash
# Reuse the preserved Rorqual seed-43999 channel and run a CPU-only diagnostic.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
SCRIPT_REL="$(realpath --relative-to="$ROOT" "$SCRIPT_DIR")"

HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
REMOTE_BASE="/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_SMOKE_5037b4e33448_20260801_031008"
ORIGINAL_JOB_ID="18041525"
SEED="43999"
CPUS=16
MEMORY_GIB=32
TIME_LIMIT="01:00:00"
POLL_SECONDS=20

STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_RETURN="/mnt/c/Users/alifa/Downloads/FR3_RORQUAL_FLOOR_DIAGNOSTIC_${ORIGINAL_JOB_ID}_${STAMP}"
LOCAL_LOG="$LOCAL_RETURN/local_floor_diagnostic.log"
mkdir -p "$LOCAL_RETURN"
exec > >(tee "$LOCAL_LOG") 2>&1

CONTROL_PATH="/tmp/fr3_rq_floor_${UID}_$$_%C"
SSH_OPTS=(
  -o ControlMaster=auto
  -o ControlPersist=20m
  -o ControlPath="$CONTROL_PATH"
  -o ServerAliveInterval=60
  -o ServerAliveCountMax=5
)
SCP_OPTS=(
  -o ControlMaster=auto
  -o ControlPersist=20m
  -o ControlPath="$CONTROL_PATH"
  -o ServerAliveInterval=60
  -o ServerAliveCountMax=5
)

close_control() {
  ssh "${SSH_OPTS[@]}" -O exit "$HOST" >/dev/null 2>&1 || true
}
trap close_control EXIT

fail() {
  code=$?
  trap - ERR
  echo
  echo "RORQUAL FLOOR DIAGNOSTIC RECOVERY: FAIL"
  echo "Exit code: $code"
  echo "Command: ${BASH_COMMAND:-unknown}"
  echo "Local return: $LOCAL_RETURN"
  echo "H100 channel regenerated: NO"
  echo "Confirmatory campaign authorized: NO"
  exit "$code"
}
trap fail ERR

echo "================================================================="
echo "RORQUAL PREDICTIVE-FLOOR DIAGNOSTIC RECOVERY"
echo "================================================================="
echo "Original H100 job: $ORIGINAL_JOB_ID"
echo "Preserved channel root: $REMOTE_BASE"
echo "Diagnostic compute: CPU only"
echo "H100 channel regenerated: NO"
echo "Confirmatory campaign authorized: NO"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: expected branch e3-first-sector-p452"
  exit 2
}
git merge-base --is-ancestor \
  910dd69e82ce313dcab8f421957ca6c68539a382 HEAD
git diff --cached --quiet || {
  echo "ERROR: staged changes exist"
  exit 3
}

(
  cd "$SCRIPT_DIR"
  sha256sum -c RORQUAL_FLOOR_DIAGNOSTIC_MANIFEST.sha256
  python3 -m py_compile diagnose_predictive_floor.py
  bash -n "$(basename "${BASH_SOURCE[0]}")"
)

git add -- "$SCRIPT_REL"
if ! git diff --cached --quiet; then
  git diff --cached --check
  git commit -m "Add CPU diagnostic for Rorqual predictive floor failure"
  git push
fi
SOURCE_COMMIT="$(git rev-parse HEAD)"

REMOTE_DIAG="$REMOTE_BASE/predictive_floor_diagnostic_v1"
REMOTE_RETURN="$REMOTE_DIAG/return"

echo
echo "=== Verify preserved Rorqual channel and failure artifacts ==="
ssh "${SSH_OPTS[@]}" "$HOST" \
  "REMOTE_BASE='$REMOTE_BASE' ORIGINAL_JOB_ID='$ORIGINAL_JOB_ID' bash -s" <<'REMOTE_PREFLIGHT'
set -Eeuo pipefail
for path in \
  "$REMOTE_BASE/package_rorqual_smoke/phase1_seed_worker.py" \
  "$REMOTE_BASE/package_rorqual_smoke/PHASE1_CAMPAIGN_CONTRACT_V3.json" \
  "$REMOTE_BASE/run/results/seed_43999/channel/CHANNEL_RECORD.json" \
  "$REMOTE_BASE/run/results/seed_43999/channel/frequency_response.npy" \
  "$REMOTE_BASE/run/runtime/RORQUAL_ENVIRONMENT_LOCK.json" \
  "$REMOTE_BASE/run/logs/smoke-${ORIGINAL_JOB_ID}.out" \
  "$REMOTE_BASE/run/logs/smoke-${ORIGINAL_JOB_ID}.err" \
  "$REMOTE_BASE/run/logs/sacct-${ORIGINAL_JOB_ID}.txt"
do
  [[ -f "$path" ]] || {
    echo "ERROR: preserved artifact is missing: $path"
    exit 10
  }
  echo "OK      $path"
done
echo "PRESERVED CHANNEL/FAILURE ARTIFACTS: PASS"
REMOTE_PREFLIGHT

ssh "${SSH_OPTS[@]}" "$HOST" \
  "mkdir -p '$REMOTE_DIAG' '$REMOTE_RETURN' && rm -f '$REMOTE_RETURN'/*"
scp "${SCP_OPTS[@]}" "$SCRIPT_DIR/diagnose_predictive_floor.py" \
  "${HOST}:${REMOTE_DIAG}/"

echo
echo "=== Submit CPU-only diagnostic (no H100, no channel regeneration) ==="
if ssh "${SSH_OPTS[@]}" "$HOST" \
  "REMOTE_BASE='$REMOTE_BASE' REMOTE_DIAG='$REMOTE_DIAG' REMOTE_RETURN='$REMOTE_RETURN' ORIGINAL_JOB_ID='$ORIGINAL_JOB_ID' SEED='$SEED' CPUS='$CPUS' MEMORY_GIB='$MEMORY_GIB' TIME_LIMIT='$TIME_LIMIT' POLL_SECONDS='$POLL_SECONDS' SOURCE_COMMIT='$SOURCE_COMMIT' bash -s" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

BASE="$REMOTE_BASE"
DIAG="$REMOTE_DIAG"
RETURN="$REMOTE_RETURN"
PACKAGE="$BASE/package_rorqual_smoke"
SOURCE_RUN="$BASE/run"
RUN="$DIAG/run"
LOGS="$RUN/logs"
ENV_ROOT="$(readlink -f "$HOME/links/scratch/FR3_PHASE1_RORQUAL_ENV_5037b4e33448")"
VENV="$ENV_ROOT/venv"

rm -rf "$RUN"
mkdir -p "$RUN" "$LOGS" "$RUN/summary" "$RETURN"

mapfile -t ACCOUNTS < <(
  sacctmgr -nP show assoc \
    user="$USER" cluster=rorqual format=Account 2>/dev/null \
  | cut -d'|' -f1 \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | sed '/^$/d' \
  | sort -u
)
ACCOUNT=""
for preferred in def-rsadve_cpu def-rsadve def-rsadve_gpu; do
  for value in "${ACCOUNTS[@]}"; do
    if [[ "$value" == "$preferred" ]]; then
      ACCOUNT="$value"
      break 2
    fi
  done
done
[[ -n "$ACCOUNT" ]] || {
  echo "ERROR: no Rorqual account selected"
  exit 20
}

SBATCH="$RUN/floor_diagnostic.sbatch"
cat > "$SBATCH" <<EOF
#!/usr/bin/env bash
#SBATCH --account=$ACCOUNT
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=$CPUS
#SBATCH --mem=${MEMORY_GIB}G
#SBATCH --time=$TIME_LIMIT
#SBATCH --job-name=fr3-p1-floor-d
#SBATCH --output=$LOGS/floor-%j.out
#SBATCH --error=$LOGS/floor-%j.err

set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export MKL_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export OPENBLAS_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export NUMEXPR_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"

python "$DIAG/diagnose_predictive_floor.py" \
  --package-root "$PACKAGE" \
  --channel-root "$SOURCE_RUN/results/seed_${SEED}/channel" \
  --output-root "$RUN/summary" \
  --original-job-id "$ORIGINAL_JOB_ID"

echo "CPU-ONLY RORQUAL FLOOR DIAGNOSTIC: PASS"
EOF
chmod 700 "$SBATCH"

JOB_ID="$(sbatch --parsable "$SBATCH")"
printf '%s\n' "$JOB_ID" > "$RUN/diagnostic_job_id.txt"
echo "Submitted diagnostic CPU job: $JOB_ID"
echo "H100 requested: NO"
echo "Preserved channel reused: YES"

while squeue -h -j "$JOB_ID" 2>/dev/null | grep -q .; do
  squeue -j "$JOB_ID" -o '%.18i %.10T %.10M %.35R' || true
  sleep "$POLL_SECONDS"
done

STATE=""
for _attempt in $(seq 1 30); do
  sacct -j "$JOB_ID" \
    --format=JobID,JobName%24,State,ExitCode,Elapsed,MaxRSS,MaxVMSize,ReqMem,AllocTRES \
    -P > "$LOGS/sacct-${JOB_ID}.txt" || true
  STATE="$(
    sacct -n -X -j "$JOB_ID" --format=State -P 2>/dev/null \
      | head -n1 | cut -d'|' -f1 | xargs
  )"
  [[ -n "$STATE" ]] && break
  sleep 10
done
cat "$LOGS/sacct-${JOB_ID}.txt" || true
echo "Final diagnostic state: ${STATE:-UNKNOWN}"

MODE="PASS"
if [[ "${STATE:-}" != COMPLETED* ]]; then
  MODE="FAIL"
fi

ZIP_NAME="FR3_RORQUAL_PREDICTIVE_FLOOR_DIAGNOSTIC_${JOB_ID}.zip"
ZIP_PATH="$RETURN/$ZIP_NAME"
python3 - "$MODE" "$BASE" "$DIAG" "$ZIP_PATH" "$JOB_ID" \
  "$ORIGINAL_JOB_ID" "$SOURCE_COMMIT" <<'PY'
from pathlib import Path
import json
import sys
import zipfile

mode, base_s, diag_s, out_s, job_id, original_job, source_commit = sys.argv[1:]
base = Path(base_s)
diag = Path(diag_s)
out = Path(out_s)
files = []

def add(path: Path, arcname: str) -> None:
    if path.is_file():
        files.append((path, arcname))

for path, arcname in [
    (base / f"run/logs/smoke-{original_job}.out",
     f"original_failure/smoke-{original_job}.out"),
    (base / f"run/logs/smoke-{original_job}.err",
     f"original_failure/smoke-{original_job}.err"),
    (base / f"run/logs/sacct-{original_job}.txt",
     f"original_failure/sacct-{original_job}.txt"),
    (base / "run/runtime/RORQUAL_ENVIRONMENT_LOCK.json",
     "environment/RORQUAL_ENVIRONMENT_LOCK.json"),
    (base / "run/runtime/pip_freeze_exact.txt",
     "environment/pip_freeze_exact.txt"),
    (base / "run/results/seed_43999/channel/CHANNEL_RECORD.json",
     "channel/CHANNEL_RECORD.json"),
    (diag / "diagnose_predictive_floor.py",
     "diagnostic_source/diagnose_predictive_floor.py"),
    (diag / "run/diagnostic_job_id.txt",
     "slurm/diagnostic_job_id.txt"),
    (diag / f"run/logs/sacct-{job_id}.txt",
     f"slurm/sacct-{job_id}.txt"),
    (diag / f"run/logs/floor-{job_id}.out",
     f"slurm/floor-{job_id}.out"),
    (diag / f"run/logs/floor-{job_id}.err",
     f"slurm/floor-{job_id}.err"),
    (diag / "run/floor_diagnostic.sbatch",
     "slurm/floor_diagnostic.sbatch"),
]:
    add(path, arcname)

summary = diag / "run/summary"
if summary.is_dir():
    for path in sorted(summary.rglob("*")):
        if path.is_file():
            add(path, f"summary/{path.relative_to(summary).as_posix()}")

metadata = {
    "schema_version": 1,
    "status": (
        "PASS_RORQUAL_FLOOR_DIAGNOSTIC_RETURN_READY"
        if mode == "PASS"
        else "FAIL_RORQUAL_FLOOR_DIAGNOSTIC_RETURN_READY"
    ),
    "mode": mode,
    "original_h100_job_id": original_job,
    "diagnostic_cpu_job_id": job_id,
    "diagnostic_source_commit": source_commit,
    "smoke_seed": 43999,
    "original_channel_reused": True,
    "h100_channel_regenerated": False,
    "immutable_job_package_modified": False,
    "confirmatory_campaign_authorized": False,
    "file_count": len(files),
}
meta = diag / "run/RETURN_METADATA.json"
meta.write_text(
    json.dumps(metadata, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
add(meta, "RETURN_METADATA.json")

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
    for path, arcname in files:
        z.write(path, arcname)
with zipfile.ZipFile(out) as z:
    bad = z.testzip()
    if bad is not None:
        raise RuntimeError(f"corrupt return member: {bad}")
PY

(
  cd "$RETURN"
  sha256sum "$ZIP_NAME" > "$ZIP_NAME.sha256"
  sha256sum -c "$ZIP_NAME.sha256"
  unzip -t "$ZIP_NAME" >/dev/null
)

if [[ "$MODE" == "PASS" ]]; then
  printf 'status=PASS\ndiagnostic_cpu_job_id=%s\n' "$JOB_ID" \
    > "$RETURN/REMOTE_DIAGNOSTIC_SUCCESS_STATUS.txt"
else
  printf 'status=FAIL\ndiagnostic_cpu_job_id=%s\n' "$JOB_ID" \
    > "$RETURN/REMOTE_DIAGNOSTIC_FAILURE_STATUS.txt"
fi

[[ "$MODE" == "PASS" ]]
REMOTE_SCRIPT
then
  REMOTE_EXIT=0
else
  REMOTE_EXIT=$?
fi

echo
echo "=== Retrieve compact diagnostic return ==="
scp "${SCP_OPTS[@]}" -r \
  "${HOST}:${REMOTE_RETURN}/." "$LOCAL_RETURN/"

find "$LOCAL_RETURN" -maxdepth 2 -type f \
  -printf '%p | %s bytes\n' | sort

ZIP="$(
  find "$LOCAL_RETURN" -maxdepth 1 -type f \
    -name 'FR3_RORQUAL_PREDICTIVE_FLOOR_DIAGNOSTIC_*.zip' \
  | head -n1
)"
[[ -f "$ZIP" ]] || {
  echo "ERROR: diagnostic ZIP was not retrieved"
  exit 30
}
SHA="${ZIP}.sha256"
[[ -f "$SHA" ]] || {
  echo "ERROR: diagnostic checksum was not retrieved"
  exit 31
}
(
  cd "$LOCAL_RETURN"
  sha256sum -c "$(basename "$SHA")"
  unzip -t "$(basename "$ZIP")" >/dev/null
)

EVIDENCE="$ROOT/evidence/phase1_rorqual_predictive_floor_diagnostic_v1"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"
cp -p "$ZIP" "$SHA" "$LOCAL_LOG" "$EVIDENCE/"

python3 - "$ZIP" "$EVIDENCE" "$REMOTE_EXIT" <<'PY'
from pathlib import Path
import hashlib
import json
import sys
import zipfile

archive = Path(sys.argv[1])
evidence = Path(sys.argv[2])
remote_exit = int(sys.argv[3])

with zipfile.ZipFile(archive) as z:
    for name in z.namelist():
        if name.startswith("summary/") and not name.endswith("/"):
            target = evidence / Path(name).name
            target.write_bytes(z.read(name))
        elif name == "RETURN_METADATA.json":
            (evidence / "RETURN_METADATA.json").write_bytes(
                z.read(name)
            )

audit_path = evidence / "PREDICTIVE_FLOOR_DIAGNOSTIC_AUDIT.json"
audit = (
    json.loads(audit_path.read_text(encoding="utf-8"))
    if audit_path.is_file()
    else None
)
status = {
    "schema_version": 1,
    "status": (
        "PASS_RORQUAL_FLOOR_DIAGNOSTIC_COLLECTED_REVIEW_REQUIRED"
        if remote_exit == 0 and audit is not None
        else "FAIL_RORQUAL_FLOOR_DIAGNOSTIC_COLLECTED_REVIEW_REQUIRED"
    ),
    "remote_exit": remote_exit,
    "original_h100_job_id": "18041525",
    "smoke_seed": 43999,
    "original_channel_reused": True,
    "h100_channel_regenerated": False,
    "confirmatory_campaign_authorized": False,
    "audit": audit,
    "next_gate": "SCIENTIFICALLY_REVIEW_PREDICTIVE_FLOOR_DIAGNOSTIC",
}
(evidence / "COLLECTION_STATUS.json").write_text(
    json.dumps(status, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

manifest = evidence / "EVIDENCE_MANIFEST.sha256"
lines = []
for path in sorted(evidence.rglob("*")):
    if path.is_file() and path != manifest:
        lines.append(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
            f"{path.relative_to(evidence).as_posix()}"
        )
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

git add -- "$SCRIPT_REL" \
  evidence/phase1_rorqual_predictive_floor_diagnostic_v1
git diff --cached --check
git commit -m \
  "Collect CPU diagnostic for excluded Rorqual predictive floor failure"
git push

FINAL_COMMIT="$(git rev-parse HEAD)"
REMOTE_BRANCH="$(
  git ls-remote --heads origin e3-first-sector-p452 | awk '{print $1}'
)"
[[ "$REMOTE_BRANCH" == "$FINAL_COMMIT" ]] || {
  echo "ERROR: remote branch does not equal evidence commit"
  exit 32
}

echo
echo "================================================================="
echo "RORQUAL PREDICTIVE-FLOOR DIAGNOSTIC RECOVERY: PASS"
echo "Original H100 job: $ORIGINAL_JOB_ID"
echo "Evidence commit: $FINAL_COMMIT"
echo "Diagnostic ZIP: $ZIP"
echo "Diagnostic ZIP SHA-256: $(sha256sum "$ZIP" | awk '{print $1}')"
echo "Original channel reused: YES"
echo "H100 channel regenerated: NO"
echo "Confirmatory campaign authorized: NO"
echo "Next gate: SCIENTIFICALLY_REVIEW_PREDICTIVE_FLOOR_DIAGNOSTIC"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
fi

[[ "$REMOTE_EXIT" -eq 0 ]]
