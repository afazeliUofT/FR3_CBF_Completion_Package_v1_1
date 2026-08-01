#!/usr/bin/env bash
# FR3 phase-1 excluded noncampaign deployment smoke on Rorqual.
#
# This runner:
#   * uses the already reviewed immutable phase-1 job package unchanged;
#   * creates a smoke-only copy bound to seed 43999;
#   * requests exactly one full H100 on Rorqual;
#   * uses /home/rsadve1/links/scratch for all heavy files;
#   * returns only compact provenance/results (not the full channel arrays);
#   * commits source and return evidence to the current GitHub branch.
#
# It does not authorize or submit the 30-seed confirmatory campaign.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$ROOT"
SCRIPT_REL="$(realpath --relative-to="$ROOT" "$SCRIPT_DIR")"

RORQUAL_HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
RORQUAL_SCRATCH_LINK="/home/rsadve1/links/scratch"

BASE_JOB_ZIP="$ROOT/campaign/phase1_nibi_job_package_v1/FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip"
BASE_JOB_SHA="a81f1808f75119e64a0f7f631a54230f3e722efa8d17dcf032ee1296f2bb76be"
BASE_PACKAGE_ID="bd18734787de7396b9de4bf8c0b9ba4d191c6346a7cb83e969499622067a8129"
CANDIDATE_SHA="f7b47fd3a07e30987b7f0901df1706d6127774d32284e7d3b0da38185d810161"
JOB_PACKAGE_COMMIT="20d65eeb0fcc53f649a4f3f716fa2780406b4810"
JOB_REVIEW_COMMIT="74d7ae7354903b9fcade76515b0765286309f7ca"

SMOKE_SEED=43999
USER_SEED=87998
CHANNEL_SEED=87999

CPUS=16
MEMORY_GIB=124
TIME_LIMIT="04:00:00"
POLL_SECONDS=30
TOKEN_VALIDITY_HOURS=168

LOCAL_RETURN_BASE="/mnt/c/Users/alifa/Downloads"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_RETURN="$LOCAL_RETURN_BASE/FR3_PHASE1_RORQUAL_SMOKE_${STAMP}"
LOCAL_LOG="$LOCAL_RETURN/local_rorqual_orchestrator.log"
TOKEN="$LOCAL_RETURN/LIVE_RORQUAL_SMOKE_AUTHORIZATION.json"
TOKEN_SHA="$TOKEN.sha256"
mkdir -p "$LOCAL_RETURN"
exec > >(tee "$LOCAL_LOG") 2>&1

CONTROL_PATH="/tmp/fr3_rorqual_${UID}_$$_%C"
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
  ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true
}
trap close_control EXIT

failure() {
  code=$?
  trap - ERR
  echo
  echo "================================================================="
  echo "FR3 RORQUAL NONCAMPAIGN SMOKE: FAIL"
  echo "Exit code: $code"
  echo "Command: ${BASH_COMMAND:-unknown}"
  echo "Local return folder: $LOCAL_RETURN"
  echo "Local log: $LOCAL_LOG"
  echo "Confirmatory campaign authorized: NO"
  echo "================================================================="
  exit "$code"
}
trap failure ERR

echo "================================================================="
echo "FR3 PHASE-1 RORQUAL NONCAMPAIGN DEPLOYMENT SMOKE"
echo "================================================================="
echo "Repository: $ROOT"
echo "Rorqual host: $RORQUAL_HOST"
echo "Rorqual scratch link: $RORQUAL_SCRATCH_LINK"
echo "Smoke seed: $SMOKE_SEED"
echo "Confirmatory seeds 44000--44029 used: NONE"
echo "Requested resource: 1 full H100, $CPUS CPUs, ${MEMORY_GIB}G RAM"
echo "Local return folder: $LOCAL_RETURN"
echo "Full campaign authorization: NO"

# ---------------------------------------------------------------------------
# Local immutable-package and Git preflight
# ---------------------------------------------------------------------------
[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: expected branch e3-first-sector-p452"
  exit 2
}
git merge-base --is-ancestor "$JOB_REVIEW_COMMIT" HEAD || {
  echo "ERROR: reviewed job-package commit is not in current history"
  exit 3
}
git diff --cached --quiet || {
  echo "ERROR: staged changes exist before Rorqual smoke"
  git diff --cached --name-status
  exit 4
}
[[ -f "$BASE_JOB_ZIP" ]] || {
  echo "ERROR: immutable phase-1 job-package ZIP is missing"
  exit 5
}
ACTUAL_BASE_SHA="$(sha256sum "$BASE_JOB_ZIP" | awk '{print $1}')"
[[ "$ACTUAL_BASE_SHA" == "$BASE_JOB_SHA" ]] || {
  echo "ERROR: immutable job-package ZIP SHA-256 mismatch"
  echo "Expected: $BASE_JOB_SHA"
  echo "Actual:   $ACTUAL_BASE_SHA"
  exit 6
}

(
  cd "$SCRIPT_DIR"
  sha256sum -c RORQUAL_PORT_MANIFEST.sha256
)

# Commit the reviewed Rorqual-port source before creating a live token.
git add -- "$SCRIPT_REL"
if ! git diff --cached --quiet; then
  git diff --cached --check
  git commit -m "Prepare excluded Rorqual phase1 deployment smoke"
  git push
fi
PORT_COMMIT="$(git rev-parse HEAD)"
REMOTE_BRANCH_SHA="$(
  git ls-remote --heads origin e3-first-sector-p452 \
    | awk '{print $1}'
)"
[[ "$REMOTE_BRANCH_SHA" == "$PORT_COMMIT" ]] || {
  echo "ERROR: remote branch does not equal local Rorqual-port commit"
  exit 7
}

