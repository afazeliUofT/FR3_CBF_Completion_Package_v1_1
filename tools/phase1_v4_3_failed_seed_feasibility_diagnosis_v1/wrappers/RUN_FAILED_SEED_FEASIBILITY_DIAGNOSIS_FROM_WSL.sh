#!/usr/bin/env bash
set -Eeuo pipefail

: "${1:?package root is required}"
PACKAGE_ROOT="$(realpath "$1")"
REPO="${FR3_REPO_ROOT:?FR3_REPO_ROOT is required}"
DOWNLOADS="${FR3_DOWNLOADS:-/mnt/c/Users/alifa/Downloads}"
RORQUAL_HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
RORQUAL_SCRATCH_LINK="${FR3_RORQUAL_SCRATCH_LINK:-/home/rsadve1/links/scratch}"
ARCHIVE="${FR3_DIAGNOSTIC_ARCHIVE_PATH:?FR3_DIAGNOSTIC_ARCHIVE_PATH is required}"
ARCHIVE_SHA256="${FR3_DIAGNOSTIC_ARCHIVE_SHA256:?FR3_DIAGNOSTIC_ARCHIVE_SHA256 is required}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
RUN_ROOT="$HOME/fr3_v4_3_failed_seed_diagnosis_runs/$STAMP"
LOCAL_RETURN="$DOWNLOADS/FR3_V4_3_FAILED_SEED_DIAGNOSIS_RETURN_$STAMP"
LOG="$LOCAL_RETURN/LOCAL_WSL_ORCHESTRATOR.log"
mkdir -p "$RUN_ROOT" "$LOCAL_RETURN"
touch "$LOG"

exec > >(tee -a "$LOG") 2>&1

package_local_failure() {
  local rc=$1 stage=$2
  local failure_dir="$LOCAL_RETURN/FR3_V4_3_FAILED_SEED_DIAGNOSIS_LOCAL_FAILURE"
  local failure_zip="$LOCAL_RETURN/FR3_V4_3_FAILED_SEED_DIAGNOSIS_LOCAL_FAILURE.zip"
  rm -rf "$failure_dir" "$failure_zip" "$failure_zip.sha256"
  mkdir -p "$failure_dir"
  cp "$LOG" "$failure_dir/LOCAL_WSL_ORCHESTRATOR.log" 2>/dev/null || true
  printf '{\n  "schema_version": 1,\n  "status": "LOCAL_FAILURE_RETURN",\n  "stage": "%s",\n  "exit_code": %s\n}\n' \
    "$stage" "$rc" >"$failure_dir/FAILURE_STATUS.json"
  (
    cd "$failure_dir"
    find . -type f ! -name RETURN_MANIFEST.sha256 -print0 | sort -z | \
      xargs -0 sha256sum | sed 's#  \./#  #' > RETURN_MANIFEST.sha256
  )
  (
    cd "$LOCAL_RETURN"
    zip -q -r "$(basename "$failure_zip")" "$(basename "$failure_dir")"
    sha256sum "$(basename "$failure_zip")" >"$(basename "$failure_zip").sha256"
  )
  echo "LOCAL_FAILURE_RETURN_ZIP=$failure_zip"
  echo "LOCAL_FAILURE_RETURN_ZIP_SHA256=$(sha256sum "$failure_zip" | awk '{print $1}')"
}

