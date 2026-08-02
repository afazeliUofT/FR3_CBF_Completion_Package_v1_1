#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE_ROOT="${1:?package root required}"
: "${FR3_REPO_ROOT:?FR3_REPO_ROOT required}"
: "${FR3_DOWNLOADS:?FR3_DOWNLOADS required}"
: "${FR3_V44_SCHED_ARCHIVE_PATH:?FR3_V44_SCHED_ARCHIVE_PATH required}"
: "${FR3_V44_SCHED_ARCHIVE_SHA256:?FR3_V44_SCHED_ARCHIVE_SHA256 required}"
RORQUAL_HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
RORQUAL_SCRATCH_LINK="${FR3_RORQUAL_SCRATCH_LINK:-/home/rsadve1/links/scratch}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
RETURN_DIR="$FR3_DOWNLOADS/FR3_V44_PROTECTED_SUBBAND_SCHEDULING_RETURN_$STAMP"
RUN_ROOT="$HOME/fr3_v44_protected_subband_scheduling_runs/$STAMP"
mkdir -p "$RETURN_DIR" "$RUN_ROOT"
LOG="$RETURN_DIR/LOCAL_WSL_ORCHESTRATOR.log"
exec > >(tee -a "$LOG") 2>&1

package_local_failure() {
  local rc="${1:-1}"
  local stage="${2:-UNEXPECTED_LOCAL_FAILURE}"
  rm -rf "$RETURN_DIR/github_source_clone" "$RETURN_DIR/github_evidence_clone" "$RETURN_DIR/evidence_extract" || true
  local name="FR3_V44_PROTECTED_SUBBAND_SCHEDULING_LOCAL_FAILURE_$STAMP"
  local temp="$RUN_ROOT/$name"
  rm -rf "$temp"; mkdir -p "$temp"
  cp -a "$RETURN_DIR/." "$temp/" 2>/dev/null || true
  printf '%s\n' \
    "LOCAL_FAILURE_STAGE=$stage" \
    "LOCAL_FAILURE_EXIT_CODE=$rc" \
    "CHANNEL_REGENERATION=NO" \
    "GPU_REQUESTED=NO" \
    "CAMPAIGN_RERUN_AUTHORIZED=NO" > "$temp/LOCAL_FAILURE_STATUS.env"
  (cd "$RUN_ROOT" && zip -qr "$RETURN_DIR/$name.zip" "$name") || true
  if [[ -f "$RETURN_DIR/$name.zip" ]]; then
    local digest
    digest="$(sha256sum "$RETURN_DIR/$name.zip" | awk '{print $1}')"
    printf '%s  %s\n' "$digest" "$name.zip" > "$RETURN_DIR/$name.zip.sha256"
    echo "LOCAL_FAILURE_RETURN_ZIP=$RETURN_DIR/$name.zip"
    echo "LOCAL_FAILURE_RETURN_ZIP_SHA256=$digest"
  fi
}