RUNNER_SHA="$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')"
SMOKE_PACKAGE_ID="$(
  printf '%s\n' \
    "$BASE_PACKAGE_ID" \
    "$BASE_JOB_SHA" \
    "$CANDIDATE_SHA" \
    "$JOB_REVIEW_COMMIT" \
    "$PORT_COMMIT" \
    "$RUNNER_SHA" \
    "RORQUAL" \
    "$SMOKE_SEED" \
  | sha256sum | awk '{print $1}'
)"

python3 - "$TOKEN" "$TOKEN_VALIDITY_HOURS" "$SMOKE_PACKAGE_ID" \
  "$BASE_PACKAGE_ID" "$CANDIDATE_SHA" "$SMOKE_SEED" "$PORT_COMMIT" \
  "$BASE_JOB_SHA" "$RUNNER_SHA" <<'PY'
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

(
    output,
    hours,
    package_id,
    base_package_id,
    candidate_sha,
    seed,
    port_commit,
    job_zip_sha,
    runner_sha,
) = sys.argv[1:]
now = datetime.now(timezone.utc)
value = {
    "schema_version": 1,
    # Legacy immutable worker string; the Rorqual wrapper additionally checks
    # cluster, seed, scope, expiry, and distinct smoke package ID.
    "authorization": "EXECUTE_PHASE1_NIBI_V1",
    "execution_authorized": True,
    "execution_scope": "NONCAMPAIGN_RORQUAL_DEPLOYMENT_SMOKE_ONLY",
    "cluster": "rorqual",
    "full_campaign_authorized": False,
    "excluded_from_phase1_confirmatory_analysis": True,
    "package_id": package_id,
    "base_package_id": base_package_id,
    "candidate_zip_sha256": candidate_sha,
    "allowed_seed": int(seed),
    "allowed_job_count": 1,
    "rorqual_port_commit": port_commit,
    "immutable_job_package_zip_sha256": job_zip_sha,
    "runner_sha256": runner_sha,
    "issued_utc": now.isoformat(),
    "expires_utc": (
        now + timedelta(hours=int(hours))
    ).isoformat(),
}
Path(output).write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
sha256sum "$TOKEN" > "$TOKEN_SHA"

echo "LOCAL IMMUTABLE-PACKAGE/TOKEN PREFLIGHT: PASS"
echo "Port commit: $PORT_COMMIT"
echo "Base package ID: $BASE_PACKAGE_ID"
echo "Rorqual smoke package ID: $SMOKE_PACKAGE_ID"
echo "Base job ZIP SHA-256: $BASE_JOB_SHA"
echo "Live token SHA-256: $(awk '{print $1}' "$TOKEN_SHA")"

# ---------------------------------------------------------------------------
# Rorqual connection and scratch preflight
# ---------------------------------------------------------------------------
echo
echo "=== Rorqual connection and scratch preflight ==="
REMOTE_INFO="$(
  ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
    "RORQUAL_SCRATCH_LINK='$RORQUAL_SCRATCH_LINK' bash -s" <<'REMOTE_PREFLIGHT'
set -Eeuo pipefail
host="$(hostname -f 2>/dev/null || hostname)"
[[ "$host" == *rorqual* ]] || {
  echo "ERROR: connection did not reach Rorqual: $host" >&2
  exit 10
}
[[ -d "$RORQUAL_SCRATCH_LINK" ]] || {
  echo "ERROR: Rorqual scratch link is missing: $RORQUAL_SCRATCH_LINK" >&2
  exit 11
}
scratch="$(readlink -f "$RORQUAL_SCRATCH_LINK")"
[[ -d "$scratch" ]] || {
  echo "ERROR: resolved Rorqual scratch is not a directory: $scratch" >&2
  exit 12
}
module --force purge
module load StdEnv/2023
module load python/3.12.4
python --version >&2
printf '__HOST__=%s\n' "$host"
printf '__SCRATCH__=%s\n' "$scratch"
REMOTE_PREFLIGHT
)"
REMOTE_HOST="$(
  printf '%s\n' "$REMOTE_INFO" | sed -n 's/^__HOST__=//p' | tail -n1
)"
REMOTE_SCRATCH="$(
  printf '%s\n' "$REMOTE_INFO" | sed -n 's/^__SCRATCH__=//p' | tail -n1
)"
[[ -n "$REMOTE_HOST" && -n "$REMOTE_SCRATCH" ]] || {
  echo "ERROR: could not resolve Rorqual host/scratch"
  exit 8
}

RUN_TAG="${SMOKE_PACKAGE_ID:0:12}_${STAMP}"
REMOTE_BASE="$REMOTE_SCRATCH/FR3_PHASE1_RORQUAL_SMOKE_${RUN_TAG}"
REMOTE_TRANSFER="$REMOTE_BASE/transfer"
REMOTE_RETURN="$REMOTE_BASE/return"

ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
  "mkdir -p '$REMOTE_TRANSFER' '$REMOTE_RETURN' && rm -f '$REMOTE_RETURN'/*"

echo "RORQUAL CONNECTION/SCRATCH PREFLIGHT: PASS"
echo "Remote host: $REMOTE_HOST"
echo "Resolved scratch: $REMOTE_SCRATCH"
echo "Remote run root: $REMOTE_BASE"

# ---------------------------------------------------------------------------
# Transfer exact reviewed package and live smoke token
# ---------------------------------------------------------------------------
echo
echo "=== Transfer immutable job package and Rorqual smoke token ==="
scp "${SCP_OPTS[@]}" \
  "$BASE_JOB_ZIP" \
  "$TOKEN" \
  "$TOKEN_SHA" \
  "${RORQUAL_HOST}:${REMOTE_TRANSFER}/"