unexpected_error() {
  local rc=$?
  trap - ERR
  echo "LOCAL_WRAPPER_STATUS=UNEXPECTED_FAILURE"
  echo "LOCAL_WRAPPER_EXIT_CODE=$rc"
  echo "LOCAL_FAILURE_COMMAND=${BASH_COMMAND:-unknown}"
  echo "CHANNEL_REGENERATION=NO"
  echo "GPU_REQUESTED=NO"
  echo "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
  package_local_failure "$rc" "UNEXPECTED_LOCAL_WRAPPER_FAILURE"
  if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap unexpected_error ERR

printf '%s\n' \
  "=================================================================" \
  "FR3 V4.3 — FAILED-SEED FEASIBILITY DIAGNOSIS" \
  "=================================================================" \
  "PACKAGE_ROOT=$PACKAGE_ROOT" \
  "REPO=$REPO" \
  "RORQUAL_HOST=$RORQUAL_HOST" \
  "FAILED_SEEDS=44001,44007,44008,44013,44017,44018,44024,44025,44026,44027,44028" \
  "CHANNEL_REGENERATION=NO" \
  "GPU_REQUESTED=NO" \
  "WORKER_WALLTIME=00:15:00" \
  "MERGE_WALLTIME=00:05:00" \
  "CAMPAIGN_RERUN_AUTHORIZED=NO" \
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
echo "DIAGNOSTIC_ARCHIVE_SHA256_GATE=PASS"

if [[ -x "$REPO/.venv/bin/python" ]]; then
  PYTHON="$REPO/.venv/bin/python"
  echo "REPO_VENV_ACTIVATED=YES"
else
  python3 -m venv "$REPO/.venv"
  PYTHON="$REPO/.venv/bin/python"
  echo "REPO_VENV_CREATED=YES"
fi
if ! "$PYTHON" -c 'import numpy,pandas,scipy,pytest' >/dev/null 2>&1; then
  "$PYTHON" -m pip install -r "$PACKAGE_ROOT/requirements.txt"
fi
"$PYTHON" -m pip check
echo "LOCAL_VENV_DEPENDENCY_GATE=PASS"

mapfile -t PY_FILES < <(find "$PACKAGE_ROOT" -type f -name '*.py' -print | sort)
"$PYTHON" - "${PY_FILES[@]}" <<'PY_IN_MEMORY'
from pathlib import Path
import sys
for raw in sys.argv[1:]:
    path=Path(raw)
    compile(path.read_text(encoding='utf-8'),str(path),'exec')
PY_IN_MEMORY
echo "PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS"
echo "PYTHON_SYNTAX_FILE_COUNT=${#PY_FILES[@]}"

mapfile -t SH_FILES < <(find "$PACKAGE_ROOT" -type f -name '*.sh' -print | sort)
for file in "${SH_FILES[@]}"; do bash -n "$file"; done
echo "BASH_SYNTAX_CHECK=PASS"

export PYTHONDONTWRITEBYTECODE=1
"$PYTHON" -m pytest -q -p no:cacheprovider "$PACKAGE_ROOT/tests"

LOCAL_AUDIT_DIR="$LOCAL_RETURN/local_campaign_audit"
mkdir -p "$LOCAL_AUDIT_DIR"
"$PYTHON" "$PACKAGE_ROOT/scripts/audit_campaign_return.py" \
  --campaign-zip "$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_18145937.zip" \
  --output-dir "$LOCAL_AUDIT_DIR" \
  | tee "$LOCAL_AUDIT_DIR/audit_stdout.log"
echo "LOCAL_QUALITY_GATE=PASS"

SOURCE_CLONE="$RUN_ROOT/github_source_clone"
git clone --branch e3-first-sector-p452 --single-branch \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$SOURCE_CLONE"
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
REQUIRED_ANCESTOR="0e2634d084849d4db36b951574bed2162761e92d"
git -C "$SOURCE_CLONE" merge-base --is-ancestor "$REQUIRED_ANCESTOR" HEAD
echo "GITHUB_REQUIRED_ANCESTOR_GATE=PASS"
GIT_HEAD_BEFORE="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
GIT_REMOTE_HEAD_BEFORE="$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)"
echo "GIT_HEAD_BEFORE=$GIT_HEAD_BEFORE"
echo "GIT_REMOTE_HEAD_BEFORE=$GIT_REMOTE_HEAD_BEFORE"

TOOL_DST="$SOURCE_CLONE/tools/phase1_v4_3_failed_seed_feasibility_diagnosis_v1"
[[ ! -e "$TOOL_DST" ]] || {
  echo "ERROR_GITHUB_TOOL_PATH_ALREADY_EXISTS=$TOOL_DST"
  false
}
mkdir -p "$TOOL_DST"
"$PYTHON" - "$PACKAGE_ROOT" "$TOOL_DST" <<'PY_COPY'
from pathlib import Path
import shutil,sys
src=Path(sys.argv[1]); dst=Path(sys.argv[2])
for name in ('PACKAGE_VERSION.json','README.md','requirements.txt','SOURCE_PAYLOAD_MANIFEST.sha256'):
    if (src/name).is_file(): shutil.copy2(src/name,dst/name)
for dirname in ('config','docs','scripts','tests','wrappers'):
    shutil.copytree(src/dirname,dst/dirname)
imm=dst/'immutable_bindings'; imm.mkdir()
for path in sorted((src/'immutable_bindings').iterdir()):
    if path.suffix in {'.json','.sha256'}:
        shutil.copy2(path,imm/path.name)
PY_COPY
find "$TOOL_DST" -type f -exec sed -i 's/[[:space:]]\+$//' {} +
git -C "$SOURCE_CLONE" add "tools/phase1_v4_3_failed_seed_feasibility_diagnosis_v1"
git -C "$SOURCE_CLONE" diff --cached --check
git -C "$SOURCE_CLONE" -c user.name='Ali Fazeli' -c user.email='ali.fazeli@utoronto.ca' \
  commit -m 'Add candidate-v4.3 failed-seed feasibility diagnosis'
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
[[ "$(git -C "$SOURCE_CLONE" rev-parse HEAD^)" == "$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)" ]]
git -C "$SOURCE_CLONE" push origin HEAD:e3-first-sector-p452
DIAGNOSTIC_SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
echo "DIAGNOSTIC_SOURCE_COMMIT=$DIAGNOSTIC_SOURCE_COMMIT"
echo "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

CONTROL_PATH="/tmp/fr3-rorqual-${UID}-$$"
SSH_OPTS=(-o ControlMaster=auto -o ControlPersist=12h -o ControlPath="$CONTROL_PATH" -o ServerAliveInterval=60 -o ServerAliveCountMax=120)
ssh "${SSH_OPTS[@]}" -fnNT "$RORQUAL_HOST"
REMOTE_UPLOAD="$RORQUAL_SCRATCH_LINK/FR3_V4_3_FAILED_SEED_DIAG_${ARCHIVE_SHA256:0:12}.zip"
REMOTE_AUDIT="$RORQUAL_SCRATCH_LINK/FR3_V4_3_FAILED_SEED_LOCAL_AUDIT_${ARCHIVE_SHA256:0:12}.json"
REMOTE_ORCH="$RORQUAL_SCRATCH_LINK/FR3_REMOTE_FAILED_SEED_DIAG_${ARCHIVE_SHA256:0:12}.sh"
scp "${SSH_OPTS[@]}" "$ARCHIVE" "$RORQUAL_HOST:$REMOTE_UPLOAD"
scp "${SSH_OPTS[@]}" "$LOCAL_AUDIT_DIR/LOCAL_CAMPAIGN_SCIENTIFIC_AUDIT.json" "$RORQUAL_HOST:$REMOTE_AUDIT"
scp "${SSH_OPTS[@]}" "$PACKAGE_ROOT/wrappers/REMOTE_ORCHESTRATE_FAILED_SEED_DIAGNOSIS.sh" "$RORQUAL_HOST:$REMOTE_ORCH"

REMOTE_LOG="$RUN_ROOT/REMOTE_FAILED_SEED_DIAGNOSTIC.log"
RUN_TAG="${ARCHIVE_SHA256:0:12}_${STAMP}"
if ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
  "env REMOTE_PACKAGE_ZIP='$REMOTE_UPLOAD' EXPECTED_PACKAGE_SHA256='$ARCHIVE_SHA256' REMOTE_LOCAL_AUDIT_JSON='$REMOTE_AUDIT' RUN_TAG='$RUN_TAG' bash '$REMOTE_ORCH'" \
  2>&1 | tee "$REMOTE_LOG"; then
  REMOTE_WRAPPER_EXIT_CODE=0
else
  REMOTE_WRAPPER_EXIT_CODE="${PIPESTATUS[0]}"
fi
echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE"

REMOTE_RETURN_ZIP="$(grep '^REMOTE_RETURN_ZIP=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
REMOTE_RETURN_SHA="$(grep '^REMOTE_RETURN_ZIP_SHA256=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
if [[ -z "$REMOTE_RETURN_ZIP" || -z "$REMOTE_RETURN_SHA" ]]; then
  echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=90"
  package_local_failure 90 "REMOTE_RETURN_PATH_NOT_PRINTED"
  ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true
  false
fi

LOCAL_DIAGNOSTIC_ZIP="$LOCAL_RETURN/$(basename "$REMOTE_RETURN_ZIP")"
if scp "${SSH_OPTS[@]}" "$RORQUAL_HOST:$REMOTE_RETURN_ZIP" "$LOCAL_DIAGNOSTIC_ZIP" && \
   scp "${SSH_OPTS[@]}" "$RORQUAL_HOST:$REMOTE_RETURN_ZIP.sha256" "$LOCAL_DIAGNOSTIC_ZIP.sha256"; then
  DIAGNOSTIC_RETRIEVAL_EXIT_CODE=0
else
  DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$?
fi
ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true

echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE"
[[ "$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" -eq 0 ]]
python3 - "$LOCAL_DIAGNOSTIC_ZIP.sha256" "$(basename "$LOCAL_DIAGNOSTIC_ZIP")" "$REMOTE_RETURN_SHA" <<'PY_SIDECAR'
from pathlib import Path
import sys
p=Path(sys.argv[1]); expected_name=sys.argv[2]; expected_hash=sys.argv[3]
lines=p.read_text(encoding='utf-8').splitlines()
assert len(lines)==1
parts=lines[0].split()
assert len(parts)==2
assert parts[0]==expected_hash
assert parts[1]==expected_name
assert Path(parts[1]).name==parts[1]
print('RETURN_SIDECAR_BASENAME_GATE=PASS')
PY_SIDECAR
[[ "$(sha256sum "$LOCAL_DIAGNOSTIC_ZIP" | awk '{print $1}')" == "$REMOTE_RETURN_SHA" ]]
(
  cd "$LOCAL_RETURN"
  sha256sum -c "$(basename "$LOCAL_DIAGNOSTIC_ZIP.sha256")" >/dev/null
)
unzip -t "$LOCAL_DIAGNOSTIC_ZIP" >/dev/null

RETURN_VERIFY_JSON="$LOCAL_RETURN/DIAGNOSTIC_RETURN_VERIFICATION.json"
if "$PYTHON" "$PACKAGE_ROOT/scripts/verify_diagnostic_return.py" \
    --return-zip "$LOCAL_DIAGNOSTIC_ZIP" \
    --expected-sha256 "$REMOTE_RETURN_SHA" \
    --output-json "$RETURN_VERIFY_JSON" \
    | tee "$LOCAL_RETURN/DIAGNOSTIC_RETURN_VERIFICATION.log"; then
  RETURN_VERIFICATION_EXIT_CODE=0
else
  RETURN_VERIFICATION_EXIT_CODE="${PIPESTATUS[0]}"
fi
echo "RETURN_VERIFICATION_EXIT_CODE=$RETURN_VERIFICATION_EXIT_CODE"

EXTRACTED_RETURN="$RUN_ROOT/extracted_diagnostic_return"
rm -rf "$EXTRACTED_RETURN"
mkdir -p "$EXTRACTED_RETURN"
unzip -q "$LOCAL_DIAGNOSTIC_ZIP" -d "$EXTRACTED_RETURN"
RETURN_ROOT="$(find "$EXTRACTED_RETURN" -mindepth 1 -maxdepth 1 -type d | head -1)"
[[ -d "$RETURN_ROOT" ]]

EVIDENCE_CLONE="$RUN_ROOT/github_evidence_clone"
git clone --branch e3-first-sector-p452 --single-branch \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$EVIDENCE_CLONE"
git -C "$EVIDENCE_CLONE" merge-base --is-ancestor "$DIAGNOSTIC_SOURCE_COMMIT" HEAD
EVIDENCE_DST="$EVIDENCE_CLONE/evidence/phase1_v4_3_failed_seed_feasibility_diagnosis_v1"
[[ ! -e "$EVIDENCE_DST" ]] || {
  echo "ERROR_GITHUB_EVIDENCE_PATH_ALREADY_EXISTS=$EVIDENCE_DST"
  false
}
mkdir -p "$EVIDENCE_DST"
"$PYTHON" - "$RETURN_ROOT" "$EVIDENCE_DST" "$LOCAL_DIAGNOSTIC_ZIP.sha256" "$LOG" "$LOCAL_AUDIT_DIR" "$RETURN_VERIFY_JSON" "$DIAGNOSTIC_SOURCE_COMMIT" <<'PY_EVIDENCE'
from pathlib import Path
import json,shutil,sys
src=Path(sys.argv[1]); dst=Path(sys.argv[2]); sidecar=Path(sys.argv[3]); log=Path(sys.argv[4]); audit=Path(sys.argv[5]); verify=Path(sys.argv[6]); source_commit=sys.argv[7]
for name in ('RETURN_STATUS.json','RETURN_MANIFEST.sha256','DIAGNOSTIC_CONTRACT.json','sacct_diagnostic.txt'):
    if (src/name).is_file(): shutil.copy2(src/name,dst/name)
for rel in (
    'merged/NEXT_REPAIR_DECISION.json',
    'merged/FAILED_SEED_DIAGNOSIS_SUMMARY.json',
    'merged/INTERVAL_CLASSIFICATION_SUMMARY.csv',
    'merged/AFFECTED_USER_AGGREGATE.csv',
    'merged/merge_stdout.log',
    'merged/merge_stderr.log',
):
    p=src/rel
    if p.is_file():
        q=dst/rel; q.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,q)