unexpected_failure() {
  local rc=$?
  trap - ERR
  package_local_failure "$rc" "${BASH_COMMAND:-UNKNOWN_COMMAND}"
  printf '%s\n' \
    "LOCAL_WRAPPER_STATUS=UNEXPECTED_FAILURE" \
    "LOCAL_WRAPPER_EXIT_CODE=$rc" \
    "FILES_TO_RETURN_FOLDER=$RETURN_DIR" \
    "WSL_TERMINAL_CLOSE_REQUESTED=NO"
  if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    explorer.exe "$(wslpath -w "$RETURN_DIR")" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap unexpected_failure ERR

printf '%s\n' \
  "=================================================================" \
  "FR3 CANDIDATE V4.4 — PROTECTED-SUBBAND SCHEDULING DEVELOPMENT" \
  "=================================================================" \
  "PACKAGE_ROOT=$PACKAGE_ROOT" \
  "REPO=$FR3_REPO_ROOT" \
  "RORQUAL_HOST=$RORQUAL_HOST" \
  "FAILED_SEED_COUNT=11" \
  "CHANNEL_REGENERATION=NO" \
  "GPU_REQUESTED=NO" \
  "WORKER_WALLTIME=00:10:00" \
  "WORKER_MEMORY=16G" \
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

REPO="$FR3_REPO_ROOT"
if [[ -x "$REPO/.venv/bin/python" ]]; then
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
else
  python3 -m venv "$REPO/.venv"
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
fi
PYTHON="$(command -v python)"
echo "REPO_VENV_ACTIVATED=YES"
"$PYTHON" -m pip install -q -r "$PACKAGE_ROOT/requirements.txt"
"$PYTHON" -m pip check
echo "LOCAL_VENV_DEPENDENCY_GATE=PASS"

"$PYTHON" - "$PACKAGE_ROOT" <<'PY_SYNTAX'
from pathlib import Path
import ast,sys
root=Path(sys.argv[1])
files=sorted(root.rglob('*.py'))
for path in files:
    ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
print('PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS')
print(f'PYTHON_SYNTAX_FILE_COUNT={len(files)}')
PY_SYNTAX
for script in "$PACKAGE_ROOT"/wrappers/*.sh; do bash -n "$script"; done
echo "BASH_SYNTAX_CHECK=PASS"
PYTHONPATH="$PACKAGE_ROOT/src" "$PYTHON" -m pytest -q "$PACKAGE_ROOT/tests"

LOCAL_AUDIT_DIR="$RETURN_DIR/local_audit"
mkdir -p "$LOCAL_AUDIT_DIR"
"$PYTHON" "$PACKAGE_ROOT/scripts/audit_failed_seed_diagnosis.py" \
  --diagnosis-zip "$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_18150465.zip" \
  --output-json "$LOCAL_AUDIT_DIR/IMMUTABLE_FAILED_SEED_DIAGNOSIS_AUDIT.json" \
  | tee "$LOCAL_AUDIT_DIR/IMMUTABLE_FAILED_SEED_DIAGNOSIS_AUDIT.log"
"$PYTHON" "$PACKAGE_ROOT/scripts/audit_scheduling_necessity.py" \
  --diagnosis-zip "$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_3_FAILED_SEED_DIAGNOSIS_18150465.zip" \
  --output-json "$LOCAL_AUDIT_DIR/SCHEDULING_NECESSITY_AND_PLAUSIBILITY_AUDIT.json" \
  | tee "$LOCAL_AUDIT_DIR/SCHEDULING_NECESSITY_AND_PLAUSIBILITY_AUDIT.log"
echo "LOCAL_QUALITY_GATE=PASS"

SOURCE_CLONE="$RETURN_DIR/github_source_clone"
git clone --branch e3-first-sector-p452 --single-branch \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$SOURCE_CLONE"
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
GIT_HEAD_BEFORE="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
GIT_REMOTE_HEAD_BEFORE="$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)"
git -C "$SOURCE_CLONE" merge-base --is-ancestor \
  b6caac8ec0ca61e8e397959b169cc473a11ffa87 \
  origin/e3-first-sector-p452
echo "GITHUB_REQUIRED_ANCESTOR_GATE=PASS"
echo "GIT_HEAD_BEFORE=$GIT_HEAD_BEFORE"
echo "GIT_REMOTE_HEAD_BEFORE=$GIT_REMOTE_HEAD_BEFORE"
echo "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

SOURCE_DEST="$SOURCE_CLONE/tools/phase1_v4_4_protected_subband_scheduling_development_v1"
if [[ -e "$SOURCE_DEST" ]]; then
  if diff -qr "$PACKAGE_ROOT/github_payload" "$SOURCE_DEST" >/dev/null; then
    V44_SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
    echo "V44_SCHEDULING_SOURCE_ALREADY_IDENTICAL=YES"
  else
    echo "ERROR_EXISTING_V44_SOURCE_PATH_DIFFERS=$SOURCE_DEST"
    false
  fi
else
  mkdir -p "$SOURCE_DEST"
  cp -a "$PACKAGE_ROOT/github_payload/." "$SOURCE_DEST/"
  git -C "$SOURCE_CLONE" add "tools/phase1_v4_4_protected_subband_scheduling_development_v1"
  git -C "$SOURCE_CLONE" diff --cached --check
  git -C "$SOURCE_CLONE" -c user.name='Ali Fazeli' -c user.email='ali.fazeli@utoronto.ca' \
    commit -m 'Add candidate-v4.4 protected-subband scheduling development'
  git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
  [[ "$(git -C "$SOURCE_CLONE" rev-parse HEAD^)" == "$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)" ]]
  git -C "$SOURCE_CLONE" push origin HEAD:e3-first-sector-p452
  V44_SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
fi
echo "V44_SCHEDULING_SOURCE_COMMIT=$V44_SOURCE_COMMIT"

CONTROL_PATH="/tmp/fr3-v44-sched-${UID}-$$"
SSH_OPTS=(-o ControlMaster=auto -o ControlPersist=12h -o ControlPath="$CONTROL_PATH" -o ServerAliveInterval=60 -o ServerAliveCountMax=120)
ssh "${SSH_OPTS[@]}" -fnNT "$RORQUAL_HOST"
REMOTE_UPLOAD="$RORQUAL_SCRATCH_LINK/FR3_V44_SCHED_${FR3_V44_SCHED_ARCHIVE_SHA256:0:12}.zip"
REMOTE_ORCH="$RORQUAL_SCRATCH_LINK/FR3_REMOTE_V44_SCHED_${FR3_V44_SCHED_ARCHIVE_SHA256:0:12}.sh"
scp "${SSH_OPTS[@]}" "$FR3_V44_SCHED_ARCHIVE_PATH" "$RORQUAL_HOST:$REMOTE_UPLOAD"
scp "${SSH_OPTS[@]}" "$PACKAGE_ROOT/wrappers/REMOTE_ORCHESTRATE_V44_SCHEDULING_DEVELOPMENT.sh" "$RORQUAL_HOST:$REMOTE_ORCH"

REMOTE_LOG="$RETURN_DIR/REMOTE_V44_SCHEDULING.log"
RUN_TAG="${FR3_V44_SCHED_ARCHIVE_SHA256:0:12}"
if ssh "${SSH_OPTS[@]}" "$RORQUAL_HOST" \
  "env REMOTE_PACKAGE_ZIP='$REMOTE_UPLOAD' EXPECTED_PACKAGE_SHA256='$FR3_V44_SCHED_ARCHIVE_SHA256' RUN_TAG='$RUN_TAG' bash '$REMOTE_ORCH'" \
  2>&1 | tee "$REMOTE_LOG"; then
  REMOTE_WRAPPER_EXIT_CODE=0
else
  REMOTE_WRAPPER_EXIT_CODE="${PIPESTATUS[0]}"
fi
echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE"

REMOTE_RETURN_ZIP="$(grep '^REMOTE_RETURN_ZIP=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
REMOTE_RETURN_SHA="$(grep '^REMOTE_RETURN_ZIP_SHA256=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
if [[ -z "$REMOTE_RETURN_ZIP" || -z "$REMOTE_RETURN_SHA" ]]; then
  ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true
  package_local_failure 90 "REMOTE_RETURN_PATH_NOT_PRINTED"
  false
fi
LOCAL_RETURN_ZIP="$RETURN_DIR/$(basename "$REMOTE_RETURN_ZIP")"
if scp "${SSH_OPTS[@]}" "$RORQUAL_HOST:$REMOTE_RETURN_ZIP" "$LOCAL_RETURN_ZIP" && \
   scp "${SSH_OPTS[@]}" "$RORQUAL_HOST:$REMOTE_RETURN_ZIP.sha256" "$LOCAL_RETURN_ZIP.sha256"; then
  DIAGNOSTIC_RETRIEVAL_EXIT_CODE=0
else
  DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$?
fi
ssh "${SSH_OPTS[@]}" -O exit "$RORQUAL_HOST" >/dev/null 2>&1 || true
echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE"
[[ "$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" -eq 0 ]]

"$PYTHON" - "$LOCAL_RETURN_ZIP.sha256" "$(basename "$LOCAL_RETURN_ZIP")" "$REMOTE_RETURN_SHA" <<'PY_SIDECAR'
from pathlib import Path
import sys
path=Path(sys.argv[1]); expected_name=sys.argv[2]; expected_hash=sys.argv[3]
lines=path.read_text(encoding='utf-8').splitlines(); assert len(lines)==1
parts=lines[0].split(); assert len(parts)==2
assert parts[0]==expected_hash and parts[1]==expected_name and Path(parts[1]).name==parts[1]
print('RETURN_SIDECAR_BASENAME_GATE=PASS')
PY_SIDECAR
[[ "$(sha256sum "$LOCAL_RETURN_ZIP" | awk '{print $1}')" == "$REMOTE_RETURN_SHA" ]]
(cd "$RETURN_DIR" && sha256sum -c "$(basename "$LOCAL_RETURN_ZIP.sha256")" >/dev/null)
unzip -t "$LOCAL_RETURN_ZIP" >/dev/null

RETURN_VERIFY_JSON="$RETURN_DIR/V44_SCHEDULING_RETURN_VERIFICATION.json"
"$PYTHON" "$PACKAGE_ROOT/scripts/verify_v44_scheduling_return.py" \
  --return-zip "$LOCAL_RETURN_ZIP" \
  --expected-sha256 "$REMOTE_RETURN_SHA" \
  --output-json "$RETURN_VERIFY_JSON" \
  | tee "$RETURN_DIR/V44_SCHEDULING_RETURN_VERIFICATION.log"
RETURN_VERIFICATION_EXIT_CODE=0

EVIDENCE_EXTRACT="$RETURN_DIR/evidence_extract"
mkdir -p "$EVIDENCE_EXTRACT"
unzip -q "$LOCAL_RETURN_ZIP" -d "$EVIDENCE_EXTRACT"
EVIDENCE_ROOT="$(find "$EVIDENCE_EXTRACT" -mindepth 1 -maxdepth 1 -type d -print -quit)"
EVIDENCE_CLONE="$RETURN_DIR/github_evidence_clone"
git clone --branch e3-first-sector-p452 --single-branch \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$EVIDENCE_CLONE"
git -C "$EVIDENCE_CLONE" merge-base --is-ancestor "$V44_SOURCE_COMMIT" HEAD
ARRAY_JOB_ID="$(grep '^ARRAY_JOB_ID=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
EVIDENCE_DEST="$EVIDENCE_CLONE/evidence/phase1_v4_4_protected_subband_scheduling_development_v1_job_${ARRAY_JOB_ID:-UNKNOWN}"
EVIDENCE_ALREADY_IDENTICAL=NO
if [[ -e "$EVIDENCE_DEST" ]]; then
  existing_sidecar="$EVIDENCE_DEST/$(basename "$LOCAL_RETURN_ZIP").sha256"
  existing_hash="$(awk 'NF>=1 {print $1; exit}' "$existing_sidecar" 2>/dev/null || true)"
  if [[ "$existing_hash" == "$REMOTE_RETURN_SHA" ]]; then
    EVIDENCE_ALREADY_IDENTICAL=YES
    echo "V44_SCHEDULING_EVIDENCE_ALREADY_IDENTICAL=YES"
  else
    echo "ERROR_GITHUB_EVIDENCE_PATH_ALREADY_EXISTS_WITH_DIFFERENT_BINDING=$EVIDENCE_DEST"
    false
  fi
else
  mkdir -p "$EVIDENCE_DEST"
  for folder in bindings audits merged slurm logs; do
    [[ -d "$EVIDENCE_ROOT/$folder" ]] && cp -a "$EVIDENCE_ROOT/$folder" "$EVIDENCE_DEST/"
  done
  mkdir -p "$EVIDENCE_DEST/seed_summaries"
  for seed_dir in "$EVIDENCE_ROOT"/seed_results/seed_*; do
    [[ -d "$seed_dir" ]] || continue
    dst="$EVIDENCE_DEST/seed_summaries/$(basename "$seed_dir")"
    mkdir -p "$dst"
    for name in V44_SCHEDULING_SEED_RESULT.json CELL_SUMMARY.csv PRIMARY_PAIRED_EFFECTS.csv RESULT_FILE_MANIFEST.json TASK_STATUS.json process_exit_code.txt stdout.log stderr.log; do
      [[ -f "$seed_dir/result/$name" ]] && cp "$seed_dir/result/$name" "$dst/$name"
      [[ -f "$seed_dir/$name" ]] && cp "$seed_dir/$name" "$dst/$name"
    done
  done
  cp "$EVIDENCE_ROOT/RETURN_METADATA.json" "$EVIDENCE_DEST/"
  cp "$RETURN_VERIFY_JSON" "$EVIDENCE_DEST/"
  printf '%s  %s\n' "$REMOTE_RETURN_SHA" "$(basename "$LOCAL_RETURN_ZIP")" > "$EVIDENCE_DEST/$(basename "$LOCAL_RETURN_ZIP").sha256"
  sed 's/[[:space:]]\+$//' "$LOG" > "$EVIDENCE_DEST/LOCAL_WSL_ORCHESTRATOR.log"
fi
"$PYTHON" - "$EVIDENCE_DEST" <<'PY_NORMALIZE'
from pathlib import Path
import sys
root=Path(sys.argv[1])
for path in root.rglob('*'):
    if not path.is_file():
        continue
    data=path.read_bytes()
    if b'\x00' in data:
        continue
    try:
        text=data.decode('utf-8')
    except UnicodeDecodeError:
        continue
    had_newline=text.endswith('\n')
    lines=[line.rstrip() for line in text.splitlines()]
    normalized='\n'.join(lines) + ('\n' if had_newline else '')
    path.write_text(normalized,encoding='utf-8')
print('GITHUB_TEXT_NORMALIZATION=PASS')
PY_NORMALIZE
if [[ "$EVIDENCE_ALREADY_IDENTICAL" == "NO" ]]; then
  git -C "$EVIDENCE_CLONE" add "evidence/$(basename "$EVIDENCE_DEST")"
  git -C "$EVIDENCE_CLONE" diff --cached --check
  git -C "$EVIDENCE_CLONE" -c user.name='Ali Fazeli' -c user.email='ali.fazeli@utoronto.ca' \
    commit -m 'Collect candidate-v4.4 protected-subband scheduling development evidence'
  git -C "$EVIDENCE_CLONE" fetch origin e3-first-sector-p452
  [[ "$(git -C "$EVIDENCE_CLONE" rev-parse HEAD^)" == "$(git -C "$EVIDENCE_CLONE" rev-parse origin/e3-first-sector-p452)" ]]
  git -C "$EVIDENCE_CLONE" push origin HEAD:e3-first-sector-p452
fi
GIT_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" rev-parse HEAD)"
GIT_REMOTE_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" ls-remote origin refs/heads/e3-first-sector-p452 | awk '{print $1}')"
[[ "$GIT_FINAL_COMMIT" == "$GIT_REMOTE_FINAL_COMMIT" ]]

SUMMARY="$EVIDENCE_ROOT/merged/V44_SCHEDULING_DEVELOPMENT_SUMMARY.json"
if [[ -f "$SUMMARY" ]]; then
  mapfile -t SUMMARY_VALUES < <("$PYTHON" - "$SUMMARY" <<'PY_SUM'
import json,sys
j=json.load(open(sys.argv[1],encoding='utf-8'))
for key in (
 'status','failed_seed_hard_gate_pass_count','failed_seed_bounded_scope_pass_count',
 'original_v4_3_unresolved_interval_count','scheduling_success_interval_count',
 'scheduling_failure_interval_count','candidate_floor_violation_user_seconds',
 'candidate_floor_violation_user_intervals','candidate_long_eess_violation_seconds',
 'candidate_short_eess_violation_seconds','maximum_protected_subband_scheduled_fraction',
 'maximum_schedule_mutable_sector_count','all30_development_primary_candidate_minus_static',
 'next_repair_decision','next_gate'):
 print(f"{key}={j.get(key)}")
PY_SUM
  )
  printf '%s\n' "${SUMMARY_VALUES[@]}"
fi

rm -rf "$SOURCE_CLONE" "$EVIDENCE_CLONE" "$EVIDENCE_EXTRACT"
echo "LOCAL_RETURN_GITHUB_CLONES_REMOVED=PASS"
MERGE_JOB_ID="$(grep '^MERGE_JOB_ID=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
MERGE_STATE="$(grep '^MERGE_STATE=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
MERGE_EXIT_CODE="$(grep '^MERGE_EXIT_CODE=' "$REMOTE_LOG" | tail -n 1 | cut -d= -f2-)"
NEXT_REPAIR_DECISION="$($PYTHON - "$RETURN_VERIFY_JSON" <<'PY_DEC'
import json,sys
j=json.load(open(sys.argv[1],encoding='utf-8'))
print(j.get('next_repair_decision') or 'REVIEW_RETURN')
PY_DEC
)"
NEXT_GATE="$($PYTHON - "$RETURN_VERIFY_JSON" <<'PY_GATE'
import json,sys
j=json.load(open(sys.argv[1],encoding='utf-8'))
print(j.get('next_gate') or 'REVIEW_RETURN')
PY_GATE
)"

printf '%s\n' \
  "=================================================================" \
  "FR3 V4.4 SCHEDULING DEVELOPMENT FINAL REPORT" \
  "=================================================================" \
  "LOCAL_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE" \
  "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE" \
  "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE" \
  "RETURN_VERIFICATION_EXIT_CODE=$RETURN_VERIFICATION_EXIT_CODE" \
  "ARRAY_JOB_ID=${ARRAY_JOB_ID:-UNKNOWN}" \
  "MERGE_JOB_ID=${MERGE_JOB_ID:-UNKNOWN}" \
  "MERGE_STATE=${MERGE_STATE:-UNKNOWN}" \
  "MERGE_EXIT_CODE=${MERGE_EXIT_CODE:-UNKNOWN}" \
  "LOCAL_RETURN_ZIP=$LOCAL_RETURN_ZIP" \
  "LOCAL_RETURN_ZIP_SHA256=$REMOTE_RETURN_SHA" \
  "V44_SCHEDULING_SOURCE_COMMIT=$V44_SOURCE_COMMIT" \
  "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT" \
  "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT" \
  "GITHUB_NEWER_WORK_OVERWRITTEN=NO" \
  "NEXT_REPAIR_DECISION=$NEXT_REPAIR_DECISION" \
  "NEXT_GATE=$NEXT_GATE" \
  "CHANNEL_REGENERATION=NO" \
  "GPU_REQUESTED=NO" \
  "WORKER_WALLTIME=00:10:00" \
  "MERGE_WALLTIME=00:05:00" \
  "CAMPAIGN_RERUN_AUTHORIZED=NO" \
  "FILES_TO_RETURN_FOLDER=$RETURN_DIR" \
  "WSL_TERMINAL_CLOSE_REQUESTED=NO"

if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$RETURN_DIR")" >/dev/null 2>&1 || true
fi
exit "$REMOTE_WRAPPER_EXIT_CODE"
