#!/usr/bin/env bash
# One-shot local WSL orchestrator for the excluded candidate-v4.3 H100 smoke.
set -Eeuo pipefail

PACKAGE_ROOT="${1:?usage: $0 PACKAGE_ROOT}"
PACKAGE_ROOT="$(realpath -e "$PACKAGE_ROOT")"
REPO="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
DOWNLOADS="${FR3_DOWNLOADS:-/mnt/c/Users/alifa/Downloads}"
BRANCH="e3-first-sector-p452"
REPOSITORY="afazeliUofT/FR3_CBF_Completion_Package_v1_1"
EXPECTED_ANCESTOR="${FR3_EXPECTED_ANCESTOR:-b65dc117f1ace492b55bd764f74bf985fbcb9507}"
EXPECTED_CHANNEL_RECORD_SHA256="bf55f7a071bc00fdc9e73075bcf2b3f9da3bd07843e3795e134d4bdb3c4fa0d9"
EXPECTED_FREQUENCY_ARRAY_SHA256="c4ac7fb56da5d3f8182836e2a99ab2ef1dd7b17bf76332abbc198d1ae6b6a093"
RORQUAL_HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
RORQUAL_SCRATCH_LINK="/home/rsadve1/links/scratch"
PRESERVED_BASE="/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_SMOKE_5037b4e33448_20260801_031008"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_RETURN="$DOWNLOADS/FR3_CANDIDATE_V4_3_H100_DEPLOYMENT_SMOKE_RETURN_$STAMP"
LOCAL_LOG="$LOCAL_RETURN/LOCAL_WSL_ORCHESTRATOR.log"
REMOTE_RETURN_LOCAL="$LOCAL_RETURN/remote_return"
GIT_WORK="$LOCAL_RETURN/github_working_clone"
mkdir -p "$LOCAL_RETURN" "$REMOTE_RETURN_LOCAL"
exec > >(tee "$LOCAL_LOG") 2>&1

CONTROL_PATH="/tmp/fr3_v43_h100_${UID}_$$_%C"
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
REMOTE_WRAPPER_EXIT_CODE=99
DIAGNOSTIC_RETRIEVAL_EXIT_CODE=99
SOURCE_COMMIT="NOT_COMMITTED"
FINAL_COMMIT="NOT_COMMITTED"
REMOTE_FINAL_COMMIT="UNKNOWN"
REMOTE_RUN_ROOT="UNKNOWN"
LOCAL_RETURN_ZIP="NONE"
LOCAL_RETURN_ZIP_SHA256="NONE"

close_control() {
    ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true
}

make_local_failure() {
    local code="$1"
    local out="$LOCAL_RETURN/FR3_LOCAL_CANDIDATE_V4_3_H100_SMOKE_FAILURE_${STAMP}.zip"
    python3 - "$PACKAGE_ROOT" "$LOCAL_RETURN" "$out" "$code" <<'PY'
from pathlib import Path
import json,sys,zipfile,hashlib
package=Path(sys.argv[1]); local=Path(sys.argv[2]); out=Path(sys.argv[3]); code=int(sys.argv[4])
meta=local/'LOCAL_FAILURE_METADATA.json'
meta.write_text(json.dumps({
 'schema_version':1,
 'status':'LOCAL_ORCHESTRATION_FAILURE',
 'exit_code':code,
 'confirmatory_campaign_authorized':False,
},indent=2,sort_keys=True)+'\n',encoding='utf-8')
files=[]
for path,arc in [
 (local/'LOCAL_WSL_ORCHESTRATOR.log','LOCAL_WSL_ORCHESTRATOR.log'),
 (local/'INDEPENDENT_V4_3_REVIEW.json','INDEPENDENT_V4_3_REVIEW.json'),
 (local/'INDEPENDENT_V4_3_REVIEW.env','INDEPENDENT_V4_3_REVIEW.env'),
 (meta,'LOCAL_FAILURE_METADATA.json'),
 (package/'PACKAGE_VERSION.json','PACKAGE_VERSION.json'),
 (package/'config/H100_DEPLOYMENT_SMOKE_CONTRACT.json','H100_DEPLOYMENT_SMOKE_CONTRACT.json'),
]:
 if path.is_file(): files.append((path,arc))
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for path,arc in files: z.write(path,arc)
with zipfile.ZipFile(out) as z:
 bad=z.testzip()
 if bad: raise RuntimeError(bad)
digest=hashlib.sha256(out.read_bytes()).hexdigest()
(out.with_suffix(out.suffix+'.sha256')).write_text(f'{digest}  {out.name}\n',encoding='utf-8')
print(f'LOCAL_FAILURE_ZIP={out}')
print(f'LOCAL_FAILURE_ZIP_SHA256={digest}')
PY
}

