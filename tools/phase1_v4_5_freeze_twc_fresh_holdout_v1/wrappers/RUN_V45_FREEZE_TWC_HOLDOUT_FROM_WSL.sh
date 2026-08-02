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
RUN_ROOT="$HOME/fr3_v45_freeze_twc_holdout_runs/$STAMP"
LOCAL_RETURN="$DOWNLOADS/FR3_V45_FREEZE_TWC_HOLDOUT_RETURN_$STAMP"
LOG="$LOCAL_RETURN/LOCAL_WSL_ORCHESTRATOR.log"
mkdir -p "$RUN_ROOT" "$LOCAL_RETURN"; touch "$LOG"
exec > >(tee -a "$LOG") 2>&1

failure_bundle(){ "$PACKAGE_ROOT/scripts/package_local_failure.py" --output-dir "$LOCAL_RETURN" --log "$LOG" --stage "$2" --exit-code "$1" || true; }
unexpected_error(){ local rc=$?; trap - ERR; echo "LOCAL_WRAPPER_STATUS=UNEXPECTED_FAILURE"; echo "LOCAL_WRAPPER_EXIT_CODE=$rc"; echo "LOCAL_FAILURE_COMMAND=${BASH_COMMAND:-unknown}"; echo "AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO"; failure_bundle "$rc" "UNEXPECTED_LOCAL_WRAPPER_FAILURE"; echo "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"; if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true; fi; exit "$rc"; }
trap unexpected_error ERR

printf '%s\n' \
 "=================================================================" \
 "FR3 V4.5 — FREEZE, TWC DRAFT START, AND FRESH HOLDOUT" \
 "=================================================================" \
 "PACKAGE_ROOT=$PACKAGE_ROOT" "REPO=$REPO" "RORQUAL_HOST=$RORQUAL_HOST" \
 "DEVELOPMENT_TUNING_STOPPED=YES" "FRESH_HOLDOUT_SEEDS=44030-44059" \
 "WORKER_WALLTIME=00:10:00" "WORKER_MEMORY=16G" \
 "AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO" "WSL_TERMINAL_CLOSE_REQUESTED=NO"
(cd "$PACKAGE_ROOT" && sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null && sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null)
echo "INTERNAL_MANIFEST_VERIFICATION=PASS"; echo "SOURCE_PAYLOAD_MANIFEST_VERIFICATION=PASS"
[[ -f "$ARCHIVE" && "$(sha256sum "$ARCHIVE"|awk '{print $1}')" == "$ARCHIVE_SHA256" ]]
echo "EXECUTION_ARCHIVE_SHA256_GATE=PASS"
if [[ -x "$REPO/.venv/bin/python" ]]; then PYTHON="$REPO/.venv/bin/python"; echo "REPO_VENV_ACTIVATED=YES"; else python3 -m venv "$REPO/.venv"; PYTHON="$REPO/.venv/bin/python"; echo "REPO_VENV_CREATED=YES"; fi
if ! "$PYTHON" -c 'import pytest' >/dev/null 2>&1; then "$PYTHON" -m pip install pytest; fi
"$PYTHON" -m pip check; echo "LOCAL_VENV_DEPENDENCY_GATE=PASS"
mapfile -t PY_FILES < <(find "$PACKAGE_ROOT" -type f -name '*.py' -print | sort)
"$PYTHON" - "${PY_FILES[@]}" <<'PY'
from pathlib import Path
import sys
for raw in sys.argv[1:]: compile(Path(raw).read_text(encoding='utf-8'),raw,'exec')
PY
echo "PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS"; echo "PYTHON_SYNTAX_FILE_COUNT=${#PY_FILES[@]}"
mapfile -t SH_FILES < <(find "$PACKAGE_ROOT" -type f -name '*.sh' -print | sort)
for f in "${SH_FILES[@]}"; do bash -n "$f"; done
echo "BASH_SYNTAX_CHECK=PASS"
"$PYTHON" -m pytest -q "$PACKAGE_ROOT/tests"
FREEZE_OUT="$LOCAL_RETURN/freeze"
"$PYTHON" "$PACKAGE_ROOT/scripts/audit_and_freeze_v45.py" --package-root "$PACKAGE_ROOT" --output-dir "$FREEZE_OUT"
cp -a "$PACKAGE_ROOT/twc_draft" "$LOCAL_RETURN/twc_draft_start"
echo "LOCAL_QUALITY_GATE=PASS"