for seed_dir in sorted((src/'seed_diagnostics').glob('seed_*')) if (src/'seed_diagnostics').is_dir() else []:
    q=dst/'seed_summaries'/seed_dir.name; q.mkdir(parents=True,exist_ok=True)
    for name in ('FAILED_SEED_DIAGNOSIS.json','REPRODUCTION_AUDIT.csv','AFFECTED_USER_DIAGNOSIS.csv','TASK_STATUS.json','process_exit_code.txt'):
        p=seed_dir/name
        if p.is_file(): shutil.copy2(p,q/name)
shutil.copy2(sidecar,dst/sidecar.name)
shutil.copy2(verify,dst/verify.name)
if (audit/'LOCAL_CAMPAIGN_SCIENTIFIC_AUDIT.json').is_file():
    shutil.copy2(audit/'LOCAL_CAMPAIGN_SCIENTIFIC_AUDIT.json',dst/'LOCAL_CAMPAIGN_SCIENTIFIC_AUDIT.json')
text=log.read_text(encoding='utf-8',errors='replace')
text='\n'.join(line.rstrip() for line in text.splitlines())+'\n'
(dst/'LOCAL_WSL_ORCHESTRATOR.log').write_text(text,encoding='utf-8')
ver=json.loads(verify.read_text())
collection={
    'schema_version':1,
    'status':'COLLECTED_FOR_INDEPENDENT_REVIEW',
    'complete_scientific_decision_available':ver['complete_scientific_decision_available'],
    'next_repair_decision':ver['next_repair_decision'],
    'next_gate':ver['next_gate'],
    'return_zip_sha256':ver['return_zip_sha256'],
    'diagnostic_source_commit':source_commit,
    'candidate_source_changed':False,
    'channel_regenerated':False,
}
(dst/'COLLECTION_STATUS.json').write_text(json.dumps(collection,indent=2,sort_keys=True)+'\n')
PY_EVIDENCE
find "$EVIDENCE_DST" -type f \( -name '*.log' -o -name '*.txt' -o -name '*.csv' -o -name '*.json' -o -name '*.sha256' \) -exec sed -i 's/[[:space:]]\+$//' {} +
git -C "$EVIDENCE_CLONE" add "evidence/phase1_v4_3_failed_seed_feasibility_diagnosis_v1"
git -C "$EVIDENCE_CLONE" diff --cached --check
git -C "$EVIDENCE_CLONE" -c user.name='Ali Fazeli' -c user.email='ali.fazeli@utoronto.ca' \
  commit -m 'Collect candidate-v4.3 failed-seed feasibility diagnosis'