on_exit() {
    local code=$?
    trap - EXIT ERR
    close_control
    if (( code != 0 )) && [[ "$LOCAL_RETURN_ZIP" == "NONE" ]]; then
        make_local_failure "$code" || true
    fi
    printf '%s\n' \
        "LOCAL_WRAPPER_EXIT_CODE=$code" \
        "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE" \
        "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" \
        "CANDIDATE_SOURCE_COMMIT=$SOURCE_COMMIT" \
        "GIT_FINAL_COMMIT=$FINAL_COMMIT" \
        "GIT_REMOTE_FINAL_COMMIT=$REMOTE_FINAL_COMMIT" \
        "LOCAL_RETURN_ZIP=$LOCAL_RETURN_ZIP" \
        "LOCAL_RETURN_ZIP_SHA256=$LOCAL_RETURN_ZIP_SHA256" \
        "REMOTE_RUN_ROOT=$REMOTE_RUN_ROOT" \
        "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN" \
        "CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO"
    if command -v explorer.exe >/dev/null 2>&1; then
        explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
    fi
    exit "$code"
}
trap on_exit EXIT
trap 'exit $?' ERR

printf '%s\n' \
    "=================================================================" \
    "FR3 CANDIDATE V4.3 — INDEPENDENT REVIEW AND H100 SMOKE" \
    "=================================================================" \
    "PACKAGE_ROOT=$PACKAGE_ROOT" \
    "REPO=$REPO" \
    "LOCAL_RETURN=$LOCAL_RETURN" \
    "RORQUAL_REQUIRED=YES_H100" \
    "H100_REQUESTED=YES_ONE_FULL_H100" \
    "H100_CHANNEL_REGENERATION=NO" \
    "PRESERVED_SEED43999_CHANNEL_REUSED=YES" \
    "CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO"

for command in python3 sha256sum unzip git ssh scp tar bash realpath; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "ERROR_MISSING_COMMAND=$command"
        exit 90
    }
done
[[ -d "$REPO/.git" ]] || {
    echo "ERROR_REPOSITORY_NOT_FOUND=$REPO"
    exit 91
}
[[ -x "$REPO/.venv/bin/python" ]] || {
    echo "REPO_VENV_CREATE_REQUIRED=YES"
    python3 -m venv "$REPO/.venv"
}
PYTHON="$REPO/.venv/bin/python"
PIP="$REPO/.venv/bin/pip"
if ! "$PYTHON" - <<'PY' >/dev/null 2>&1
import numpy,pandas,scipy,pytest
PY
then
    echo "REPO_VENV_DEPENDENCY_REPAIR_REQUIRED=YES"
    "$PIP" install -r "$PACKAGE_ROOT/requirements.txt"
else
    echo "REPO_VENV_REUSE=PASS"
fi

