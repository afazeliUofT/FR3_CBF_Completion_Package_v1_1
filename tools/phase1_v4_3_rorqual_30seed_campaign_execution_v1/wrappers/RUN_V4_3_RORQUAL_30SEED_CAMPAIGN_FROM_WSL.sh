#!/usr/bin/env bash
set -Eeuo pipefail

: "${1:?package root is required}"
PACKAGE_ROOT="$(realpath "$1")"
REPO="${FR3_REPO_ROOT:?FR3_REPO_ROOT is required}"
DOWNLOADS="${FR3_DOWNLOADS:-/mnt/c/Users/alifa/Downloads}"
RORQUAL_HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
RORQUAL_SCRATCH_LINK="${FR3_RORQUAL_SCRATCH_LINK:-/home/rsadve1/links/scratch}"
ARCHIVE="${FR3_EXECUTION_ARCHIVE_PATH:?FR3_EXECUTION_ARCHIVE_PATH is required}"
ARCHIVE_SHA256="${FR3_EXECUTION_ARCHIVE_SHA256:?FR3_EXECUTION_ARCHIVE_SHA256 is required}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
RUN_ROOT="$HOME/fr3_v4_3_rorqual_30seed_campaign_runs/$STAMP"
LOCAL_RETURN="$DOWNLOADS/FR3_V4_3_RORQUAL_30SEED_CAMPAIGN_RETURN_$STAMP"
LOG="$LOCAL_RETURN/LOCAL_WSL_ORCHESTRATOR.log"
mkdir -p "$RUN_ROOT" "$LOCAL_RETURN"
touch "$LOG"

exec > >(tee -a "$LOG") 2>&1

failure_bundle() {
  local rc=$1 stage=$2
  "$PACKAGE_ROOT/scripts/package_local_failure.py" \
    --output-dir "$LOCAL_RETURN" \
    --log "$LOG" \
    --stage "$stage" \
    --exit-code "$rc" || true
}

