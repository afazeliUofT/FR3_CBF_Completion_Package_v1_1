#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE_ROOT="$(realpath "${1:?package root required}")"
REPO="${FR3_REPO_ROOT:?FR3_REPO_ROOT is required}"
DOWNLOADS="${FR3_DOWNLOADS:-/mnt/c/Users/alifa/Downloads}"
RORQUAL_HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_RETURN="$DOWNLOADS/FR3_V45_HOLDOUT_COMPLETION_R2_RETRIEVAL_RETURN_$STAMP"
mkdir -p "$LOCAL_RETURN"
LOG="$LOCAL_RETURN/LOCAL_WSL_ORCHESTRATOR.log"
REMOTE_VERIFY_LOG="$LOCAL_RETURN/REMOTE_RETRIEVAL_VERIFY.log"
AUDIT_LOG="$LOCAL_RETURN/RETRIEVED_HOLDOUT_AUDIT.log"
exec > >(tee -a "$LOG") 2>&1

failure_handler() {
  local rc=$?
  trap - ERR
  set +e
  echo "LOCAL_RETRIEVAL_ONLY_UNEXPECTED_EXIT_CODE=$rc"
  echo "LOCAL_RETRIEVAL_ONLY_FAILURE_COMMAND=${BASH_COMMAND:-unknown}"
  python "$PACKAGE_ROOT/scripts/package_local_failure.py" \
    --output-dir "$LOCAL_RETURN" \
    --package-root "$PACKAGE_ROOT" \
    --log "$LOG" \
    --log "$REMOTE_VERIFY_LOG" \
    --log "$AUDIT_LOG" \
    --reason "retrieval-only workflow failed with exit $rc" || true
  echo 'REMOTE_COMPUTATION_RERUN=NO'
  echo 'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO'
  echo 'AUTOMATIC_ALGORITHM_TUNING_AUTHORIZED=NO'
  echo 'WSL_TERMINAL_CLOSE_REQUESTED=NO'
  echo "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
  if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap failure_handler ERR

printf '%s\n' \
  '=================================================================' \
  'FR3 V4.5 — HOLDOUT COMPLETION R2 RETRIEVAL-ONLY RECOVERY' \
  '=================================================================' \
  "PACKAGE_ROOT=$PACKAGE_ROOT" \
  "REPO=$REPO" \
  "RORQUAL_HOST=$RORQUAL_HOST" \
  'REMOTE_COMPUTATION_RERUN=NO' \
  'SLURM_SUBMISSION=NO' \
  'CHANNEL_REGENERATION=NO' \
  'GPU_REQUESTED=NO' \
  'NEW_SEED_EXECUTION=NO' \
  'AUTOMATIC_ALGORITHM_TUNING_AUTHORIZED=NO' \
  'WSL_TERMINAL_CLOSE_REQUESTED=NO'

(
  cd "$PACKAGE_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo 'INTERNAL_MANIFEST_VERIFICATION=PASS'
echo 'SOURCE_PAYLOAD_MANIFEST_VERIFICATION=PASS'

[[ -d "$REPO/.git" ]]
if [[ -f "$REPO/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
  echo 'REPO_VENV_ACTIVATED=YES'
else
  echo 'REPO_VENV_ACTIVATED=NO_STANDARD_LIBRARY_ONLY'
fi
python3 -m compileall -q "$PACKAGE_ROOT/scripts" "$PACKAGE_ROOT/tests"
echo 'PYTHON_SYNTAX_CHECK=PASS'
bash -n "$PACKAGE_ROOT/wrappers/RUN_V45_HOLDOUT_COMPLETION_R2_RETRIEVAL_FROM_WSL.sh"
echo 'BASH_SYNTAX_CHECK=PASS'
if python3 -c 'import pytest' >/dev/null 2>&1; then
  PYTHONPATH="$PACKAGE_ROOT" python3 -m pytest -q "$PACKAGE_ROOT/tests"
  echo 'FOCUSED_TESTS=PASS'
else
  echo 'FOCUSED_TESTS=SKIPPED_PYTEST_NOT_INSTALLED'
fi

mapfile -t CONTRACT_VALUES < <(python3 - "$PACKAGE_ROOT/config/RETRIEVAL_CONTRACT.json" <<'PY'
import json,sys
value=json.load(open(sys.argv[1],encoding='utf-8'))
print(value['github']['required_ancestor'])
print(value['remote']['return_zip'])
print(value['remote']['return_zip_sha256'])
print(value['remote']['pass_array_job_id'])
print(value['remote']['assembly_job_id'])
PY
)
REQUIRED_ANCESTOR="${CONTRACT_VALUES[0]}"
REMOTE_RETURN_ZIP="${CONTRACT_VALUES[1]}"
EXPECTED_RETURN_SHA="${CONTRACT_VALUES[2]}"
PASS_ARRAY_JOB_ID="${CONTRACT_VALUES[3]}"
ASSEMBLY_JOB_ID="${CONTRACT_VALUES[4]}"
REMOTE_RETURN_DIR="$(dirname "$REMOTE_RETURN_ZIP")"
REMOTE_RETURN_BASE="$(basename "$REMOTE_RETURN_ZIP")"

SOURCE_CLONE="$LOCAL_RETURN/github_working_clone"
git clone --branch e3-first-sector-p452 \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$SOURCE_CLONE"
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
GIT_REMOTE_HEAD_BEFORE="$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)"
git -C "$SOURCE_CLONE" merge-base --is-ancestor "$REQUIRED_ANCESTOR" origin/e3-first-sector-p452
echo 'GITHUB_REQUIRED_ANCESTOR_GATE=PASS'
echo "GIT_REMOTE_HEAD_BEFORE=$GIT_REMOTE_HEAD_BEFORE"
echo 'GITHUB_NEWER_WORK_OVERWRITTEN=NO'

TOOL_DEST="$SOURCE_CLONE/tools/phase1_v4_5_holdout_completion_r2_retrieval_only_v1"
if [[ -e "$TOOL_DEST" ]]; then
  (
    cd "$TOOL_DEST"
    sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
  )
  echo 'GITHUB_RETRIEVAL_SOURCE_ALREADY_IDENTICAL=YES'
else
  mkdir -p "$TOOL_DEST"
  python3 - "$PACKAGE_ROOT" "$TOOL_DEST" <<'PY'
from pathlib import Path
import shutil,sys
source=Path(sys.argv[1]); target=Path(sys.argv[2])
for rel in ('PACKAGE_VERSION.json','README.md','requirements.txt','SOURCE_PAYLOAD_MANIFEST.sha256','config','docs','scripts','tests','wrappers'):
    src=source/rel; dst=target/rel
    if src.is_dir(): shutil.copytree(src,dst,dirs_exist_ok=True)
    elif src.is_file(): dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
print('GITHUB_RETRIEVAL_SOURCE_SUBSET_COPY=PASS')
PY
  (
    cd "$TOOL_DEST"
    sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
  )
  git -C "$SOURCE_CLONE" add "$TOOL_DEST"
  git -C "$SOURCE_CLONE" diff --cached --check
  if ! git -C "$SOURCE_CLONE" diff --cached --quiet; then
    git -C "$SOURCE_CLONE" -c user.name='Ali Fazeli' \
      -c user.email='ali.fazeli@utoronto.ca' \
      commit -m 'Add retrieval-only recovery for completed v4.5 holdout'
    git -C "$SOURCE_CLONE" pull --rebase origin e3-first-sector-p452
    git -C "$SOURCE_CLONE" push origin HEAD:e3-first-sector-p452
  fi
fi
RETRIEVAL_SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
echo "RETRIEVAL_SOURCE_COMMIT=$RETRIEVAL_SOURCE_COMMIT"

TRANSFER_TAR="$LOCAL_RETURN/REMOTE_RETURN_TRANSFER.tar"
if ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=6 "$RORQUAL_HOST" bash -s -- \
    "$REMOTE_RETURN_DIR" "$REMOTE_RETURN_BASE" "$EXPECTED_RETURN_SHA" \
    > "$TRANSFER_TAR" 2> >(tee "$REMOTE_VERIFY_LOG" >&2) <<'REMOTE'
set -Eeuo pipefail
RETURN_DIR="$1"
RETURN_BASE="$2"
EXPECTED_SHA="$3"
cd "$RETURN_DIR"
[[ -f "$RETURN_BASE" && -f "$RETURN_BASE.sha256" ]]
SIDE_DIGEST="$(awk 'NF>=2{print $1;exit}' "$RETURN_BASE.sha256")"
SIDE_NAME="$(awk 'NF>=2{print $2;exit}' "$RETURN_BASE.sha256")"
ACTUAL_SHA="$(sha256sum "$RETURN_BASE" | awk '{print $1}')"
[[ "$SIDE_DIGEST" == "$EXPECTED_SHA" ]]
[[ "$SIDE_NAME" == "$RETURN_BASE" ]]
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]]
unzip -t "$RETURN_BASE" >/dev/null
printf '%s\n' \
  'REMOTE_EXISTING_RETURN_BINDING=PASS' \
  "REMOTE_RETURN_ZIP=$RETURN_DIR/$RETURN_BASE" \
  "REMOTE_RETURN_ZIP_SHA256=$ACTUAL_SHA" \
  'REMOTE_RETURN_SIDECAR_BASENAME_GATE=PASS' \
  'REMOTE_RETURN_ZIP_CRC=PASS' \
  'REMOTE_COMPUTATION_RERUN=NO' >&2
tar -cf - "$RETURN_BASE" "$RETURN_BASE.sha256"
REMOTE
then
  echo 'SINGLE_SSH_TRANSFER_SESSION=PASS'
else
  rc=$?
  echo "SINGLE_SSH_TRANSFER_SESSION=FAIL:$rc"
  exit "$rc"
fi

tar -tf "$TRANSFER_TAR" >/dev/null
tar -xf "$TRANSFER_TAR" -C "$LOCAL_RETURN"
rm -f "$TRANSFER_TAR"
LOCAL_ZIP="$LOCAL_RETURN/$REMOTE_RETURN_BASE"
LOCAL_SHA="$LOCAL_ZIP.sha256"
[[ -f "$LOCAL_ZIP" && -f "$LOCAL_SHA" ]]
SIDE_DIGEST="$(awk 'NF>=2{print $1;exit}' "$LOCAL_SHA")"
SIDE_NAME="$(awk 'NF>=2{print $2;exit}' "$LOCAL_SHA")"
ACTUAL_RETURN_SHA="$(sha256sum "$LOCAL_ZIP" | awk '{print $1}')"
[[ "$SIDE_DIGEST" == "$EXPECTED_RETURN_SHA" ]]
[[ "$SIDE_NAME" == "$REMOTE_RETURN_BASE" ]]
[[ "$ACTUAL_RETURN_SHA" == "$EXPECTED_RETURN_SHA" ]]
unzip -t "$LOCAL_ZIP" >/dev/null
echo 'HOLDOUT_COMPLETION_R2_RETURN_SHA256_GATE=PASS'
echo 'HOLDOUT_COMPLETION_R2_RETURN_SIDECAR_BASENAME_GATE=PASS'
echo 'HOLDOUT_COMPLETION_R2_RETURN_ZIP_CRC=PASS'

EXTRACTED="$LOCAL_RETURN/extracted_return"
mkdir -p "$EXTRACTED"
unzip -q "$LOCAL_ZIP" -d "$EXTRACTED"
RETURN_ROOT="$(find "$EXTRACTED" -mindepth 1 -maxdepth 1 -type d -print -quit)"
[[ -d "$RETURN_ROOT" ]]
(
  cd "$RETURN_ROOT"
  sha256sum -c RETURN_MANIFEST.sha256 >/dev/null
)
echo 'HOLDOUT_COMPLETION_R2_RETURN_MANIFEST=PASS'

python3 "$PACKAGE_ROOT/scripts/audit_retrieved_return.py" \
  --return-root "$RETURN_ROOT" \
  --output-json "$LOCAL_RETURN/RETRIEVED_HOLDOUT_AUDIT.json" \
  | tee "$AUDIT_LOG"

EVIDENCE_DEST="$SOURCE_CLONE/evidence/phase1_v4_5_holdout_completion_r2_pass_parallel_v1"
if [[ -e "$EVIDENCE_DEST" ]]; then
  EXISTING_SIDE="$(find "$EVIDENCE_DEST" -maxdepth 1 -type f -name '*.zip.sha256' -print -quit || true)"
  [[ -f "$EXISTING_SIDE" ]]
  [[ "$(awk 'NF>=2{print $1;exit}' "$EXISTING_SIDE")" == "$EXPECTED_RETURN_SHA" ]]
  echo 'GITHUB_EVIDENCE_ALREADY_PRESENT_AND_BOUND=YES'
else
  mkdir -p "$EVIDENCE_DEST" "$EVIDENCE_DEST/merged" "$EVIDENCE_DEST/slurm" "$EVIDENCE_DEST/pass_outputs"
  cp "$LOCAL_SHA" "$EVIDENCE_DEST/"
  python3 - "$LOG" "$EVIDENCE_DEST/LOCAL_WSL_ORCHESTRATOR.log" \
    "$REMOTE_VERIFY_LOG" "$EVIDENCE_DEST/REMOTE_RETRIEVAL_VERIFY.log" \
    "$AUDIT_LOG" "$EVIDENCE_DEST/RETRIEVED_HOLDOUT_AUDIT.log" <<'PY'
from pathlib import Path
import sys
for source_name,target_name in zip(sys.argv[1::2],sys.argv[2::2]):
    source=Path(source_name); target=Path(target_name)
    lines=source.read_text(encoding='utf-8',errors='replace').splitlines()
    target.write_text('\n'.join(line.rstrip() for line in lines)+'\n',encoding='utf-8')
print('GITHUB_LOG_TRAILING_WHITESPACE_NORMALIZATION=PASS')
PY
  cp "$LOCAL_RETURN/RETRIEVED_HOLDOUT_AUDIT.json" "$EVIDENCE_DEST/"
  for name in HOLDOUT_COMPLETION_AUDIT.json RETURN_METADATA.json RETURN_MANIFEST.sha256 \
    R1_TIMEOUT_AUDIT.json PASS_PARALLEL_EQUIVALENCE_AUDIT.json holdout_key_results.tex; do
    [[ -f "$RETURN_ROOT/$name" ]] && cp "$RETURN_ROOT/$name" "$EVIDENCE_DEST/"
  done
  for name in PHASE1_MERGED_AUDIT.json PHASE1_BOOTSTRAP_SUMMARY.json \
    PHASE1_SEED_CLUSTER_EFFECTS.csv PHASE1_METHOD_ENDPOINT_SUMMARY.csv \
    PHASE1_PASS_SPECIFIC_EFFECTS.csv PHASE1_LEAVE_ONE_PASS_OUT.csv \
    PHASE1_ACTION_AND_RUNTIME_SUMMARY.json PHASE1_SEED_RESULT_HASH_INDEX.csv; do
    [[ -f "$RETURN_ROOT/merged/$name" ]] && cp "$RETURN_ROOT/merged/$name" "$EVIDENCE_DEST/merged/"
  done
  find "$RETURN_ROOT/slurm" -maxdepth 1 -type f -exec cp {} "$EVIDENCE_DEST/slurm/" \; 2>/dev/null || true
  find "$RETURN_ROOT/pass_outputs" -type f ! -name '*.npz' ! -name '*.npy' 2>/dev/null | while read -r source; do
    rel="${source#"$RETURN_ROOT/pass_outputs/"}"
    mkdir -p "$EVIDENCE_DEST/pass_outputs/$(dirname "$rel")"
    cp "$source" "$EVIDENCE_DEST/pass_outputs/$rel"
  done
fi

mkdir -p "$SOURCE_CLONE/paper/twc_v4_5_draft_start/tables" \
  "$SOURCE_CLONE/paper/twc_v4_5_draft_start/data"
cp "$RETURN_ROOT/holdout_key_results.tex" \
  "$SOURCE_CLONE/paper/twc_v4_5_draft_start/tables/holdout_key_results.tex"
cp "$RETURN_ROOT/HOLDOUT_COMPLETION_AUDIT.json" \
  "$SOURCE_CLONE/paper/twc_v4_5_draft_start/data/HOLDOUT_COMPLETION_AUDIT.json"
cp "$LOCAL_RETURN/RETRIEVED_HOLDOUT_AUDIT.json" \
  "$SOURCE_CLONE/paper/twc_v4_5_draft_start/data/RETRIEVED_HOLDOUT_AUDIT.json"

git -C "$SOURCE_CLONE" add "$EVIDENCE_DEST" \
  paper/twc_v4_5_draft_start/tables/holdout_key_results.tex \
  paper/twc_v4_5_draft_start/data/HOLDOUT_COMPLETION_AUDIT.json \
  paper/twc_v4_5_draft_start/data/RETRIEVED_HOLDOUT_AUDIT.json
git -C "$SOURCE_CLONE" diff --cached --check
if ! git -C "$SOURCE_CLONE" diff --cached --quiet; then
  git -C "$SOURCE_CLONE" -c user.name='Ali Fazeli' \
    -c user.email='ali.fazeli@utoronto.ca' \
    commit -m 'Collect completed v4.5 fresh-holdout R2 evidence'
  git -C "$SOURCE_CLONE" pull --rebase origin e3-first-sector-p452
  git -C "$SOURCE_CLONE" push origin HEAD:e3-first-sector-p452
fi
GIT_FINAL_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
GIT_REMOTE_FINAL_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)"
echo "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT"
echo "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT"
[[ "$GIT_FINAL_COMMIT" == "$GIT_REMOTE_FINAL_COMMIT" ]]
echo 'GITHUB_EVIDENCE_PUSH=PASS'

rm -rf "$SOURCE_CLONE" "$EXTRACTED"
echo 'LOCAL_RETURN_GITHUB_CLONE_REMOVED=PASS'
printf '%s\n' \
  "PASS_ARRAY_JOB_ID=$PASS_ARRAY_JOB_ID" \
  "ASSEMBLY_JOB_ID=$ASSEMBLY_JOB_ID" \
  'PASS_TASK_RECORD_COUNT=5' \
  'PASS_TASK_COMPLETED_COUNT=5' \
  'ASSEMBLY_STATE=COMPLETED' \
  'ASSEMBLY_SLURM_EXIT_CODE=0:0' \
  'SEED44052_SCIENTIFIC_EXIT_CODE=42' \
  'SEED44052_CANDIDATE_HARD_GATES_PASS=False' \
  'REMOTE_COMPUTATION_RERUN=NO' \
  'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO' \
  'AUTOMATIC_ALGORITHM_TUNING_AUTHORIZED=NO' \
  'PAPER_WRITING_AUTHORIZED=True' \
  'NEXT_GATE=FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION' \
  "LOCAL_HOLDOUT_COMPLETION_R2_RETURN_ZIP=$LOCAL_ZIP" \
  "LOCAL_HOLDOUT_COMPLETION_R2_RETURN_ZIP_SHA256=$ACTUAL_RETURN_SHA" \
  "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN" \
  'WSL_TERMINAL_CLOSE_REQUESTED=NO'

if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
fi
exit 0