(
    cd "$PACKAGE_ROOT"
    sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
    sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo "INTERNAL_MANIFEST_VERIFICATION=PASS"
echo "SOURCE_PAYLOAD_MANIFEST_VERIFICATION=PASS"

"$PYTHON" - "$PACKAGE_ROOT" <<'PY'
from pathlib import Path
import ast,sys
root=Path(sys.argv[1])
files=sorted(root.rglob('*.py'))
for path in files:
 ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
print('PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS')
print(f'PYTHON_SYNTAX_FILE_COUNT={len(files)}')
PY
while IFS= read -r script; do bash -n "$script"; done < <(
    find "$PACKAGE_ROOT" -type f -name '*.sh' -print | sort
)
echo "BASH_SYNTAX_CHECK=PASS"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$LOCAL_RETURN/pycache"
PYTHONPATH="$PACKAGE_ROOT/candidate_v4_3_package/src" \
    "$PYTHON" -m pytest -q -p no:cacheprovider \
    "$PACKAGE_ROOT/candidate_v4_3_package/tests" \
    "$PACKAGE_ROOT/tests"

"$PYTHON" "$PACKAGE_ROOT/scripts/independent_review_v4_3.py" \
    --evidence-root "$PACKAGE_ROOT/immutable_bindings/v4_3_cpu_return" \
    --binding "$PACKAGE_ROOT/immutable_bindings/V4_3_RETURN_BINDING.json" \
    --output-json "$LOCAL_RETURN/INDEPENDENT_V4_3_REVIEW.json" \
    --output-env "$LOCAL_RETURN/INDEPENDENT_V4_3_REVIEW.env"
cmp -s "$LOCAL_RETURN/INDEPENDENT_V4_3_REVIEW.json" \
    "$PACKAGE_ROOT/local_diagnostics/INDEPENDENT_V4_3_REVIEW.json" || {
    echo "PACKAGED_INDEPENDENT_REVIEW_REPRODUCTION=FAIL_JSON"
    exit 99
}
cmp -s "$LOCAL_RETURN/INDEPENDENT_V4_3_REVIEW.env" \
    "$PACKAGE_ROOT/local_diagnostics/INDEPENDENT_V4_3_REVIEW.env" || {
    echo "PACKAGED_INDEPENDENT_REVIEW_REPRODUCTION=FAIL_ENV"
    exit 99
}
echo "PACKAGED_INDEPENDENT_REVIEW_REPRODUCTION=PASS"
echo "LOCAL_QUALITY_GATE=PASS"

# Isolated Git clone protects the user's working tree and newer remote work.
ORIGIN="$(git -C "$REPO" remote get-url origin)"
git -C "$REPO" fetch origin "$BRANCH"
LOCAL_REPO_HEAD="$(git -C "$REPO" rev-parse HEAD)"
REMOTE_HEAD_BEFORE="$(git -C "$REPO" rev-parse "origin/$BRANCH")"
rm -rf "$GIT_WORK"
git clone --branch "$BRANCH" --single-branch "$ORIGIN" "$GIT_WORK"
git -C "$GIT_WORK" fetch origin "$BRANCH"
git -C "$GIT_WORK" reset --hard "origin/$BRANCH"
if [[ -z "$(git -C "$GIT_WORK" config user.name || true)" ]]; then
    git -C "$GIT_WORK" config user.name "Ali Fazeli"
fi
if [[ -z "$(git -C "$GIT_WORK" config user.email || true)" ]]; then
    git -C "$GIT_WORK" config user.email "ali.fazeli@utoronto.ca"
fi
GIT_HEAD_BEFORE="$(git -C "$GIT_WORK" rev-parse HEAD)"
git -C "$GIT_WORK" merge-base --is-ancestor "$EXPECTED_ANCESTOR" HEAD || {
    echo "ERROR_EXPECTED_V4_3_SOURCE_COMMIT_NOT_ANCESTOR=$EXPECTED_ANCESTOR"
    exit 92
}
printf '%s\n' \
    "LOCAL_REPOSITORY_HEAD=$LOCAL_REPO_HEAD" \
    "GIT_HEAD_BEFORE=$GIT_HEAD_BEFORE" \
    "GIT_REMOTE_HEAD_BEFORE=$REMOTE_HEAD_BEFORE" \
    "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

TOOL_REL="tools/candidate_v4_3_h100_deployment_smoke_v1"
TOOL_DEST="$GIT_WORK/$TOOL_REL"
if [[ -e "$TOOL_DEST" ]]; then
    if [[ -f "$TOOL_DEST/SOURCE_PAYLOAD_MANIFEST.sha256" ]] \
        && cmp -s "$PACKAGE_ROOT/SOURCE_PAYLOAD_MANIFEST.sha256" \
            "$TOOL_DEST/SOURCE_PAYLOAD_MANIFEST.sha256" \
        && (cd "$TOOL_DEST"; sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null)
    then
        echo "EXISTING_IDENTICAL_H100_SMOKE_SOURCE_REUSED=YES"
    else
        echo "ERROR_EXISTING_H100_SMOKE_SOURCE_PATH_DIFFERS=$TOOL_REL"
        exit 93
    fi
else
    mkdir -p "$TOOL_DEST"
    for item in \
        PACKAGE_VERSION.json SOURCE_PAYLOAD_MANIFEST.sha256 README.md requirements.txt \
        config docs scripts tests wrappers local_diagnostics cluster_diagnostics \
        immutable_bindings/V4_3_RETURN_BINDING.json \
        candidate_v4_3_package/PACKAGE_VERSION.json \
        candidate_v4_3_package/SOURCE_PAYLOAD_MANIFEST.sha256 \
        candidate_v4_3_package/README.md \
        candidate_v4_3_package/requirements.txt \
        candidate_v4_3_package/config \
        candidate_v4_3_package/docs \
        candidate_v4_3_package/scripts \
        candidate_v4_3_package/src \
        candidate_v4_3_package/tests \
        candidate_v4_3_package/wrappers \
        candidate_v4_3_package/immutable_bindings/IMMUTABLE_INPUT_BINDINGS.json
    do
        if [[ -e "$PACKAGE_ROOT/$item" ]]; then
            mkdir -p "$TOOL_DEST/$(dirname "$item")"
            cp -a "$PACKAGE_ROOT/$item" "$TOOL_DEST/$item"
        fi
    done
    find "$TOOL_DEST" -type d \( -name __pycache__ -o -name .pytest_cache \) \
        -prune -exec rm -rf {} +
    find "$TOOL_DEST" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
    (cd "$TOOL_DEST"; sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null)
    "$PYTHON" - "$TOOL_DEST" <<'PY'
from pathlib import Path
import hashlib,sys
root=Path(sys.argv[1]); out=root/'GITHUB_TOOL_MANIFEST.sha256'; lines=[]
for path in sorted(root.rglob('*')):
    if path.is_file() and path != out:
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}")
out.write_text('\n'.join(lines)+'\n',encoding='utf-8')
PY
fi

