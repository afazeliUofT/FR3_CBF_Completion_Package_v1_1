#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE_ROOT="$(realpath "$1")"
REPO="$(realpath "${FR3_REPO_ROOT:?FR3_REPO_ROOT is required}")"
DOWNLOADS="${FR3_DOWNLOADS:-/mnt/c/Users/alifa/Downloads}"
RORQUAL_HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
ARCHIVE="$(realpath "${FR3_COMPLETION_R2_ARCHIVE_PATH:?FR3_COMPLETION_R2_ARCHIVE_PATH is required}")"
ARCHIVE_SHA="${FR3_COMPLETION_R2_ARCHIVE_SHA256:?FR3_COMPLETION_R2_ARCHIVE_SHA256 is required}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_RETURN="$DOWNLOADS/FR3_V45_HOLDOUT_COMPLETION_R2_RETURN_$STAMP"
LOG="$LOCAL_RETURN/LOCAL_WSL_ORCHESTRATOR.log"
mkdir -p "$LOCAL_RETURN"
exec > >(tee -a "$LOG") 2>&1

fail_with_code() { return "$1"; }

local_failure() {
  local rc=$?
  trap - ERR
  set +e
  local archive="$LOCAL_RETURN/FR3_V45_HOLDOUT_COMPLETION_R2_LOCAL_FAILURE_$STAMP.zip"
  python3 - "$archive" "$LOCAL_RETURN" "$PACKAGE_ROOT" "$rc" <<'PY'
from pathlib import Path
import hashlib,json,sys,tempfile,zipfile,shutil
archive=Path(sys.argv[1]); local=Path(sys.argv[2]); package=Path(sys.argv[3]); rc=int(sys.argv[4])
name=archive.stem
with tempfile.TemporaryDirectory(prefix='fr3-v45-r2-local-failure-') as td:
    payload=Path(td)/name; payload.mkdir()
    (payload/'FAILURE_METADATA.json').write_text(json.dumps({
      'schema_version':1,'status':'LOCAL_HOLDOUT_COMPLETION_R2_FAILURE',
      'exit_code':rc,'seed_scope':[44052],'new_seeds_authorized':False,
      'channel_regenerated':False,'gpu_requested':False,
      'terminal_close_requested':False,
    },indent=2,sort_keys=True)+'\n',encoding='utf-8')
    for source in sorted(local.glob('*')):
        if source.is_file() and source != archive and not source.name.endswith('.zip'):
            try: shutil.copy2(source,payload/source.name)
            except OSError: pass
    for rel in ('PACKAGE_VERSION.json','config/HOLDOUT_COMPLETION_R2_CONTRACT.json'):
        source=package/rel
        if source.is_file():
            target=payload/'package'/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
    lines=[]
    for source in sorted(payload.rglob('*')):
        if source.is_file() and source.name!='RETURN_MANIFEST.sha256':
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            lines.append(f'{digest}  {source.relative_to(payload).as_posix()}\n')
    (payload/'RETURN_MANIFEST.sha256').write_text(''.join(lines),encoding='utf-8')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zf:
        for source in sorted(payload.rglob('*')):
            if source.is_file(): zf.write(source,source.relative_to(Path(td)).as_posix())
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
Path(str(archive)+'.sha256').write_text(f'{digest}  {archive.name}\n',encoding='utf-8')
PY
  printf '%s\n' \
    "LOCAL_WRAPPER_UNEXPECTED_EXIT_CODE=$rc" \
    'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO' \
    'AUTOMATIC_ALGORITHM_TUNING_AUTHORIZED=NO' \
    'WSL_TERMINAL_CLOSE_REQUESTED=NO' \
    "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
  if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap local_failure ERR

printf '%s\n' \
  '=================================================================' \
  'FR3 V4.5 — HOLDOUT COMPLETION R2 PASS-PARALLEL RECOVERY' \
  '=================================================================' \
  "PACKAGE_ROOT=$PACKAGE_ROOT" \
  "REPO=$REPO" \
  'RERUN_SEEDS=44052_ONLY' \
  'PASS_ARRAY=0-4%5' \
  'CHANNEL_REGENERATION=NO' \
  'GPU_REQUESTED=NO' \
  'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO' \
  'AUTOMATIC_ALGORITHM_TUNING_AUTHORIZED=NO' \
  'WSL_TERMINAL_CLOSE_REQUESTED=NO'

(
  cd "$PACKAGE_ROOT"
  sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
  sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
)
echo 'INTERNAL_MANIFEST_VERIFICATION=PASS'
echo 'SOURCE_PAYLOAD_MANIFEST_VERIFICATION=PASS'

[[ "$(sha256sum "$ARCHIVE" | awk '{print $1}')" == "$ARCHIVE_SHA" ]]
echo 'EXECUTION_ARCHIVE_SHA256_GATE=PASS'

if [[ -x "$REPO/.venv/bin/python" ]]; then
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
  echo 'REPO_VENV_ACTIVATED=YES'
else
  python3 -m venv "$REPO/.venv"
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
  echo 'REPO_VENV_CREATED=YES'
fi
python -m pip install --disable-pip-version-check -q -r "$PACKAGE_ROOT/requirements.txt"
python -m pip check
echo 'LOCAL_VENV_DEPENDENCY_GATE=PASS'

python - "$PACKAGE_ROOT" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
count=0
for path in sorted(root.rglob('*.py')):
    compile(path.read_text(encoding='utf-8'),str(path),'exec')
    count+=1
print('PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS')
print('PYTHON_SYNTAX_FILE_COUNT='+str(count))
PY
for script in "$PACKAGE_ROOT"/wrappers/*.sh; do bash -n "$script"; done
echo 'BASH_SYNTAX_CHECK=PASS'
pytest -q -p no:cacheprovider "$PACKAGE_ROOT/tests"
find "$PACKAGE_ROOT" -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
find "$PACKAGE_ROOT" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
if find "$PACKAGE_ROOT" -type d \( -name __pycache__ -o -name .pytest_cache \) -print -quit | grep -q . || \
   find "$PACKAGE_ROOT" -type f \( -name '*.pyc' -o -name '*.pyo' \) -print -quit | grep -q .; then
  echo 'FORBIDDEN_ARTIFACT_SCAN=FAIL'
  fail_with_code 72
fi
echo 'FORBIDDEN_ARTIFACT_SCAN=PASS'

python "$PACKAGE_ROOT/scripts/audit_r1_timeout.py" \
  --contract "$PACKAGE_ROOT/config/HOLDOUT_COMPLETION_R2_CONTRACT.json" \
  --r1-return "$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R1_18207112.zip" \
  --holdout-return "$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_5_FRESH_HOLDOUT_18163102.zip" \
  --output-json "$LOCAL_RETURN/R1_TIMEOUT_AUDIT.json"

AUDIT_JOB_ROOT="$LOCAL_RETURN/audit_job_package"
mkdir -p "$AUDIT_JOB_ROOT"
unzip -q "$PACKAGE_ROOT/immutable_bindings/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_5_HOLDOUT_v1.zip" \
  -d "$AUDIT_JOB_ROOT"
python "$PACKAGE_ROOT/scripts/audit_pass_parallel_equivalence.py" \
  --job-package-root "$AUDIT_JOB_ROOT" \
  --output-json "$LOCAL_RETURN/PASS_PARALLEL_EQUIVALENCE_AUDIT.json"
rm -rf "$AUDIT_JOB_ROOT"
echo 'LOCAL_QUALITY_GATE=PASS'

SOURCE_CLONE="$LOCAL_RETURN/github_source_clone"
git clone --branch e3-first-sector-p452 \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$SOURCE_CLONE"
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
REMOTE_BEFORE="$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)"
if ! git -C "$SOURCE_CLONE" merge-base --is-ancestor \
  dc360843fcbbe1ef0c4a6420d7a94414ecb0a9bd "$REMOTE_BEFORE"; then
  echo 'GITHUB_REQUIRED_ANCESTOR_GATE=FAIL'
  fail_with_code 71
fi
echo 'GITHUB_REQUIRED_ANCESTOR_GATE=PASS'
echo "GIT_REMOTE_HEAD_BEFORE=$REMOTE_BEFORE"
echo 'GITHUB_NEWER_WORK_OVERWRITTEN=NO'

TOOL_DEST="$SOURCE_CLONE/tools/phase1_v4_5_holdout_completion_r2_pass_parallel_v1"
rm -rf "$TOOL_DEST"
mkdir -p "$TOOL_DEST"
python - "$PACKAGE_ROOT" "$TOOL_DEST" <<'PY'
from pathlib import Path
import hashlib,shutil,sys
source=Path(sys.argv[1]); target=Path(sys.argv[2])
for path in sorted(source.rglob('*')):
    if not path.is_file(): continue
    rel=path.relative_to(source)
    if rel.as_posix() in {'PACKAGE_MANIFEST.sha256'}: continue
    if rel.parts and rel.parts[0]=='immutable_bindings' and path.suffix=='.zip': continue
    if rel.parts and rel.parts[0]=='local_diagnostics': continue
    destination=target/rel; destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(path,destination)
lines=[]
for path in sorted(target.rglob('*')):
    if path.is_file() and path.name!='GITHUB_SOURCE_MANIFEST.sha256':
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(target).as_posix()}\n")
(target/'GITHUB_SOURCE_MANIFEST.sha256').write_text(''.join(lines),encoding='utf-8')
print('GITHUB_SOURCE_SUBSET_COPY=PASS')
print('GITHUB_SOURCE_SUBSET_MANIFEST=PASS')
PY
cp "$LOCAL_RETURN/R1_TIMEOUT_AUDIT.json" "$TOOL_DEST/"
cp "$LOCAL_RETURN/PASS_PARALLEL_EQUIVALENCE_AUDIT.json" "$TOOL_DEST/"
python - "$TOOL_DEST" <<'PY'
from pathlib import Path
import hashlib,sys
root=Path(sys.argv[1]); lines=[]
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name!='GITHUB_SOURCE_MANIFEST.sha256':
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}\n")
(root/'GITHUB_SOURCE_MANIFEST.sha256').write_text(''.join(lines),encoding='utf-8')
print('GITHUB_SOURCE_SUBSET_MANIFEST_FINAL=PASS')
PY

git -C "$SOURCE_CLONE" add "$TOOL_DEST"
git -C "$SOURCE_CLONE" diff --cached --check
if ! git -C "$SOURCE_CLONE" diff --cached --quiet; then
  git -C "$SOURCE_CLONE" -c user.name='Ali Fazeli' \
    -c user.email='ali.fazeli@utoronto.ca' \
    commit -m 'Add pass-parallel completion for holdout seed 44052'
  git -C "$SOURCE_CLONE" pull --rebase origin e3-first-sector-p452
  git -C "$SOURCE_CLONE" push origin HEAD:e3-first-sector-p452
fi
HOLDOUT_COMPLETION_R2_SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
echo "HOLDOUT_COMPLETION_R2_SOURCE_COMMIT=$HOLDOUT_COMPLETION_R2_SOURCE_COMMIT"

REMOTE_BASE='/home/rsadve1/links/scratch/FR3_V45_HOLDOUT_COMPLETION_R2_UPLOADS'
REMOTE_ARCHIVE="$REMOTE_BASE/$(basename "$ARCHIVE")"
ssh "$RORQUAL_HOST" "mkdir -p '$REMOTE_BASE'"
scp "$ARCHIVE" "$RORQUAL_HOST:$REMOTE_ARCHIVE"
REMOTE_LOG="$LOCAL_RETURN/REMOTE_ORCHESTRATOR.log"
if ssh "$RORQUAL_HOST" \
  "FR3_RORQUAL_SCRATCH_LINK=/home/rsadve1/links/scratch bash -s -- '$REMOTE_ARCHIVE' '$ARCHIVE_SHA'" \
  < "$PACKAGE_ROOT/wrappers/REMOTE_ORCHESTRATE_V45_HOLDOUT_COMPLETION_R2.sh" \
  | tee "$REMOTE_LOG"; then
  REMOTE_WRAPPER_EXIT_CODE=0
else
  REMOTE_WRAPPER_EXIT_CODE=${PIPESTATUS[0]}
fi
echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE"

REMOTE_RETURN_ZIP="$(grep '^REMOTE_HOLDOUT_COMPLETION_R2_RETURN_ZIP=' "$REMOTE_LOG" | tail -n1 | cut -d= -f2-)"
REMOTE_RETURN_SHA="$(grep '^REMOTE_HOLDOUT_COMPLETION_R2_RETURN_ZIP_SHA256=' "$REMOTE_LOG" | tail -n1 | cut -d= -f2-)"
[[ -n "$REMOTE_RETURN_ZIP" && -n "$REMOTE_RETURN_SHA" ]]
LOCAL_ZIP="$LOCAL_RETURN/$(basename "$REMOTE_RETURN_ZIP")"
if scp "$RORQUAL_HOST:$REMOTE_RETURN_ZIP" "$LOCAL_ZIP" && \
   scp "$RORQUAL_HOST:$REMOTE_RETURN_ZIP.sha256" "$LOCAL_ZIP.sha256"; then
  DIAGNOSTIC_RETRIEVAL_EXIT_CODE=0
else
  DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$?
fi
echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$DIAGNOSTIC_RETRIEVAL_EXIT_CODE"

SIDE_NAME="$(awk 'NF>=2{print $2;exit}' "$LOCAL_ZIP.sha256")"
[[ "$SIDE_NAME" == "$(basename "$LOCAL_ZIP")" ]]
[[ "$(sha256sum "$LOCAL_ZIP" | awk '{print $1}')" == "$REMOTE_RETURN_SHA" ]]
unzip -t "$LOCAL_ZIP" >/dev/null
echo 'HOLDOUT_COMPLETION_R2_RETURN_SHA256_GATE=PASS'
echo 'HOLDOUT_COMPLETION_R2_RETURN_ZIP_CRC=PASS'

EXTRACTED="$LOCAL_RETURN/extracted_return"
mkdir -p "$EXTRACTED"
unzip -q "$LOCAL_ZIP" -d "$EXTRACTED"
RETURN_ROOT="$(find "$EXTRACTED" -mindepth 1 -maxdepth 1 -type d | head -n1)"
(
  cd "$RETURN_ROOT"
  sha256sum -c RETURN_MANIFEST.sha256 >/dev/null
)
echo 'HOLDOUT_COMPLETION_R2_RETURN_MANIFEST=PASS'

EVIDENCE_CLONE="$LOCAL_RETURN/github_evidence_clone"
git clone --branch e3-first-sector-p452 \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$EVIDENCE_CLONE"
EVIDENCE_DEST="$EVIDENCE_CLONE/evidence/phase1_v4_5_holdout_completion_r2_pass_parallel_v1"
rm -rf "$EVIDENCE_DEST"
mkdir -p "$EVIDENCE_DEST"
cp "$LOCAL_ZIP.sha256" "$EVIDENCE_DEST/"
python - "$LOG" "$EVIDENCE_DEST/LOCAL_WSL_ORCHESTRATOR.log" \
  "$REMOTE_LOG" "$EVIDENCE_DEST/REMOTE_ORCHESTRATOR.log" <<'PY'
from pathlib import Path
import sys
for source_name,target_name in zip(sys.argv[1::2],sys.argv[2::2]):
    source=Path(source_name); target=Path(target_name)
    lines=source.read_text(encoding='utf-8',errors='replace').splitlines()
    target.write_text('\n'.join(line.rstrip() for line in lines)+'\n',encoding='utf-8')
print('GITHUB_LOG_TRAILING_WHITESPACE_NORMALIZATION=PASS')
PY
for name in HOLDOUT_COMPLETION_AUDIT.json RETURN_METADATA.json RETURN_MANIFEST.sha256 \
  R1_TIMEOUT_AUDIT.json PASS_PARALLEL_EQUIVALENCE_AUDIT.json; do
  [[ -f "$RETURN_ROOT/$name" ]] && cp "$RETURN_ROOT/$name" "$EVIDENCE_DEST/"
done
mkdir -p "$EVIDENCE_DEST/merged" "$EVIDENCE_DEST/slurm" "$EVIDENCE_DEST/pass_outputs"
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
mkdir -p "$EVIDENCE_CLONE/paper/twc_v4_5_draft_start/tables" \
  "$EVIDENCE_CLONE/paper/twc_v4_5_draft_start/data"
[[ -f "$RETURN_ROOT/holdout_key_results.tex" ]] && cp "$RETURN_ROOT/holdout_key_results.tex" \
  "$EVIDENCE_CLONE/paper/twc_v4_5_draft_start/tables/holdout_key_results.tex"
[[ -f "$RETURN_ROOT/HOLDOUT_COMPLETION_AUDIT.json" ]] && cp "$RETURN_ROOT/HOLDOUT_COMPLETION_AUDIT.json" \
  "$EVIDENCE_CLONE/paper/twc_v4_5_draft_start/data/HOLDOUT_COMPLETION_AUDIT.json"

git -C "$EVIDENCE_CLONE" add "$EVIDENCE_DEST" \
  paper/twc_v4_5_draft_start/tables/holdout_key_results.tex \
  paper/twc_v4_5_draft_start/data/HOLDOUT_COMPLETION_AUDIT.json
git -C "$EVIDENCE_CLONE" diff --cached --check
if ! git -C "$EVIDENCE_CLONE" diff --cached --quiet; then
  git -C "$EVIDENCE_CLONE" -c user.name='Ali Fazeli' \
    -c user.email='ali.fazeli@utoronto.ca' \
    commit -m 'Complete holdout seed 44052 with pass-parallel recovery'
  git -C "$EVIDENCE_CLONE" pull --rebase origin e3-first-sector-p452
  git -C "$EVIDENCE_CLONE" push origin HEAD:e3-first-sector-p452
fi
GIT_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" rev-parse HEAD)"
git -C "$EVIDENCE_CLONE" fetch origin e3-first-sector-p452
GIT_REMOTE_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" rev-parse origin/e3-first-sector-p452)"
echo "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT"
echo "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT"

for key in PASS_ARRAY_JOB_ID ASSEMBLY_JOB_ID PASS_TASK_RECORD_COUNT \
  PASS_TASK_COMPLETED_COUNT ASSEMBLY_STATE ASSEMBLY_SLURM_EXIT_CODE \
  SEED44052_SCIENTIFIC_EXIT_CODE SEED44052_CANDIDATE_HARD_GATES_PASS \
  HOLDOUT_RETURN_STATUS HOLDOUT_VALID_RESULT HOLDOUT_SEED_RETURN_COUNT \
  HOLDOUT_SEED_SAFETY_PASS_COUNT HOLDOUT_SEED_ZERO_FLOOR_PASS_COUNT \
  HOLDOUT_PRIMARY_SUPERIORITY_MET HOLDOUT_FLOOR_ZERO PRIMARY_POINT_ESTIMATE \
  PRIMARY_LOWER_95 PRIMARY_UPPER_95 PAPER_WRITING_AUTHORIZED NEXT_GATE; do
  value="$(grep "^${key}=" "$REMOTE_LOG" | tail -n1 | cut -d= -f2- || true)"
  [[ -n "$value" ]] && echo "$key=$value"
done

rm -rf "$SOURCE_CLONE" "$EVIDENCE_CLONE" "$EXTRACTED"
echo 'LOCAL_RETURN_GITHUB_CLONES_REMOVED=PASS'
echo "LOCAL_HOLDOUT_COMPLETION_R2_RETURN_ZIP=$LOCAL_ZIP"
echo "LOCAL_HOLDOUT_COMPLETION_R2_RETURN_ZIP_SHA256=$(sha256sum "$LOCAL_ZIP" | awk '{print $1}')"
echo 'AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO'
echo 'AUTOMATIC_ALGORITHM_TUNING_AUTHORIZED=NO'
echo "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
echo 'WSL_TERMINAL_CLOSE_REQUESTED=NO'

if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
fi
exit "$REMOTE_WRAPPER_EXIT_CODE"