JOB_NAME="$(basename "$BASE_JOB_ZIP")"
TOKEN_NAME="$(basename "$TOKEN")"
TOKEN_SHA_NAME="$(basename "$TOKEN_SHA")"

# ---------------------------------------------------------------------------
# Remote workspace, environment, single H100 job, and compact return
# ---------------------------------------------------------------------------
echo
echo "=== Build workspace and submit exactly one Rorqual H100 smoke job ==="
set +e
ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
  "REMOTE_BASE='$REMOTE_BASE' REMOTE_TRANSFER='$REMOTE_TRANSFER' REMOTE_RETURN='$REMOTE_RETURN' JOB_NAME='$JOB_NAME' TOKEN_NAME='$TOKEN_NAME' TOKEN_SHA_NAME='$TOKEN_SHA_NAME' BASE_JOB_SHA='$BASE_JOB_SHA' BASE_PACKAGE_ID='$BASE_PACKAGE_ID' CANDIDATE_SHA='$CANDIDATE_SHA' SMOKE_PACKAGE_ID='$SMOKE_PACKAGE_ID' SMOKE_SEED='$SMOKE_SEED' USER_SEED='$USER_SEED' CHANNEL_SEED='$CHANNEL_SEED' CPUS='$CPUS' MEMORY_GIB='$MEMORY_GIB' TIME_LIMIT='$TIME_LIMIT' POLL_SECONDS='$POLL_SECONDS' bash -s" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

BASE="$REMOTE_BASE"
TRANSFER="$REMOTE_TRANSFER"
RETURN="$REMOTE_RETURN"
BASE_PACKAGE="$BASE/package_base"
SMOKE_PACKAGE="$BASE/package_rorqual_smoke"
RUN="$BASE/run"
LOGS="$RUN/logs"
ENV_ROOT="$HOME/links/scratch/FR3_PHASE1_RORQUAL_ENV_${SMOKE_PACKAGE_ID:0:12}"
ENV_ROOT="$(readlink -f "$ENV_ROOT")"
VENV="$ENV_ROOT/venv"

rm -rf "$BASE_PACKAGE" "$SMOKE_PACKAGE" "$RUN"
mkdir -p \
  "$BASE_PACKAGE" \
  "$SMOKE_PACKAGE" \
  "$RUN" \
  "$LOGS" \
  "$RUN/runtime" \
  "$RUN/cache" \
  "$RETURN" \
  "$ENV_ROOT"

JOB_ID="not_submitted"