git -C "$GIT_WORK" add -- "$TOOL_REL"
if ! git -C "$GIT_WORK" diff --cached --quiet; then
    git -C "$GIT_WORK" diff --cached --check
    git -C "$GIT_WORK" commit -m \
        "Add candidate-v4.3 excluded H100 deployment smoke"
    git -C "$GIT_WORK" fetch origin "$BRANCH"
    CURRENT_REMOTE="$(git -C "$GIT_WORK" rev-parse "origin/$BRANCH")"
    if [[ "$CURRENT_REMOTE" != "$GIT_HEAD_BEFORE" ]]; then
        echo "REMOTE_BRANCH_ADVANCED_BEFORE_SOURCE_PUSH=YES"
        git -C "$GIT_WORK" rebase "origin/$BRANCH"
    fi
    git -C "$GIT_WORK" push origin "HEAD:$BRANCH"
fi
PUSHED_HEAD="$(git -C "$GIT_WORK" rev-parse HEAD)"
REMOTE_SOURCE_HEAD="$(git -C "$GIT_WORK" ls-remote --heads origin "$BRANCH" | awk '{print $1}')"
[[ "$PUSHED_HEAD" == "$REMOTE_SOURCE_HEAD" ]] || {
    echo "ERROR_SOURCE_PUSH_REMOTE_MISMATCH=$REMOTE_SOURCE_HEAD"
    exit 94
}
SOURCE_COMMIT="$(git -C "$GIT_WORK" log -n1 --format=%H -- "$TOOL_REL")"
[[ -n "$SOURCE_COMMIT" ]] || {
    echo "ERROR_H100_SMOKE_SOURCE_COMMIT_NOT_FOUND=$TOOL_REL"
    exit 94
}
printf '%s\n' \
    "CANDIDATE_SOURCE_COMMIT=$SOURCE_COMMIT" \
    "GIT_REMOTE_HEAD_AFTER_SOURCE=$REMOTE_SOURCE_HEAD"