git -C "$EVIDENCE_CLONE" fetch origin e3-first-sector-p452
[[ "$(git -C "$EVIDENCE_CLONE" rev-parse HEAD^)" == "$(git -C "$EVIDENCE_CLONE" rev-parse origin/e3-first-sector-p452)" ]]
git -C "$EVIDENCE_CLONE" push origin HEAD:e3-first-sector-p452
GIT_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" rev-parse HEAD)"
GIT_REMOTE_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" ls-remote origin refs/heads/e3-first-sector-p452 | awk '{print $1}')"
echo "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT"
echo "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT"
echo "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

NEXT_REPAIR_DECISION="$(python3 - "$RETURN_VERIFY_JSON" <<'PY_DECISION'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
print(v.get('next_repair_decision') or 'UNAVAILABLE_DIAGNOSTIC_RETURN_REVIEW_REQUIRED')
PY_DECISION
)"
NEXT_GATE="$(python3 - "$RETURN_VERIFY_JSON" <<'PY_GATE'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
print(v.get('next_gate') or 'REVIEW_FAILED_SEED_DIAGNOSTIC_INFRASTRUCTURE')
PY_GATE
)"
ARRAY_JOB_ID="$(grep '^ARRAY_JOB_ID=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
MERGE_JOB_ID="$(grep '^MERGE_JOB_ID=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
MERGE_STATE="$(grep '^MERGE_STATE=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
MERGE_EXIT_CODE="$(grep '^MERGE_EXIT_CODE=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"