unexpected_error() {
  local rc=$?
  trap - ERR
  echo "LOCAL_WRAPPER_STATUS=UNEXPECTED_FAILURE"
  echo "LOCAL_WRAPPER_EXIT_CODE=$rc"
  echo "LOCAL_FAILURE_COMMAND=${BASH_COMMAND:-unknown}"
  echo "CAMPAIGN_EXECUTION_AUTHORIZED=YES_BUT_RESULT_UNKNOWN"
  echo "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
  failure_bundle "$rc" "UNEXPECTED_LOCAL_WRAPPER_FAILURE"
  if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap unexpected_error ERR

printf '%s\n' \
  "=================================================================" \
  "FR3 V4.3 — RORQUAL 30-SEED CAMPAIGN AUTHORIZATION AND EXECUTION" \
  "=================================================================" \
  "PACKAGE_ROOT=$PACKAGE_ROOT" \
  "REPO=$REPO" \
  "RORQUAL_HOST=$RORQUAL_HOST" \
  "RORQUAL_SCRATCH_LINK=$RORQUAL_SCRATCH_LINK" \
  "CAMPAIGN_SEEDS=44000-44029" \
  "SLURM_ARRAY=0-29%8" \
  "CAMPAIGN_EXECUTION_AUTHORIZED=YES_EXACT_PACKAGE_AND_SEEDS_ONLY" \
  "WSL_TERMINAL_CLOSE_REQUESTED=NO"

(
  cd "$PACKAGE_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo "INTERNAL_MANIFEST_VERIFICATION=PASS"
echo "SOURCE_PAYLOAD_MANIFEST_VERIFICATION=PASS"

[[ -f "$ARCHIVE" ]]
[[ "$(sha256sum "$ARCHIVE" | awk '{print $1}')" == "$ARCHIVE_SHA256" ]]
echo "EXECUTION_ARCHIVE_SHA256_GATE=PASS"

if [[ -x "$REPO/.venv/bin/python" ]]; then
  PYTHON="$REPO/.venv/bin/python"
  echo "REPO_VENV_ACTIVATED=YES"
else
  python3 -m venv "$REPO/.venv"
  PYTHON="$REPO/.venv/bin/python"
  echo "REPO_VENV_CREATED=YES"
fi
if ! "$PYTHON" -c 'import pytest' >/dev/null 2>&1; then
  "$PYTHON" -m pip install pytest
fi
"$PYTHON" -m pip check
echo "LOCAL_VENV_DEPENDENCY_GATE=PASS"

mapfile -t PY_FILES < <(find "$PACKAGE_ROOT" -type f -name '*.py' -print | sort)
"$PYTHON" - "${PY_FILES[@]}" <<'PY_IN_MEMORY'
from pathlib import Path
import sys
for raw in sys.argv[1:]:
    path=Path(raw)
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
PY_IN_MEMORY
echo "PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS"
echo "PYTHON_SYNTAX_FILE_COUNT=${#PY_FILES[@]}"

mapfile -t SH_FILES < <(find "$PACKAGE_ROOT" -type f -name '*.sh' -print | sort)
for file in "${SH_FILES[@]}"; do
  bash -n "$file"
done
echo "BASH_SYNTAX_CHECK=PASS"

"$PYTHON" -m pytest -q "$PACKAGE_ROOT/tests"
"$PYTHON" "$PACKAGE_ROOT/scripts/audit_authorization_prerequisites.py" --package-root "$PACKAGE_ROOT"

echo "LOCAL_QUALITY_GATE=PASS"

SOURCE_CLONE="$RUN_ROOT/github_source_clone"
git clone --branch e3-first-sector-p452 --single-branch \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$SOURCE_CLONE"
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
REQUIRED_ANCESTOR="0bfcd810717a117142fcf95ca7c00a982d473394"
git -C "$SOURCE_CLONE" merge-base --is-ancestor "$REQUIRED_ANCESTOR" HEAD
echo "GITHUB_REQUIRED_ANCESTOR_GATE=PASS"
GIT_HEAD_BEFORE="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
GIT_REMOTE_HEAD_BEFORE="$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)"
echo "GIT_HEAD_BEFORE=$GIT_HEAD_BEFORE"
echo "GIT_REMOTE_HEAD_BEFORE=$GIT_REMOTE_HEAD_BEFORE"

TOOL_DST="$SOURCE_CLONE/tools/phase1_v4_3_rorqual_30seed_campaign_execution_v1"
if [[ -e "$TOOL_DST" ]]; then
  echo "ERROR_GITHUB_TOOL_PATH_ALREADY_EXISTS=$TOOL_DST"
  false
fi
mkdir -p "$TOOL_DST"
"$PYTHON" - "$PACKAGE_ROOT" "$TOOL_DST" <<'PY'
from pathlib import Path
import shutil, sys
src=Path(sys.argv[1]); dst=Path(sys.argv[2])
for name in ('PACKAGE_VERSION.json','README.md','requirements.txt','SOURCE_PAYLOAD_MANIFEST.sha256'):
    if (src/name).is_file(): shutil.copy2(src/name,dst/name)
for dirname in ('config','docs','scripts','tests','wrappers'):
    shutil.copytree(src/dirname,dst/dirname)
imm=dst/'immutable_bindings'; imm.mkdir()
for path in sorted((src/'immutable_bindings').iterdir()):
    if path.suffix in {'.json','.sha256'}:
        shutil.copy2(path,imm/path.name)
PY
find "$TOOL_DST" -type f -exec sed -i 's/[[:space:]]\+$//' {} +
git -C "$SOURCE_CLONE" add "tools/phase1_v4_3_rorqual_30seed_campaign_execution_v1"
git -C "$SOURCE_CLONE" diff --cached --check
git -C "$SOURCE_CLONE" -c user.name='Ali Fazeli' -c user.email='ali.fazeli@utoronto.ca' \
  commit -m 'Authorize and orchestrate candidate-v4.3 Rorqual 30-seed campaign'
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
[[ "$(git -C "$SOURCE_CLONE" rev-parse HEAD^)" == "$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)" ]]
git -C "$SOURCE_CLONE" push origin HEAD:e3-first-sector-p452
CAMPAIGN_EXECUTION_SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
echo "CAMPAIGN_EXECUTION_SOURCE_COMMIT=$CAMPAIGN_EXECUTION_SOURCE_COMMIT"
echo "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

CONTROL_PATH="/tmp/fr3-rorqual-${UID}-$$"
SSH_OPTS=(-o ControlMaster=auto -o ControlPersist=12h -o ControlPath="$CONTROL_PATH" -o ServerAliveInterval=60 -o ServerAliveCountMax=120)
ssh "${SSH_OPTS[@]}" -fnNT "$RORQUAL_HOST"
REMOTE_UPLOAD="$RORQUAL_SCRATCH_LINK/FR3_V4_3_R2_AUTH_EXEC_${ARCHIVE_SHA256:0:12}.zip"
scp "${SSH_OPTS[@]}" "$ARCHIVE" "$RORQUAL_HOST:$REMOTE_UPLOAD"
REMOTE_ORCH_LOCAL="$PACKAGE_ROOT/wrappers/REMOTE_ORCHESTRATE_V4_3_RORQUAL_30SEED_CAMPAIGN.sh"
REMOTE_ORCH="$RORQUAL_SCRATCH_LINK/FR3_REMOTE_ORCHESTRATE_V4_3_R2_${ARCHIVE_SHA256:0:12}.sh"
scp "${SSH_OPTS[@]}" "$REMOTE_ORCH_LOCAL" "$RORQUAL_HOST:$REMOTE_ORCH"

REMOTE_LOG="$RUN_ROOT/REMOTE_CAMPAIGN_ORCHESTRATOR.log"
if ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
    "bash '$REMOTE_ORCH' '$REMOTE_UPLOAD' '$ARCHIVE_SHA256' '$RORQUAL_SCRATCH_LINK'" \
    2>&1 | tee "$REMOTE_LOG"; then
  REMOTE_WRAPPER_EXIT_CODE=0
else
  REMOTE_WRAPPER_EXIT_CODE="${PIPESTATUS[0]}"
fi
echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE"

REMOTE_RETURN_ZIP="$(grep '^CAMPAIGN_RETURN_ZIP=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
REMOTE_RETURN_SHA="$(grep '^CAMPAIGN_RETURN_ZIP_SHA256=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
if [[ -z "$REMOTE_RETURN_ZIP" || -z "$REMOTE_RETURN_SHA" ]]; then
  echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=90"
  failure_bundle 90 "REMOTE_RETURN_PATH_NOT_PRINTED"
  ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true
  false
fi

LOCAL_CAMPAIGN_ZIP="$LOCAL_RETURN/$(basename "$REMOTE_RETURN_ZIP")"
if scp "${SSH_OPTS[@]}" "$RORQUAL_HOST:$REMOTE_RETURN_ZIP" "$LOCAL_CAMPAIGN_ZIP" && \
   scp "${SSH_OPTS[@]}" "$RORQUAL_HOST:$REMOTE_RETURN_ZIP.sha256" "$LOCAL_CAMPAIGN_ZIP.sha256"; then
  DIAGNOSTIC_RETRIEVAL_EXIT_CODE=0
else
  DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$?
fi
ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true

echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE"
[[ "$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" -eq 0 ]]
[[ "$(sha256sum "$LOCAL_CAMPAIGN_ZIP" | awk '{print $1}')" == "$REMOTE_RETURN_SHA" ]]
(
  cd "$LOCAL_RETURN"
  sha256sum -c "$(basename "$LOCAL_CAMPAIGN_ZIP.sha256")" >/dev/null
)
unzip -t "$LOCAL_CAMPAIGN_ZIP" >/dev/null
echo "LOCAL_CAMPAIGN_RETURN_SHA256=$REMOTE_RETURN_SHA"
echo "LOCAL_CAMPAIGN_RETURN_ZIP_CRC=PASS"

LOCAL_AUDIT_LOG="$RUN_ROOT/LOCAL_CAMPAIGN_RETURN_AUDIT.log"
if "$PYTHON" "$PACKAGE_ROOT/scripts/audit_campaign_return.py" \
    --return-zip "$LOCAL_CAMPAIGN_ZIP" 2>&1 | tee "$LOCAL_AUDIT_LOG"; then
  LOCAL_RETURN_AUDIT_EXIT_CODE=0
else
  LOCAL_RETURN_AUDIT_EXIT_CODE="${PIPESTATUS[0]}"
fi
echo "LOCAL_RETURN_AUDIT_EXIT_CODE=$LOCAL_RETURN_AUDIT_EXIT_CODE"

EVIDENCE_CLONE="$RUN_ROOT/github_evidence_clone"
git clone --branch e3-first-sector-p452 --single-branch \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$EVIDENCE_CLONE"
git -C "$EVIDENCE_CLONE" merge-base --is-ancestor "$CAMPAIGN_EXECUTION_SOURCE_COMMIT" HEAD
EVIDENCE_DST="$EVIDENCE_CLONE/evidence/phase1_v4_3_rorqual_30seed_campaign_r2"
if [[ -e "$EVIDENCE_DST" ]]; then
  echo "ERROR_GITHUB_EVIDENCE_PATH_ALREADY_EXISTS=$EVIDENCE_DST"
  false
fi
mkdir -p "$EVIDENCE_DST"
EXTRACTED_RETURN="$RUN_ROOT/extracted_campaign_return"
rm -rf "$EXTRACTED_RETURN"
mkdir -p "$EXTRACTED_RETURN"
unzip -q "$LOCAL_CAMPAIGN_ZIP" -d "$EXTRACTED_RETURN"
RETURN_ROOT="$(find "$EXTRACTED_RETURN" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
[[ -d "$RETURN_ROOT" ]]
"$PYTHON" - "$RETURN_ROOT" "$EVIDENCE_DST" "$LOCAL_CAMPAIGN_ZIP.sha256" "$LOG" "$CAMPAIGN_EXECUTION_SOURCE_COMMIT" <<'PY'
from pathlib import Path
import json, shutil, sys
src=Path(sys.argv[1]); dst=Path(sys.argv[2]); sidecar=Path(sys.argv[3]); log=Path(sys.argv[4]); source_commit=sys.argv[5]
for name in ('CAMPAIGN_RETURN_METADATA.json','SEED_COMPLETION_INDEX.json','RETURN_MANIFEST.sha256'):
    if (src/name).is_file(): shutil.copy2(src/name,dst/name)
for rel in (
    'merged/PHASE1_MERGED_AUDIT.json',
    'merged/PHASE1_BOOTSTRAP_SUMMARY.json',
    'merged/PHASE1_SEED_CLUSTER_EFFECTS.csv',
    'merged/PHASE1_PRIMARY_PAIRED_EFFECTS.csv',
    'merged/PHASE1_METHOD_ENDPOINT_SUMMARY.csv',
    'merged/PHASE1_ACTION_AND_RUNTIME_SUMMARY.json',
    'merged/PHASE1_LEAVE_ONE_PASS_OUT.csv',
    'merged/PHASE1_SEED_RESULT_HASH_INDEX.csv',
    'merged/PHASE1_MERGED_REVIEW_RETURN.zip.sha256',
    'slurm/sacct_campaign.txt',
    'slurm/sacct_final.txt',
    'status/ARRAY_SUMMARY.json',
):
    p=src/rel
    if p.is_file():
        q=dst/rel; q.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,q)
merged_zip=src/'merged/FR3_PHASE1_MERGED_REVIEW_RETURN.zip'
if merged_zip.is_file() and merged_zip.stat().st_size < 95_000_000:
    q=dst/'merged'/merged_zip.name; q.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(merged_zip,q)
shutil.copy2(sidecar,dst/sidecar.name)
text=log.read_text(encoding='utf-8',errors='replace')
text='\n'.join(line.rstrip() for line in text.splitlines())+'\n'
(dst/'LOCAL_WSL_ORCHESTRATOR.log').write_text(text,encoding='utf-8')
meta=json.loads((src/'CAMPAIGN_RETURN_METADATA.json').read_text())
collection={'schema_version':1,'status':'COLLECTED_FOR_INDEPENDENT_REVIEW','scientific_status':meta['status'],'campaign_return_sha256':sidecar.read_text().split()[0],'campaign_execution_source_commit':source_commit,'next_gate':meta['next_gate']}
(dst/'COLLECTION_STATUS.json').write_text(json.dumps(collection,indent=2,sort_keys=True)+'\n')
PY
find "$EVIDENCE_DST" -type f \( -name '*.log' -o -name '*.txt' -o -name '*.csv' -o -name '*.json' -o -name '*.sha256' \) -exec sed -i 's/[[:space:]]\+$//' {} +
git -C "$EVIDENCE_CLONE" add "evidence/phase1_v4_3_rorqual_30seed_campaign_r2"
git -C "$EVIDENCE_CLONE" diff --cached --check
git -C "$EVIDENCE_CLONE" -c user.name='Ali Fazeli' -c user.email='ali.fazeli@utoronto.ca' \
  commit -m 'Collect candidate-v4.3 Rorqual 30-seed campaign evidence'
git -C "$EVIDENCE_CLONE" fetch origin e3-first-sector-p452
[[ "$(git -C "$EVIDENCE_CLONE" rev-parse HEAD^)" == "$(git -C "$EVIDENCE_CLONE" rev-parse origin/e3-first-sector-p452)" ]]
git -C "$EVIDENCE_CLONE" push origin HEAD:e3-first-sector-p452
GIT_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" rev-parse HEAD)"
GIT_REMOTE_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" ls-remote origin refs/heads/e3-first-sector-p452 | awk '{print $1}')"
echo "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT"
echo "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT"
echo "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

CAMPAIGN_RETURN_STATUS="$(grep '^CAMPAIGN_RETURN_STATUS=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
CAMPAIGN_SCIENTIFIC_EXIT_CODE="$(grep '^CAMPAIGN_SCIENTIFIC_EXIT_CODE=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
ARRAY_JOB_ID="$(grep '^ARRAY_JOB_ID=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
MERGE_JOB_ID="$(grep '^MERGE_JOB_ID=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
FINALIZER_JOB_ID="$(grep '^FINALIZER_JOB_ID=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"

printf '%s\n' \
  "=================================================================" \
  "FR3 V4.3 — RORQUAL 30-SEED CAMPAIGN FINAL REPORT" \
  "=================================================================" \
  "LOCAL_WRAPPER_EXIT_CODE=${CAMPAIGN_SCIENTIFIC_EXIT_CODE:-$LOCAL_RETURN_AUDIT_EXIT_CODE}" \
  "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE" \
  "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" \
  "LOCAL_RETURN_AUDIT_EXIT_CODE=$LOCAL_RETURN_AUDIT_EXIT_CODE" \
  "ARRAY_JOB_ID=$ARRAY_JOB_ID" \
  "MERGE_JOB_ID=$MERGE_JOB_ID" \
  "FINALIZER_JOB_ID=$FINALIZER_JOB_ID" \
  "CAMPAIGN_RETURN_STATUS=$CAMPAIGN_RETURN_STATUS" \
  "CAMPAIGN_SCIENTIFIC_EXIT_CODE=$CAMPAIGN_SCIENTIFIC_EXIT_CODE" \
  "LOCAL_CAMPAIGN_RETURN_ZIP=$LOCAL_CAMPAIGN_ZIP" \
  "LOCAL_CAMPAIGN_RETURN_ZIP_SHA256=$REMOTE_RETURN_SHA" \
  "CAMPAIGN_EXECUTION_SOURCE_COMMIT=$CAMPAIGN_EXECUTION_SOURCE_COMMIT" \
  "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT" \
  "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT" \
  "NEXT_GATE=INDEPENDENT_SCIENTIFIC_REVIEW_AND_TWC_RESULTS_MANUSCRIPT_INTEGRATION" \
  "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN" \
  "WSL_TERMINAL_CLOSE_REQUESTED=NO"

if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
fi

FINAL_RC="${CAMPAIGN_SCIENTIFIC_EXIT_CODE:-$LOCAL_RETURN_AUDIT_EXIT_CODE}"
exit "$FINAL_RC"