# Build one exact payload from the validated package.
PAYLOAD_TAR="$LOCAL_RETURN/FR3_V43_H100_SMOKE_PAYLOAD.tar.gz"
tar --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc' \
    --exclude='*.pyo' -C "$PACKAGE_ROOT" -czf "$PAYLOAD_TAR" .
PAYLOAD_SHA256="$(sha256sum "$PAYLOAD_TAR" | awk '{print $1}')"
printf '%s  %s\n' "$PAYLOAD_SHA256" "$(basename "$PAYLOAD_TAR")" \
    > "$PAYLOAD_TAR.sha256"
echo "REMOTE_PAYLOAD_SHA256=$PAYLOAD_SHA256"

REMOTE_INFO="$(
    ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
        "RORQUAL_SCRATCH_LINK='$RORQUAL_SCRATCH_LINK' bash -s" <<'REMOTE'
set -Eeuo pipefail
host="$(hostname -f 2>/dev/null || hostname)"
[[ "$host" == *rorqual* ]] || { echo "ERROR_NOT_RORQUAL=$host" >&2; exit 10; }
scratch="$(readlink -f "$RORQUAL_SCRATCH_LINK")"
[[ -d "$scratch" ]] || { echo "ERROR_SCRATCH_MISSING=$scratch" >&2; exit 11; }
printf '__HOST__=%s\n' "$host"
printf '__SCRATCH__=%s\n' "$scratch"
REMOTE
)"
REMOTE_HOST="$(printf '%s\n' "$REMOTE_INFO" | sed -n 's/^__HOST__=//p' | tail -n1)"
REMOTE_SCRATCH="$(printf '%s\n' "$REMOTE_INFO" | sed -n 's/^__SCRATCH__=//p' | tail -n1)"
[[ -n "$REMOTE_HOST" && -n "$REMOTE_SCRATCH" ]] || {
    echo "ERROR_REMOTE_PREFLIGHT_PARSE"
    exit 94
}
REMOTE_RUN_ROOT="$REMOTE_SCRATCH/FR3_CANDIDATE_V4_3_H100_SMOKE_${SOURCE_COMMIT:0:12}_$STAMP"
ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
    "rm -rf '$REMOTE_RUN_ROOT' && mkdir -p '$REMOTE_RUN_ROOT/payload' '$REMOTE_RUN_ROOT/return'"
scp "${SCP_OPTS[@]}" "$PAYLOAD_TAR" "$PAYLOAD_TAR.sha256" \
    "$RORQUAL_HOST:$REMOTE_RUN_ROOT/"

# Expected nonzero is captured in the if-condition so diagnostic retrieval runs.
if ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
    "REMOTE_RUN_ROOT='$REMOTE_RUN_ROOT' REMOTE_BASE='$PRESERVED_BASE' SOURCE_COMMIT='$SOURCE_COMMIT' EXPECTED_CHANNEL_RECORD_SHA256='$EXPECTED_CHANNEL_RECORD_SHA256' EXPECTED_FREQUENCY_ARRAY_SHA256='$EXPECTED_FREQUENCY_ARRAY_SHA256' PAYLOAD_TAR_NAME='$(basename "$PAYLOAD_TAR")' bash -s" <<'REMOTE_RUN'
set -Eeuo pipefail
cd "$REMOTE_RUN_ROOT"
sha256sum -c "${PAYLOAD_TAR_NAME}.sha256" >/dev/null
tar -xzf "$PAYLOAD_TAR_NAME" -C payload
bash payload/wrappers/REMOTE_ORCHESTRATE_V4_3_H100_DEPLOYMENT_SMOKE.sh
REMOTE_RUN
then
    REMOTE_WRAPPER_EXIT_CODE=0
else
    REMOTE_WRAPPER_EXIT_CODE=$?
fi
echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE"