printf '%s\n' \
  "=================================================================" \
  "FR3 V4.3 — FAILED-SEED DIAGNOSIS FINAL REPORT" \
  "=================================================================" \
  "LOCAL_WRAPPER_EXIT_CODE=$RETURN_VERIFICATION_EXIT_CODE" \
  "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE" \
  "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" \
  "RETURN_VERIFICATION_EXIT_CODE=$RETURN_VERIFICATION_EXIT_CODE" \
  "ARRAY_JOB_ID=$ARRAY_JOB_ID" \
  "MERGE_JOB_ID=$MERGE_JOB_ID" \
  "MERGE_STATE=${MERGE_STATE:-UNKNOWN}" \
  "MERGE_EXIT_CODE=${MERGE_EXIT_CODE:-UNKNOWN}" \
  "LOCAL_DIAGNOSTIC_RETURN_ZIP=$LOCAL_DIAGNOSTIC_ZIP" \
  "LOCAL_DIAGNOSTIC_RETURN_ZIP_SHA256=$REMOTE_RETURN_SHA" \
  "DIAGNOSTIC_SOURCE_COMMIT=$DIAGNOSTIC_SOURCE_COMMIT" \
  "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT" \
  "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT" \
  "NEXT_REPAIR_DECISION=$NEXT_REPAIR_DECISION" \
  "NEXT_GATE=$NEXT_GATE" \
  "CHANNEL_REGENERATION=NO" \
  "GPU_REQUESTED=NO" \
  "WORKER_WALLTIME=00:15:00" \
  "MERGE_WALLTIME=00:05:00" \
  "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN" \
  "WSL_TERMINAL_CLOSE_REQUESTED=NO"

if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
fi

exit "$RETURN_VERIFICATION_EXIT_CODE"