SOURCE_CLONE="$RUN_ROOT/github_source_clone"
git clone --branch e3-first-sector-p452 --single-branch git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$SOURCE_CLONE"
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
REQUIRED_ANCESTOR="66daf6ba3b924090e451b3bb08045a6814a7f889"
git -C "$SOURCE_CLONE" merge-base --is-ancestor "$REQUIRED_ANCESTOR" HEAD
echo "GITHUB_REQUIRED_ANCESTOR_GATE=PASS"
GIT_HEAD_BEFORE="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
GIT_REMOTE_HEAD_BEFORE="$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)"
echo "GIT_HEAD_BEFORE=$GIT_HEAD_BEFORE"; echo "GIT_REMOTE_HEAD_BEFORE=$GIT_REMOTE_HEAD_BEFORE"
TOOL_DST="$SOURCE_CLONE/tools/phase1_v4_5_freeze_twc_fresh_holdout_v1"
CAMPAIGN_DST="$SOURCE_CLONE/campaign/phase1_rorqual_v4_5_fresh_holdout_v1"
PAPER_DST="$SOURCE_CLONE/paper/twc_v4_5_draft_start"
for path in "$TOOL_DST" "$CAMPAIGN_DST" "$PAPER_DST"; do [[ ! -e "$path" ]] || { echo "ERROR_GITHUB_PATH_ALREADY_EXISTS=$path"; false; }; done
mkdir -p "$TOOL_DST" "$CAMPAIGN_DST" "$PAPER_DST"
"$PYTHON" - "$PACKAGE_ROOT" "$TOOL_DST" "$CAMPAIGN_DST" "$PAPER_DST" <<'PY'
from pathlib import Path
import shutil,sys
src=Path(sys.argv[1]); tool=Path(sys.argv[2]); campaign=Path(sys.argv[3]); paper=Path(sys.argv[4])
for name in ('PACKAGE_VERSION.json','README.md','requirements.txt','SOURCE_PAYLOAD_MANIFEST.sha256'):
    if (src/name).is_file(): shutil.copy2(src/name,tool/name)
for d in ('config','docs','scripts','tests','wrappers'):
    shutil.copytree(src/d,tool/d)
imm=tool/'immutable_bindings'; imm.mkdir()
for p in sorted((src/'immutable_bindings').iterdir()):
    if p.suffix in {'.json','.csv','.sha256'}: shutil.copy2(p,imm/p.name)
for name in ('FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip','FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip.sha256'):
    shutil.copy2(src/'immutable_bindings'/name,campaign/name)
shutil.copy2(src/'config'/'FREEZE_HOLDOUT_CONTRACT.json',campaign/'FREEZE_HOLDOUT_CONTRACT.json')
for p in (src/'twc_draft').rglob('*'):
    if p.is_file():
        dst=paper/p.relative_to(src/'twc_draft'); dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dst)
PY
find "$TOOL_DST" "$CAMPAIGN_DST" "$PAPER_DST" -type f -exec sed -i 's/[[:space:]]\+$//' {} +
git -C "$SOURCE_CLONE" add tools/phase1_v4_5_freeze_twc_fresh_holdout_v1 campaign/phase1_rorqual_v4_5_fresh_holdout_v1 paper/twc_v4_5_draft_start
git -C "$SOURCE_CLONE" diff --cached --check
git -C "$SOURCE_CLONE" -c user.name='Ali Fazeli' -c user.email='ali.fazeli@utoronto.ca' commit -m 'Freeze candidate-v4.5, start TWC draft, and authorize fresh holdout'
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
[[ "$(git -C "$SOURCE_CLONE" rev-parse HEAD^)" == "$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)" ]]
git -C "$SOURCE_CLONE" push origin HEAD:e3-first-sector-p452
HOLDOUT_SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
echo "HOLDOUT_SOURCE_COMMIT=$HOLDOUT_SOURCE_COMMIT"; echo "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