build_return() {
  mode="$1"
  zip_name="$2"
  output="$RETURN/$zip_name"
  rm -f "$output" "$output.sha256"

  python3 - "$mode" "$BASE" "$TRANSFER/$TOKEN_NAME" "$output" \
    "$JOB_ID" "$SMOKE_SEED" <<'PY'
from pathlib import Path
import json
import sys
import zipfile

mode = sys.argv[1]
base = Path(sys.argv[2])
token = Path(sys.argv[3])
output = Path(sys.argv[4])
job_id = sys.argv[5]
seed = sys.argv[6]

package = base / "package_rorqual_smoke"
run = base / "run"
files = []

def add(path: Path, arcname: str) -> None:
    if path.is_file():
        files.append((path, arcname))

for path, arcname in [
    (package / "JOB_PACKAGE_CONTRACT.json", "package/JOB_PACKAGE_CONTRACT.json"),
    (package / "BASE_JOB_PACKAGE_CONTRACT.json", "package/BASE_JOB_PACKAGE_CONTRACT.json"),
    (package / "SMOKE_WORKSPACE_RECORD.json", "package/SMOKE_WORKSPACE_RECORD.json"),
    (package / "SMOKE_WORKSPACE_MANIFEST.sha256", "package/SMOKE_WORKSPACE_MANIFEST.sha256"),
    (run / "runtime/RORQUAL_ENVIRONMENT_LOCK.json", "runtime/RORQUAL_ENVIRONMENT_LOCK.json"),
    (run / "runtime/RORQUAL_ENVIRONMENT_LOCK.json.sha256", "runtime/RORQUAL_ENVIRONMENT_LOCK.json.sha256"),
    (run / "runtime/pip_freeze_exact.txt", "runtime/pip_freeze_exact.txt"),
    (run / "runtime/RORQUAL_SMOKE_AUDIT.json", "runtime/RORQUAL_SMOKE_AUDIT.json"),
    (run / "runtime/RORQUAL_SMOKE_AUDIT.json.sha256", "runtime/RORQUAL_SMOKE_AUDIT.json.sha256"),
    (run / "runtime/SMOKE_COMPLETION_MARKER.txt", "runtime/SMOKE_COMPLETION_MARKER.txt"),
    (run / "job_id.txt", "slurm/job_id.txt"),
    (run / "logs" / f"sacct-{job_id}.txt", f"slurm/sacct-{job_id}.txt"),
    (run / "logs" / f"smoke-{job_id}.out", f"slurm/smoke-{job_id}.out"),
    (run / "logs" / f"smoke-{job_id}.err", f"slurm/smoke-{job_id}.err"),
    (run / "rorqual_smoke.sbatch", "slurm/rorqual_smoke.sbatch"),
    (
        run / "results" / f"seed_{seed}" / "channel/CHANNEL_RECORD.json",
        "channel/CHANNEL_RECORD.json",
    ),
]:
    add(path, arcname)

result_root = run / "results" / f"seed_{seed}" / "result"
if result_root.is_dir():
    for path in sorted(result_root.rglob("*")):
        if path.is_file():
            add(path, f"result/{path.relative_to(result_root).as_posix()}")

# Never place the live token in the return. Include only its SHA-256.
if token.is_file():
    token_hash = __import__("hashlib").sha256(token.read_bytes()).hexdigest()
    token_hash_path = run / "runtime/AUTHORIZATION_TOKEN_SHA256.txt"
    token_hash_path.parent.mkdir(parents=True, exist_ok=True)
    token_hash_path.write_text(token_hash + "\n", encoding="utf-8")
    add(token_hash_path, "authorization/AUTHORIZATION_TOKEN_SHA256.txt")

metadata = {
    "schema_version": 1,
    "mode": mode,
    "job_id": job_id,
    "smoke_seed": int(seed),
    "cluster": "rorqual",
    "excluded_from_phase1_confirmatory_analysis": True,
    "full_campaign_authorized": False,
    "file_count": len(files),
}
metadata_path = run / "runtime/RETURN_METADATA.json"
metadata_path.write_text(
    json.dumps(metadata, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
add(metadata_path, "runtime/RETURN_METADATA.json")

with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
    for path, arcname in files:
        archive.write(path, arcname)
with zipfile.ZipFile(output) as archive:
    bad = archive.testzip()
    if bad is not None:
        raise RuntimeError(f"corrupt return member: {bad}")
print(output)
PY

  (
    cd "$RETURN"
    sha256sum "$zip_name" > "$zip_name.sha256"
    sha256sum -c "$zip_name.sha256"
    unzip -t "$zip_name" >/dev/null
  )
}

remote_failure() {
  code=$?
  trap - ERR
  echo
  echo "REMOTE RORQUAL SMOKE: FAIL"
  echo "Exit code: $code"
  echo "Command: ${BASH_COMMAND:-unknown}"
  echo "Job ID: $JOB_ID"
  {
    echo "status=FAIL"
    echo "exit_code=$code"
    echo "job_id=$JOB_ID"
    echo "smoke_seed=$SMOKE_SEED"
    echo "cluster=rorqual"
    echo "excluded_from_phase1_confirmatory_analysis=true"
    echo "full_campaign_authorized=false"
    date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
  } > "$RETURN/REMOTE_FAILURE_STATUS.txt"
  build_return \
    "FAIL_DIAGNOSTIC" \
    "FR3_PHASE1_RORQUAL_SMOKE_DIAGNOSTIC_${JOB_ID}.zip" || true
  exit "$code"
}
trap remote_failure ERR

cd "$TRANSFER"
[[ "$(sha256sum "$JOB_NAME" | awk '{print $1}')" == "$BASE_JOB_SHA" ]]
sha256sum -c "$TOKEN_SHA_NAME"
unzip -t "$JOB_NAME" >/dev/null
unzip -q "$JOB_NAME" -d "$BASE_PACKAGE"
(
  cd "$BASE_PACKAGE"
  sha256sum -c PACKAGE_MANIFEST.sha256
)
echo "REMOTE IMMUTABLE PACKAGE EXTRACTION/MANIFEST: PASS"

cp -a "$BASE_PACKAGE/." "$SMOKE_PACKAGE/"
cp -p \
  "$SMOKE_PACKAGE/JOB_PACKAGE_CONTRACT.json" \
  "$SMOKE_PACKAGE/BASE_JOB_PACKAGE_CONTRACT.json"
cp -p \
  "$SMOKE_PACKAGE/PACKAGE_MANIFEST.sha256" \
  "$SMOKE_PACKAGE/BASE_PACKAGE_MANIFEST.sha256"

python3 - "$SMOKE_PACKAGE" "$TRANSFER/$TOKEN_NAME" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys

package = Path(sys.argv[1])
token_path = Path(sys.argv[2])
contract_path = package / "JOB_PACKAGE_CONTRACT.json"
base_path = package / "BASE_JOB_PACKAGE_CONTRACT.json"

base = json.loads(base_path.read_text(encoding="utf-8"))
token = json.loads(token_path.read_text(encoding="utf-8"))

assert base["package_id"] == "bd18734787de7396b9de4bf8c0b9ba4d191c6346a7cb83e969499622067a8129"
assert base["candidate_v3"]["zip_sha256"] == "f7b47fd3a07e30987b7f0901df1706d6127774d32284e7d3b0da38185d810161"
assert token["execution_scope"] == "NONCAMPAIGN_RORQUAL_DEPLOYMENT_SMOKE_ONLY"
assert token["cluster"] == "rorqual"
assert token["allowed_seed"] == 43999
assert token["allowed_job_count"] == 1
assert token["full_campaign_authorized"] is False
assert token["base_package_id"] == base["package_id"]
assert token["candidate_zip_sha256"] == base["candidate_v3"]["zip_sha256"]
expires = datetime.fromisoformat(token["expires_utc"].replace("Z", "+00:00"))
assert expires > datetime.now(timezone.utc)

smoke = dict(base)
smoke.update(
    {
        "schema_version": 2,
        "status": "NONCAMPAIGN_RORQUAL_DEPLOYMENT_SMOKE_ONLY",
        "package_id": token["package_id"],
        "base_reviewed_package_id": base["package_id"],
        "campaign_seed_list": [43999],
        "seed_mapping": {
            "campaign_seed_list": [43999],
            "user_seed_rule": "2 * campaign_seed",
            "channel_seed_rule": "2 * campaign_seed + 1",
        },
        "execution_authorized": True,
        "full_campaign_authorized": False,
        "submission_scripts_locked": True,
        "smoke_scope": {
            "cluster": "rorqual",
            "campaign_seed": 43999,
            "user_seed": 87998,
            "channel_seed": 87999,
            "excluded_from_phase1_confirmatory_analysis": True,
            "full_campaign_authorized": False,
            "authorization_token_sha256": hashlib.sha256(
                token_path.read_bytes()
            ).hexdigest(),
            "authorization_expires_utc": token["expires_utc"],
            "rorqual_port_commit": token["rorqual_port_commit"],
        },
        "authorization_contract": {
            "authorization_file_required": True,
            "required_authorization_string": "EXECUTE_PHASE1_NIBI_V1",
            "required_package_id": token["package_id"],
            "token_included": False,
            "scope": "NONCAMPAIGN_RORQUAL_DEPLOYMENT_SMOKE_ONLY",
            "allowed_seed": 43999,
            "allowed_job_count": 1,
        },
        "next_gate": "INDEPENDENTLY_REVIEW_RORQUAL_NONCAMPAIGN_SMOKE_RETURN",
    }
)
contract_path.write_text(
    json.dumps(smoke, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

record = {
    "schema_version": 1,
    "status": "PASS_RORQUAL_SMOKE_WORKSPACE_READY",
    "base_package_id": base["package_id"],
    "rorqual_smoke_package_id": token["package_id"],
    "smoke_seed": 43999,
    "token_sha256": hashlib.sha256(token_path.read_bytes()).hexdigest(),
    "excluded_from_phase1_confirmatory_analysis": True,
    "full_campaign_authorized": False,
}
(package / "SMOKE_WORKSPACE_RECORD.json").write_text(
    json.dumps(record, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

manifest = package / "SMOKE_WORKSPACE_MANIFEST.sha256"
lines = []
for path in sorted(package.rglob("*")):
    if path.is_file() and path != manifest:
        lines.append(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
            f"{path.relative_to(package).as_posix()}"
        )
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("RORQUAL SMOKE WORKSPACE CONTRACT: PASS")
PY

(
  cd "$SMOKE_PACKAGE"
  sha256sum -c SMOKE_WORKSPACE_MANIFEST.sha256
)

# Build or reuse the environment on the Rorqual login node. Rorqual compute
# nodes have no internet access, so this must complete before Slurm execution.
PHASE1_BASE="$ENV_ROOT" \
PHASE1_VENV="$VENV" \
bash "$SMOKE_PACKAGE/setup_environment.sh"

source "$VENV/bin/activate"
python - "$SMOKE_PACKAGE/JOB_PACKAGE_CONTRACT.json" \
  "$TRANSFER/$TOKEN_NAME" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

contract = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
token = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert contract["status"] == "NONCAMPAIGN_RORQUAL_DEPLOYMENT_SMOKE_ONLY"
assert contract["campaign_seed_list"] == [43999]
assert contract["full_campaign_authorized"] is False
assert token["package_id"] == contract["package_id"]
assert token["execution_scope"] == "NONCAMPAIGN_RORQUAL_DEPLOYMENT_SMOKE_ONLY"
assert token["cluster"] == "rorqual"
assert token["allowed_seed"] == 43999
assert datetime.fromisoformat(
    token["expires_utc"].replace("Z", "+00:00")
) > datetime.now(timezone.utc)
print("RORQUAL SMOKE TOKEN/CONTRACT VALIDATION: PASS")
PY

mapfile -t ACCOUNTS < <(
  sacctmgr -nP show assoc \
    user="$USER" cluster=rorqual format=Account 2>/dev/null \
  | cut -d'|' -f1 \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | sed '/^$/d' \
  | sort -u
)
echo "Rorqual account associations:"
printf '  %s\n' "${ACCOUNTS[@]:-<none>}"

ACCOUNT=""
for preferred in def-rsadve_gpu def-rsadve def-rsadve_cpu; do
  for value in "${ACCOUNTS[@]}"; do
    if [[ "$value" == "$preferred" ]]; then
      ACCOUNT="$value"
      break 2
    fi
  done
done
if [[ -z "$ACCOUNT" && "${#ACCOUNTS[@]}" -gt 0 ]]; then
  ACCOUNT="${ACCOUNTS[0]}"
fi
[[ -n "$ACCOUNT" ]] || {
  echo "ERROR: no Rorqual Slurm account could be selected"
  exit 20
}
echo "Selected Rorqual account: $ACCOUNT"

SBATCH="$RUN/rorqual_smoke.sbatch"
cat > "$SBATCH" <<EOF
#!/usr/bin/env bash
#SBATCH --account=$ACCOUNT
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus=h100:1
#SBATCH --cpus-per-task=$CPUS
#SBATCH --mem=${MEMORY_GIB}G
#SBATCH --time=$TIME_LIMIT
#SBATCH --job-name=fr3-p1-rq-smk
#SBATCH --output=$LOGS/smoke-%j.out
#SBATCH --error=$LOGS/smoke-%j.err

set -Eeuo pipefail
module --force purge
module load StdEnv/2023
module load python/3.12.4
source "$VENV/bin/activate"

export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export PHASE1_AUTHORIZATION_FILE="$TRANSFER/$TOKEN_NAME"
export CUDA_CACHE_PATH="$RUN/cache/cuda"
export XDG_CACHE_HOME="$RUN/cache/xdg"
export TMPDIR="$RUN/cache/tmp"
export TORCH_HOME="$RUN/cache/torch"
export TORCH_EXTENSIONS_DIR="$RUN/cache/torch_extensions"
export MPLCONFIGDIR="$RUN/cache/matplotlib"
export OMP_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export MKL_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export OPENBLAS_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"
export NUMEXPR_NUM_THREADS="\${SLURM_CPUS_PER_TASK:-16}"

mkdir -p \
  "$RUN/results" \
  "$RUN/runtime" \
  "$RUN/cache/cuda" \
  "$RUN/cache/xdg" \
  "$RUN/cache/tmp" \
  "$RUN/cache/torch" \
  "$RUN/cache/torch_extensions" \
  "$RUN/cache/matplotlib"

nvidia-smi

python - "$SMOKE_PACKAGE/JOB_PACKAGE_CONTRACT.json" \
  "$TRANSFER/$TOKEN_NAME" "$ENV_ROOT" "$RUN/runtime" <<'PYENV'
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys

import numpy
import pandas
import scipy
import torch

contract_path = Path(sys.argv[1])
token_path = Path(sys.argv[2])
environment_root = Path(sys.argv[3])
runtime = Path(sys.argv[4])
runtime.mkdir(parents=True, exist_ok=True)

freeze = subprocess.run(
    [sys.executable, "-m", "pip", "freeze", "--all"],
    capture_output=True,
    text=True,
    check=True,
)
freeze_path = runtime / "pip_freeze_exact.txt"
freeze_path.write_text(freeze.stdout, encoding="utf-8")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def cmd(command):
    result = subprocess.run(
        command, capture_output=True, text=True, check=False
    )
    return (result.stdout + result.stderr).strip()

contract = json.loads(contract_path.read_text(encoding="utf-8"))
token = json.loads(token_path.read_text(encoding="utf-8"))
packages = {}
for name in [
    "torch", "sionna-no-rt", "numpy", "scipy", "pandas",
    "h5py", "matplotlib", "pyproj", "pip", "setuptools", "wheel",
]:
    try:
        packages[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        packages[name] = "NOT_INSTALLED"

wheels = []
wheel_root = environment_root / "wheels"
if wheel_root.is_dir():
    for path in sorted(wheel_root.glob("*")):
        if path.is_file():
            wheels.append(
                {
                    "name": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": sha(path),
                }
            )

value = {
    "schema_version": 1,
    "status": "PASS_EXACT_RORQUAL_SMOKE_ENVIRONMENT_LOCK",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "cluster": "rorqual",
    "hostname": platform.node(),
    "platform": platform.platform(),
    "python_executable": sys.executable,
    "python_version": sys.version,
    "loaded_modules": os.environ.get("LOADEDMODULES", ""),
    "packages": packages,
    "numpy_version": numpy.__version__,
    "scipy_version": scipy.__version__,
    "pandas_version": pandas.__version__,
    "torch_version": torch.__version__,
    "torch_cuda_build": torch.version.cuda,
    "torch_cuda_available": bool(torch.cuda.is_available()),
    "torch_gpu_name": torch.cuda.get_device_name(0),
    "torch_gpu_total_memory_bytes": int(
        torch.cuda.get_device_properties(0).total_memory
    ),
    "nvidia_smi_query": cmd(
        [
            "nvidia-smi",
            "--query-gpu=name,uuid,driver_version,memory.total",
            "--format=csv,noheader",
        ]
    ),
    "nvidia_smi_full": cmd(["nvidia-smi"]),
    "pip_check": cmd([sys.executable, "-m", "pip", "check"]),
    "pip_freeze_sha256": sha(freeze_path),
    "wheel_records": wheels,
    "job_package_contract_sha256": sha(contract_path),
    "authorization_token_sha256": sha(token_path),
    "rorqual_smoke_package_id": contract["package_id"],
    "base_package_id": contract["base_reviewed_package_id"],
    "candidate_zip_sha256": contract["candidate_v3"]["zip_sha256"],
    "smoke_seed": 43999,
    "excluded_from_phase1_confirmatory_analysis": True,
    "full_campaign_authorized": False,
}
assert value["torch_cuda_available"]
assert "H100" in value["torch_gpu_name"]
assert value["torch_gpu_total_memory_bytes"] >= 75 * 1024**3
assert value["pip_check"] == "No broken requirements found."

output = runtime / "RORQUAL_ENVIRONMENT_LOCK.json"
output.write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
Path(str(output) + ".sha256").write_text(
    f"{sha(output)}  {output.name}\n",
    encoding="utf-8",
)
print("EXACT RORQUAL SOFTWARE/GPU ENVIRONMENT LOCK: PASS")
PYENV

python "$SMOKE_PACKAGE/phase1_seed_worker.py" \
  --seed "$SMOKE_SEED" \
  --output-root "$RUN/results"

python "$SMOKE_PACKAGE/validate_seed_result.py" \
  --result-dir "$RUN/results/seed_${SMOKE_SEED}/result" \
  --package-contract "$SMOKE_PACKAGE/JOB_PACKAGE_CONTRACT.json"

python - "$SMOKE_PACKAGE/JOB_PACKAGE_CONTRACT.json" \
  "$RUN/results/seed_${SMOKE_SEED}/result" \
  "$RUN/results/seed_${SMOKE_SEED}/channel" \
  "$RUN/runtime/RORQUAL_ENVIRONMENT_LOCK.json" \
  "$RUN/runtime/RORQUAL_SMOKE_AUDIT.json" <<'PYAUDIT'
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd

contract_path = Path(sys.argv[1])
result_root = Path(sys.argv[2])
channel_root = Path(sys.argv[3])
environment_path = Path(sys.argv[4])
output = Path(sys.argv[5])

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

contract = json.loads(contract_path.read_text(encoding="utf-8"))
seed = json.loads(
    (result_root / "SEED_RESULT.json").read_text(encoding="utf-8")
)
channel = json.loads(
    (channel_root / "CHANNEL_RECORD.json").read_text(encoding="utf-8")
)
environment = json.loads(environment_path.read_text(encoding="utf-8"))
cells = pd.read_csv(result_root / "CELL_SUMMARY.csv")
paired = pd.read_csv(result_root / "PRIMARY_PAIRED_EFFECTS.csv")

assert contract["status"] == "NONCAMPAIGN_RORQUAL_DEPLOYMENT_SMOKE_ONLY"
assert contract["campaign_seed_list"] == [43999]
assert contract["full_campaign_authorized"] is False
assert seed["campaign_seed"] == 43999
assert seed["package_id"] == contract["package_id"]
assert channel["campaign_seed"] == 43999
assert channel["user_seed"] == 87998
assert channel["channel_seed"] == 87999
assert "H100" in channel["gpu_name"]
assert environment["status"] == "PASS_EXACT_RORQUAL_SMOKE_ENVIRONMENT_LOCK"
assert len(cells) == 40
assert sorted(cells["pass_slot"].unique().tolist()) == list(range(5))
assert cells["method_id"].nunique() == 8
assert len(paired) == 5

predictive = cells.loc[
    cells["method_id"]
    == "robust_predictive_constrained_pf_with_sector_selective_fallback"
]
reactive = cells.loc[
    cells["method_id"]
    == "delayed_myopic_constrained_pf_with_reactive_sector_fallback"
]
assert (predictive["long_violation_seconds"] == 0).all()
assert (predictive["short_violation_seconds"] == 0).all()
assert (
    predictive["eligible_floor_violation_user_seconds"] == 0
).all()
assert (reactive["long_violation_seconds"] == 0).all()
assert (reactive["short_violation_seconds"] == 0).all()

audit = {
    "schema_version": 1,
    "status": "PASS_RORQUAL_NONCAMPAIGN_DEPLOYMENT_SMOKE_REVIEW_REQUIRED",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "cluster": "rorqual",
    "smoke_seed": 43999,
    "user_seed": 87998,
    "channel_seed": 87999,
    "rorqual_smoke_package_id": contract["package_id"],
    "base_package_id": contract["base_reviewed_package_id"],
    "candidate_zip_sha256": contract["candidate_v3"]["zip_sha256"],
    "environment_lock_sha256": sha(environment_path),
    "channel_record_sha256": sha(channel_root / "CHANNEL_RECORD.json"),
    "frequency_response_sha256_array_bytes": channel[
        "frequency_response_sha256_array_bytes"
    ],
    "cell_count": len(cells),
    "pass_count": 5,
    "method_count": 8,
    "predictive_long_violation_seconds": int(
        predictive["long_violation_seconds"].sum()
    ),
    "predictive_short_violation_seconds": int(
        predictive["short_violation_seconds"].sum()
    ),
    "predictive_floor_violation_user_seconds": int(
        predictive["eligible_floor_violation_user_seconds"].sum()
    ),
    "reactive_long_violation_seconds": int(
        reactive["long_violation_seconds"].sum()
    ),
    "mean_predictive_minus_static_final_pf": float(
        paired["predictive_minus_static_final_pf"].mean()
    ),
    "excluded_from_phase1_confirmatory_analysis": True,
    "full_campaign_authorized": False,
    "paper_result": False,
    "next_gate": "INDEPENDENTLY_REVIEW_RORQUAL_NONCAMPAIGN_SMOKE_RETURN",
}
output.write_text(
    json.dumps(audit, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
Path(str(output) + ".sha256").write_text(
    f"{sha(output)}  {output.name}\n",
    encoding="utf-8",
)
print("RORQUAL NONCAMPAIGN SMOKE STRICT VALIDATION: PASS")
print(json.dumps(audit, indent=2))
PYAUDIT

{
  echo "status=PASS"
  echo "job_id=\${SLURM_JOB_ID:-unknown}"
  echo "cluster=rorqual"
  echo "smoke_seed=$SMOKE_SEED"
  echo "excluded_from_phase1_confirmatory_analysis=true"
  echo "full_campaign_authorized=false"
  date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
} > "$RUN/runtime/SMOKE_COMPLETION_MARKER.txt"

echo "RORQUAL NONCAMPAIGN DEPLOYMENT SMOKE WORKER: PASS"
EOF
chmod 700 "$SBATCH"

JOB_ID="$(sbatch --parsable "$SBATCH")"
printf '%s\n' "$JOB_ID" > "$RUN/job_id.txt"
echo "Submitted Rorqual smoke job: $JOB_ID"
echo "Slurm array used: NO"
echo "Requested: 1 full H100, $CPUS CPUs, ${MEMORY_GIB}G RAM"

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
echo "Final Rorqual smoke state: ${STATE:-UNKNOWN}"

if [[ "${STATE:-}" != COMPLETED* ]]; then
  tail -n 320 "$LOGS/smoke-${JOB_ID}.out" || true
  tail -n 320 "$LOGS/smoke-${JOB_ID}.err" || true
  exit 21
fi

build_return \
  "PASS" \
  "FR3_PHASE1_RORQUAL_SMOKE_RETURN_${JOB_ID}.zip"

{
  echo "status=PASS"
  echo "job_id=$JOB_ID"
  echo "slurm_account=$ACCOUNT"
  echo "cluster=rorqual"
  echo "smoke_seed=$SMOKE_SEED"
  echo "return_zip=$RETURN/FR3_PHASE1_RORQUAL_SMOKE_RETURN_${JOB_ID}.zip"
  echo "excluded_from_phase1_confirmatory_analysis=true"
  echo "full_campaign_authorized=false"
  date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
} > "$RETURN/REMOTE_SUCCESS_STATUS.txt"

echo "REMOTE RORQUAL NONCAMPAIGN SMOKE: PASS"
echo "Job ID: $JOB_ID"
echo "Return folder: $RETURN"
REMOTE_SCRIPT
REMOTE_EXIT=$?
set -e

# ---------------------------------------------------------------------------
# Retrieve and freeze local evidence
# ---------------------------------------------------------------------------
echo
echo "=== Retrieve compact Rorqual return or diagnostics ==="
scp "${SCP_OPTS[@]}" -r \
  "${RORQUAL_HOST}:${REMOTE_RETURN}/." \
  "$LOCAL_RETURN/"

echo "Retrieved files:"
find "$LOCAL_RETURN" -maxdepth 2 -type f \
  -printf '%p | %s bytes\n' | sort

SUCCESS_STATUS="$LOCAL_RETURN/REMOTE_SUCCESS_STATUS.txt"
FAILURE_STATUS="$LOCAL_RETURN/REMOTE_FAILURE_STATUS.txt"
if [[ -f "$SUCCESS_STATUS" && -f "$FAILURE_STATUS" ]]; then
  echo "ERROR: both success and failure statuses were retrieved"
  exit 30
fi
if [[ ! -f "$SUCCESS_STATUS" && ! -f "$FAILURE_STATUS" ]]; then
  echo "ERROR: neither success nor failure status was retrieved"
  exit 31
fi

mapfile -t RETURN_ZIPS < <(
  find "$LOCAL_RETURN" -maxdepth 1 -type f -name '*.zip' -print | sort
)
[[ "${#RETURN_ZIPS[@]}" -eq 1 ]] || {
  echo "ERROR: expected exactly one compact return/diagnostic ZIP"
  printf '  %s\n' "${RETURN_ZIPS[@]:-<none>}"
  exit 32
}
RETURN_ZIP="${RETURN_ZIPS[0]}"
RETURN_SHA="${RETURN_ZIP}.sha256"
[[ -f "$RETURN_SHA" ]] || {
  echo "ERROR: return ZIP checksum file is missing"
  exit 33
}
(
  cd "$LOCAL_RETURN"
  sha256sum -c "$(basename "$RETURN_SHA")"
  unzip -t "$(basename "$RETURN_ZIP")" >/dev/null
)
RETURN_DIGEST="$(sha256sum "$RETURN_ZIP" | awk '{print $1}')"

EVIDENCE_REL="evidence/phase1_rorqual_noncampaign_smoke_v1"
EVIDENCE="$ROOT/$EVIDENCE_REL"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"
cp -p \
  "$RETURN_ZIP" \
  "$RETURN_SHA" \
  "$LOCAL_LOG" \
  "$EVIDENCE/"
if [[ -f "$SUCCESS_STATUS" ]]; then
  cp -p "$SUCCESS_STATUS" "$EVIDENCE/"
  COLLECTION_STATUS="PASS_RORQUAL_SMOKE_EXECUTED_REVIEW_REQUIRED"
  COMMIT_MESSAGE="Collect excluded Rorqual phase1 deployment smoke"
else
  cp -p "$FAILURE_STATUS" "$EVIDENCE/"
  COLLECTION_STATUS="FAIL_RORQUAL_SMOKE_DIAGNOSTIC_REVIEW_REQUIRED"
  COMMIT_MESSAGE="Collect failed Rorqual phase1 smoke diagnostics"
fi

python3 - "$EVIDENCE" "$COLLECTION_STATUS" "$RETURN_DIGEST" \
  "$SMOKE_PACKAGE_ID" "$PORT_COMMIT" "$REMOTE_EXIT" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys

evidence = Path(sys.argv[1])
status = sys.argv[2]
return_sha = sys.argv[3]
package_id = sys.argv[4]
port_commit = sys.argv[5]
remote_exit = int(sys.argv[6])

value = {
    "schema_version": 1,
    "status": status,
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "cluster": "rorqual",
    "smoke_seed": 43999,
    "user_seed": 87998,
    "channel_seed": 87999,
    "rorqual_smoke_package_id": package_id,
    "rorqual_port_commit": port_commit,
    "return_zip_sha256": return_sha,
    "remote_exit_code": remote_exit,
    "excluded_from_phase1_confirmatory_analysis": True,
    "full_campaign_authorized": False,
    "next_gate": (
        "INDEPENDENTLY_REVIEW_RORQUAL_NONCAMPAIGN_SMOKE_RETURN"
        if status.startswith("PASS_")
        else "DIAGNOSE_RORQUAL_NONCAMPAIGN_SMOKE_FAILURE"
    ),
}
(evidence / "RORQUAL_SMOKE_COLLECTION_STATUS.json").write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n",
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

git add -- "$EVIDENCE_REL"
git diff --cached --check
git commit -m "$COMMIT_MESSAGE"
git push
FINAL_COMMIT="$(git rev-parse HEAD)"
REMOTE_FINAL="$(
  git ls-remote --heads origin e3-first-sector-p452 \
    | awk '{print $1}'
)"
[[ "$REMOTE_FINAL" == "$FINAL_COMMIT" ]] || {
  echo "ERROR: remote branch does not equal Rorqual evidence commit"
  exit 34
}

# The live token must not be retained after collection.
rm -f "$TOKEN" "$TOKEN_SHA"

echo
echo "================================================================="
if [[ -f "$SUCCESS_STATUS" && "$REMOTE_EXIT" -eq 0 ]]; then
  echo "FR3 RORQUAL NONCAMPAIGN SMOKE: PASS"
else
  echo "FR3 RORQUAL NONCAMPAIGN SMOKE: DIAGNOSTIC RETURN COLLECTED"
fi
echo "Rorqual job ID: $(
  sed -n 's/^job_id=//p' \
    "$SUCCESS_STATUS" "$FAILURE_STATUS" 2>/dev/null | head -n1
)"
echo "Remote exit: $REMOTE_EXIT"
echo "Evidence commit: $FINAL_COMMIT"
echo "Return ZIP: $RETURN_ZIP"
echo "Return ZIP SHA-256: $RETURN_DIGEST"
echo "Actual host memory will be recorded in Slurm MaxRSS."
echo "Smoke seed: $SMOKE_SEED"
echo "Excluded from confirmatory analysis: YES"
echo "Full campaign authorization: NO"
echo "Next gate: INDEPENDENTLY_REVIEW_RORQUAL_NONCAMPAIGN_SMOKE_RETURN"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
fi

if [[ "$REMOTE_EXIT" -ne 0 ]]; then
  exit "$REMOTE_EXIT"
fi