# Retrieve success or failure return unconditionally.
if scp "${SCP_OPTS[@]}" \
    "$RORQUAL_HOST:$REMOTE_RUN_ROOT/return/*" "$REMOTE_RETURN_LOCAL/"
then
    DIAGNOSTIC_RETRIEVAL_EXIT_CODE=0
else
    DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$?
fi
echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE"
[[ "$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" == 0 ]] || exit "$DIAGNOSTIC_RETRIEVAL_EXIT_CODE"

LOCAL_RETURN_ZIP="$(find "$REMOTE_RETURN_LOCAL" -maxdepth 1 -type f -name '*.zip' \
    -printf '%T@ %p\n' | sort -n | tail -n1 | cut -d' ' -f2-)"
[[ -n "$LOCAL_RETURN_ZIP" && -f "$LOCAL_RETURN_ZIP" ]] || {
    echo "ERROR_NO_REMOTE_RETURN_ZIP"
    exit 95
}
SIDE="$LOCAL_RETURN_ZIP.sha256"
[[ -f "$SIDE" ]] || {
    echo "ERROR_RETURN_SIDECAR_MISSING=$SIDE"
    exit 96
}
LISTED_NAME="$(awk 'NF>=2 {print $2; exit}' "$SIDE")"
[[ "$LISTED_NAME" == "$(basename "$LOCAL_RETURN_ZIP")" ]] || {
    echo "ERROR_RETURN_SIDECAR_NOT_BASENAME_ONLY=$LISTED_NAME"
    exit 97
}
(
    cd "$(dirname "$LOCAL_RETURN_ZIP")"
    sha256sum -c "$(basename "$SIDE")" >/dev/null
)
unzip -t "$LOCAL_RETURN_ZIP" >/dev/null
LOCAL_RETURN_ZIP_SHA256="$(sha256sum "$LOCAL_RETURN_ZIP" | awk '{print $1}')"
echo "LOCAL_RETURN_ZIP_SHA256=$LOCAL_RETURN_ZIP_SHA256"

RETURN_EXTRACT="$LOCAL_RETURN/return_extracted"
rm -rf "$RETURN_EXTRACT"
mkdir -p "$RETURN_EXTRACT"
unzip -q "$LOCAL_RETURN_ZIP" -d "$RETURN_EXTRACT"
(
    cd "$RETURN_EXTRACT"
    sha256sum -c RETURN_CONTENT_MANIFEST.sha256 >/dev/null
)
echo "RETURN_CONTENT_MANIFEST_VERIFICATION=PASS"

# Push compact review evidence without force and without replacing newer work.
JOB_ID_VALUE="$(awk -F= '$1=="SLURM_JOB_ID" {print $2; exit}' \
    "$RETURN_EXTRACT/runtime/REMOTE_RUN_SUMMARY.env" 2>/dev/null || true)"
[[ -n "$JOB_ID_VALUE" ]] || JOB_ID_VALUE="UNKNOWN_${STAMP}"
EVIDENCE_REL="evidence/phase1_candidate_v4_3_h100_deployment_smoke_v1_job_${JOB_ID_VALUE}"
EVIDENCE_DEST="$GIT_WORK/$EVIDENCE_REL"
[[ ! -e "$EVIDENCE_DEST" ]] || {
    echo "ERROR_EXISTING_H100_SMOKE_EVIDENCE_PATH=$EVIDENCE_REL"
    exit 99
}
mkdir -p "$EVIDENCE_DEST"
cp -a "$RETURN_EXTRACT"/. "$EVIDENCE_DEST/"
cp "$LOCAL_LOG" "$EVIDENCE_DEST/LOCAL_WSL_ORCHESTRATOR.log"
cp "$SIDE" "$EVIDENCE_DEST/$(basename "$SIDE")"
python3 - "$EVIDENCE_DEST" "$REMOTE_WRAPPER_EXIT_CODE" \
    "$LOCAL_RETURN_ZIP_SHA256" <<'PY'