CONTROL_PATH="/tmp/fr3-v45-holdout-${UID}-$$"
SSH_OPTS=(-o ControlMaster=auto -o ControlPersist=12h -o ControlPath="$CONTROL_PATH" -o ServerAliveInterval=60 -o ServerAliveCountMax=120)
ssh "${SSH_OPTS[@]}" -fnNT "$RORQUAL_HOST"
REMOTE_UPLOAD="$RORQUAL_SCRATCH_LINK/FR3_V45_HOLDOUT_EXEC_${ARCHIVE_SHA256:0:12}.zip"
REMOTE_ORCH="$RORQUAL_SCRATCH_LINK/FR3_REMOTE_ORCH_V45_HOLDOUT_${ARCHIVE_SHA256:0:12}.sh"
scp "${SSH_OPTS[@]}" "$ARCHIVE" "$RORQUAL_HOST:$REMOTE_UPLOAD"
scp "${SSH_OPTS[@]}" "$PACKAGE_ROOT/wrappers/REMOTE_ORCHESTRATE_V45_FRESH_HOLDOUT.sh" "$RORQUAL_HOST:$REMOTE_ORCH"
REMOTE_LOG="$RUN_ROOT/REMOTE_HOLDOUT_ORCHESTRATOR.log"
if ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" "bash '$REMOTE_ORCH' '$REMOTE_UPLOAD' '$ARCHIVE_SHA256' '$RORQUAL_SCRATCH_LINK'" 2>&1 | tee "$REMOTE_LOG"; then REMOTE_WRAPPER_EXIT_CODE=0; else REMOTE_WRAPPER_EXIT_CODE="${PIPESTATUS[0]}"; fi
echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE"
REMOTE_RETURN_ZIP="$(grep '^HOLDOUT_RETURN_ZIP=' "$REMOTE_LOG"|tail -1|cut -d= -f2-)"
REMOTE_RETURN_SHA="$(grep '^HOLDOUT_RETURN_ZIP_SHA256=' "$REMOTE_LOG"|tail -1|cut -d= -f2-)"
ARRAY_JOB_ID="$(grep '^ARRAY_JOB_ID=' "$REMOTE_LOG"|tail -1|cut -d= -f2-)"
MERGE_JOB_ID="$(grep '^MERGE_JOB_ID=' "$REMOTE_LOG"|tail -1|cut -d= -f2-)"
FINALIZER_JOB_ID="$(grep '^FINALIZER_JOB_ID=' "$REMOTE_LOG"|tail -1|cut -d= -f2-)"
if [[ -z "$REMOTE_RETURN_ZIP" || -z "$REMOTE_RETURN_SHA" ]]; then echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=90"; failure_bundle 90 REMOTE_RETURN_PATH_NOT_PRINTED; ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true; false; fi
LOCAL_HOLDOUT_ZIP="$LOCAL_RETURN/$(basename "$REMOTE_RETURN_ZIP")"
if scp "${SSH_OPTS[@]}" "$RORQUAL_HOST:$REMOTE_RETURN_ZIP" "$LOCAL_HOLDOUT_ZIP" && scp "${SSH_OPTS[@]}" "$RORQUAL_HOST:$REMOTE_RETURN_ZIP.sha256" "$LOCAL_HOLDOUT_ZIP.sha256"; then DIAGNOSTIC_RETRIEVAL_EXIT_CODE=0; else DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$?; fi
ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true
echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE"
[[ "$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" -eq 0 && "$(sha256sum "$LOCAL_HOLDOUT_ZIP"|awk '{print $1}')" == "$REMOTE_RETURN_SHA" ]]
(cd "$LOCAL_RETURN" && sha256sum -c "$(basename "$LOCAL_HOLDOUT_ZIP.sha256")" >/dev/null)
unzip -t "$LOCAL_HOLDOUT_ZIP" >/dev/null
echo "LOCAL_HOLDOUT_RETURN_SHA256=$REMOTE_RETURN_SHA"; echo "LOCAL_HOLDOUT_RETURN_ZIP_CRC=PASS"
if "$PYTHON" "$PACKAGE_ROOT/scripts/audit_fresh_holdout_return.py" --return-zip "$LOCAL_HOLDOUT_ZIP" --twc-output-dir "$LOCAL_RETURN/twc_draft_start" 2>&1 | tee "$RUN_ROOT/LOCAL_HOLDOUT_AUDIT.log"; then LOCAL_RETURN_AUDIT_EXIT_CODE=0; else LOCAL_RETURN_AUDIT_EXIT_CODE="${PIPESTATUS[0]}"; fi
echo "LOCAL_RETURN_AUDIT_EXIT_CODE=$LOCAL_RETURN_AUDIT_EXIT_CODE"