from pathlib import Path
import json,sys,hashlib
root=Path(sys.argv[1]); rc=int(sys.argv[2]); digest=sys.argv[3]
status='COLLECTED_FOR_INDEPENDENT_REVIEW'
science='UNKNOWN'
env=root/'runtime/H100_DEPLOYMENT_SMOKE_STATUS.env'
if env.is_file():
 for line in env.read_text().splitlines():
  if line.startswith('H100_DEPLOYMENT_SMOKE_STATUS='):
   science=line.split('=',1)[1]
value={
 'schema_version':1,
 'candidate_version':'v4.3',
 'status':status,
 'scientific_status':science,
 'remote_wrapper_exit_code':rc,
 'return_zip_sha256':digest,
 'confirmatory_campaign_authorized':False,
 'next_gate':(
   'FREEZE_V4_3_AND_INDEPENDENTLY_REVIEW_CAMPAIGN_READINESS'
   if rc==0 else 'REVIEW_EXCLUDED_H100_SMOKE_DIAGNOSTIC'
 ),
}
(root/'COLLECTION_STATUS.json').write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
lines=[]
for path in sorted(root.rglob('*')):
 if path.is_file() and path.name!='EVIDENCE_MANIFEST.sha256':
  h=hashlib.sha256(path.read_bytes()).hexdigest()
  lines.append(f'{h}  {path.relative_to(root).as_posix()}')
(root/'EVIDENCE_MANIFEST.sha256').write_text('\n'.join(lines)+'\n')
PY

git -C "$GIT_WORK" add -- "$EVIDENCE_REL"
if ! git -C "$GIT_WORK" diff --cached --quiet; then
    git -C "$GIT_WORK" diff --cached --check
    git -C "$GIT_WORK" commit -m \
        "Collect candidate-v4.3 excluded H100 deployment-smoke evidence"
    git -C "$GIT_WORK" fetch origin "$BRANCH"
    REMOTE_BEFORE_EVIDENCE="$(git -C "$GIT_WORK" rev-parse "origin/$BRANCH")"
    PARENT="$(git -C "$GIT_WORK" rev-parse HEAD^)"
    if [[ "$REMOTE_BEFORE_EVIDENCE" != "$PARENT" ]]; then
        echo "REMOTE_BRANCH_ADVANCED_BEFORE_EVIDENCE_PUSH=YES"
        git -C "$GIT_WORK" rebase "origin/$BRANCH"
    fi
    git -C "$GIT_WORK" push origin "HEAD:$BRANCH"
fi
FINAL_COMMIT="$(git -C "$GIT_WORK" rev-parse HEAD)"
REMOTE_FINAL_COMMIT="$(git -C "$GIT_WORK" ls-remote --heads origin "$BRANCH" | awk '{print $1}')"
[[ "$FINAL_COMMIT" == "$REMOTE_FINAL_COMMIT" ]] || {
    echo "ERROR_EVIDENCE_PUSH_REMOTE_MISMATCH=$REMOTE_FINAL_COMMIT"
    exit 98
}

# Print scientific and Slurm values from the returned evidence.
for file in \
    "$RETURN_EXTRACT/runtime/REMOTE_RUN_SUMMARY.env" \
    "$RETURN_EXTRACT/runtime/H100_DEPLOYMENT_SMOKE_STATUS.env" \
    "$RETURN_EXTRACT/summary/RUN_STATUS.env"
do
    [[ -f "$file" ]] && cat "$file"
done
printf '%s\n' \
    "LOCAL_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE" \
    "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE" \
    "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" \
    "REMOTE_PAYLOAD_SHA256=$PAYLOAD_SHA256" \
    "LOCAL_RETURN_ZIP=$LOCAL_RETURN_ZIP" \
    "LOCAL_RETURN_ZIP_SHA256=$LOCAL_RETURN_ZIP_SHA256" \
    "CANDIDATE_SOURCE_COMMIT=$SOURCE_COMMIT" \
    "GIT_FINAL_COMMIT=$FINAL_COMMIT" \
    "GIT_REMOTE_FINAL_COMMIT=$REMOTE_FINAL_COMMIT" \
    "CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO" \
    "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
exit "$REMOTE_WRAPPER_EXIT_CODE"