EVIDENCE_CLONE="$RUN_ROOT/github_evidence_clone"
git clone --branch e3-first-sector-p452 --single-branch git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$EVIDENCE_CLONE"
git -C "$EVIDENCE_CLONE" merge-base --is-ancestor "$HOLDOUT_SOURCE_COMMIT" HEAD
EVIDENCE_DST="$EVIDENCE_CLONE/evidence/phase1_v4_5_fresh_holdout_v1_job_${ARRAY_JOB_ID:-unknown}"
[[ ! -e "$EVIDENCE_DST" ]]; mkdir -p "$EVIDENCE_DST"
EXTRACTED="$RUN_ROOT/extracted_holdout_return"; mkdir -p "$EXTRACTED"; unzip -q "$LOCAL_HOLDOUT_ZIP" -d "$EXTRACTED"
RETURN_ROOT="$(find "$EXTRACTED" -mindepth 1 -maxdepth 1 -type d|head -1)"; [[ -d "$RETURN_ROOT" ]]
"$PYTHON" - "$RETURN_ROOT" "$EVIDENCE_DST" "$LOCAL_HOLDOUT_ZIP.sha256" "$LOG" "$LOCAL_RETURN/twc_draft_start" <<'PY'
from pathlib import Path
import shutil,sys
src=Path(sys.argv[1]); dst=Path(sys.argv[2]); sidecar=Path(sys.argv[3]); log=Path(sys.argv[4]); paper=Path(sys.argv[5])
for name in ('HOLDOUT_RETURN_METADATA.json','SEED_COMPLETION_INDEX.json','RETURN_MANIFEST.sha256'):
    if (src/name).is_file(): shutil.copy2(src/name,dst/name)
for rel in ('merged/PHASE1_MERGED_AUDIT.json','merged/PHASE1_BOOTSTRAP_SUMMARY.json','merged/PHASE1_SEED_CLUSTER_EFFECTS.csv','merged/PHASE1_PRIMARY_PAIRED_EFFECTS.csv','merged/PHASE1_METHOD_ENDPOINT_SUMMARY.csv','merged/PHASE1_LEAVE_ONE_PASS_OUT.csv','merged/PHASE1_ACTION_AND_RUNTIME_SUMMARY.json','slurm/sacct_holdout.txt'):
    p=src/rel
    if p.is_file(): q=dst/rel; q.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,q)
shutil.copy2(sidecar,dst/sidecar.name)
shutil.copy2(log,dst/'LOCAL_WSL_ORCHESTRATOR.log')
for name in ('generated_holdout_results.tex','HOLDOUT_PAPER_RESULT.json'):
    if (paper/name).is_file(): shutil.copy2(paper/name,dst/name)
PY
find "$EVIDENCE_DST" -type f -exec sed -i 's/[[:space:]]\+$//' {} +
git -C "$EVIDENCE_CLONE" add "${EVIDENCE_DST#$EVIDENCE_CLONE/}"
git -C "$EVIDENCE_CLONE" diff --cached --check
git -C "$EVIDENCE_CLONE" -c user.name='Ali Fazeli' -c user.email='ali.fazeli@utoronto.ca' commit -m 'Collect candidate-v4.5 fresh holdout evidence'
git -C "$EVIDENCE_CLONE" fetch origin e3-first-sector-p452
[[ "$(git -C "$EVIDENCE_CLONE" rev-parse HEAD^)" == "$(git -C "$EVIDENCE_CLONE" rev-parse origin/e3-first-sector-p452)" ]]
git -C "$EVIDENCE_CLONE" push origin HEAD:e3-first-sector-p452
GIT_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" rev-parse HEAD)"; GIT_REMOTE_FINAL_COMMIT="$(git ls-remote git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git refs/heads/e3-first-sector-p452|awk '{print $1}')"
echo "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT"; echo "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT"
cp "$RUN_ROOT/LOCAL_HOLDOUT_AUDIT.log" "$LOCAL_RETURN/"; cp "$REMOTE_LOG" "$LOCAL_RETURN/"
printf '%s\n' "LOCAL_WRAPPER_EXIT_CODE=$LOCAL_RETURN_AUDIT_EXIT_CODE" "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE" "ARRAY_JOB_ID=$ARRAY_JOB_ID" "MERGE_JOB_ID=$MERGE_JOB_ID" "FINALIZER_JOB_ID=$FINALIZER_JOB_ID" "AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO" "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN" "WSL_TERMINAL_CLOSE_REQUESTED=NO"
if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true; fi
exit "$LOCAL_RETURN_AUDIT_EXIT_CODE"
