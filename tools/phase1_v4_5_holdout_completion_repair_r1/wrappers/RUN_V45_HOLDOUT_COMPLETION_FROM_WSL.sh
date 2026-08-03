#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE_ROOT="$(realpath "$1")"
REPO="${FR3_REPO_ROOT:?FR3_REPO_ROOT is required}"
DOWNLOADS="${FR3_DOWNLOADS:-/mnt/c/Users/alifa/Downloads}"
RORQUAL_HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
ARCHIVE="${FR3_COMPLETION_ARCHIVE_PATH:?FR3_COMPLETION_ARCHIVE_PATH is required}"
ARCHIVE_SHA="${FR3_COMPLETION_ARCHIVE_SHA256:?FR3_COMPLETION_ARCHIVE_SHA256 is required}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_RETURN="$DOWNLOADS/FR3_V45_HOLDOUT_COMPLETION_R1_RETURN_$STAMP"
LOG="$LOCAL_RETURN/LOCAL_WSL_ORCHESTRATOR.log"
mkdir -p "$LOCAL_RETURN"
exec > >(tee -a "$LOG") 2>&1

local_failure() {
  local rc=$?
  trap - ERR
  set +e
  local failure_zip="$LOCAL_RETURN/FR3_LOCAL_V4_5_HOLDOUT_COMPLETION_R1_FAILURE_${STAMP}.zip"
  python3 - "$LOCAL_RETURN" "$failure_zip" "$PACKAGE_ROOT" "$rc" <<'PY_LOCAL_FAILURE'
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import zipfile

return_dir = Path(sys.argv[1])
archive = Path(sys.argv[2])
package_root = Path(sys.argv[3])
exit_code = int(sys.argv[4])
name = archive.stem
with tempfile.TemporaryDirectory(prefix='fr3-v45-local-failure-') as td:
    payload = Path(td) / name
    payload.mkdir()
    for source_name in ('LOCAL_WSL_ORCHESTRATOR.log', 'INCOMPLETE_HOLDOUT_AUDIT.json', 'REMOTE_ORCHESTRATOR.log'):
        source = return_dir / source_name
        if source.is_file():
            (payload / source_name).write_bytes(source.read_bytes())
    for rel in ('PACKAGE_VERSION.json', 'config/HOLDOUT_COMPLETION_REPAIR_CONTRACT.json'):
        source = package_root / rel
        if source.is_file():
            target = payload / 'package' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    metadata = {
        'schema_version': 1,
        'status': 'LOCAL_HOLDOUT_COMPLETION_ORCHESTRATION_FAILURE',
        'exit_code': exit_code,
        'automatic_extra_seeds_authorized': False,
        'terminal_close_requested': False,
    }
    (payload / 'FAILURE_METADATA.json').write_text(json.dumps(metadata, indent=2, sort_keys=True) + '\n')
    lines=[]
    for source in sorted(payload.rglob('*')):
        if source.is_file() and source.name != 'RETURN_MANIFEST.sha256':
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            lines.append(f'{digest}  {source.relative_to(payload).as_posix()}\n')
    (payload / 'RETURN_MANIFEST.sha256').write_text(''.join(lines))
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zf:
        for source in sorted(payload.rglob('*')):
            if source.is_file():
                zf.write(source, source.relative_to(Path(td)).as_posix())
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
Path(str(archive)+'.sha256').write_text(f'{digest}  {archive.name}\n')
print('LOCAL_FAILURE_RETURN_PACKAGING=PASS')
print('LOCAL_FAILURE_RETURN_ZIP='+str(archive))
print('LOCAL_FAILURE_RETURN_ZIP_SHA256='+digest)
PY_LOCAL_FAILURE
  printf '%s\n' \
    "LOCAL_WRAPPER_UNEXPECTED_EXIT_CODE=$rc" \
    'AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO' \
    'WSL_TERMINAL_CLOSE_REQUESTED=NO' \
    "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
  if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap local_failure ERR
fail_with_code() { return "$1"; }
for cmd in python3 sha256sum unzip git ssh scp bash realpath; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR_MISSING_COMMAND=$cmd"; fail_with_code 90; }
done

printf '%s\n' \
  '=================================================================' \
  'FR3 V4.5 — FRESH HOLDOUT COMPLETION REPAIR R1' \
  '=================================================================' \
  "PACKAGE_ROOT=$PACKAGE_ROOT" \
  "REPO=$REPO" \
  'RERUN_SEEDS=44052_ONLY' \
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

[[ -d "$REPO/.git" ]]
if [[ -f "$REPO/.venv/bin/activate" ]]; then
  source "$REPO/.venv/bin/activate"
else
  python3 -m venv "$REPO/.venv"
  source "$REPO/.venv/bin/activate"
fi
echo 'REPO_VENV_ACTIVATED=YES'
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
python -m pip install -q --disable-pip-version-check -r "$PACKAGE_ROOT/requirements.txt"
python -m pip check
echo 'LOCAL_VENV_DEPENDENCY_GATE=PASS'

python - <<PY
from pathlib import Path
for path in sorted(Path('$PACKAGE_ROOT').rglob('*.py')):
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')
print('PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS')
PY
for script in "$PACKAGE_ROOT"/wrappers/*.sh; do bash -n "$script"; done
echo 'BASH_SYNTAX_CHECK=PASS'
pytest -q -p no:cacheprovider "$PACKAGE_ROOT/tests"
find "$PACKAGE_ROOT" -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
find "$PACKAGE_ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete
if find "$PACKAGE_ROOT" -type d \( -name __pycache__ -o -name .pytest_cache \) -print -quit | grep -q . || \
   find "$PACKAGE_ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" \) -print -quit | grep -q .; then
  echo "FORBIDDEN_ARTIFACT_SCAN=FAIL"
  fail_with_code 72
fi
echo "FORBIDDEN_ARTIFACT_SCAN=PASS"

python "$PACKAGE_ROOT/scripts/audit_incomplete_holdout.py" \
  --holdout-return-zip "$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_5_FRESH_HOLDOUT_18163102.zip" \
  --output-json "$LOCAL_RETURN/INCOMPLETE_HOLDOUT_AUDIT.json"
echo 'LOCAL_QUALITY_GATE=PASS'

SOURCE_CLONE="$LOCAL_RETURN/github_source_clone"
git clone --branch e3-first-sector-p452 \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$SOURCE_CLONE"
git -C "$SOURCE_CLONE" fetch origin e3-first-sector-p452
REMOTE_BEFORE="$(git -C "$SOURCE_CLONE" rev-parse origin/e3-first-sector-p452)"
if ! git -C "$SOURCE_CLONE" merge-base --is-ancestor \
    9c77d520e2f1dc94e44ac5a4750ee5e8548836c4 "$REMOTE_BEFORE"; then
  echo 'GITHUB_REQUIRED_ANCESTOR_GATE=FAIL'
  fail_with_code 71
fi
echo 'GITHUB_REQUIRED_ANCESTOR_GATE=PASS'
echo "GIT_REMOTE_HEAD_BEFORE=$REMOTE_BEFORE"
TOOL_DEST="$SOURCE_CLONE/tools/phase1_v4_5_holdout_completion_repair_r1"
rm -rf "$TOOL_DEST"
mkdir -p "$TOOL_DEST"
python - "$PACKAGE_ROOT" "$TOOL_DEST" <<'PY_COPY_SOURCE'
from pathlib import Path
import shutil
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
for path in sorted(source.rglob('*')):
    rel = path.relative_to(source)
    if not path.is_file():
        continue
    if rel.parts and rel.parts[0] == 'local_diagnostics':
        continue
    if rel.as_posix() == 'PACKAGE_MANIFEST.sha256':
        continue
    if rel.parts and rel.parts[0] == 'immutable_bindings' and path.name.endswith('.zip'):
        continue
    destination = target / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
import hashlib
lines=[]
for path in sorted(target.rglob('*')):
    if path.is_file() and path.name != 'GITHUB_SOURCE_MANIFEST.sha256':
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f'{digest}  {path.relative_to(target).as_posix()}\n')
(target / 'GITHUB_SOURCE_MANIFEST.sha256').write_text(''.join(lines), encoding='utf-8')
print('GITHUB_SOURCE_SUBSET_COPY=PASS')
print('GITHUB_SOURCE_SUBSET_MANIFEST=PASS')
PY_COPY_SOURCE
cp "$LOCAL_RETURN/INCOMPLETE_HOLDOUT_AUDIT.json" "$TOOL_DEST/"
python - "$TOOL_DEST" <<'PY_GITHUB_MANIFEST'
from pathlib import Path
import hashlib
import sys
root=Path(sys.argv[1])
lines=[]
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name != 'GITHUB_SOURCE_MANIFEST.sha256':
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f'{digest}  {path.relative_to(root).as_posix()}\n')
(root/'GITHUB_SOURCE_MANIFEST.sha256').write_text(''.join(lines), encoding='utf-8')
print('GITHUB_SOURCE_SUBSET_MANIFEST_FINAL=PASS')
PY_GITHUB_MANIFEST
git -C "$SOURCE_CLONE" add "$TOOL_DEST"
git -C "$SOURCE_CLONE" diff --cached --check
if ! git -C "$SOURCE_CLONE" diff --cached --quiet; then
  git -C "$SOURCE_CLONE" -c user.name='Ali Fazeli' \
    -c user.email='ali.fazeli@utoronto.ca' \
    commit -m 'Add v4.5 fresh-holdout completion repair'
  git -C "$SOURCE_CLONE" pull --rebase origin e3-first-sector-p452
  git -C "$SOURCE_CLONE" push origin HEAD:e3-first-sector-p452
fi
SOURCE_COMMIT="$(git -C "$SOURCE_CLONE" rev-parse HEAD)"
echo "HOLDOUT_COMPLETION_SOURCE_COMMIT=$SOURCE_COMMIT"
echo 'GITHUB_NEWER_WORK_OVERWRITTEN=NO'

REMOTE_BASE='/home/rsadve1/links/scratch/FR3_V45_HOLDOUT_COMPLETION_UPLOADS'
REMOTE_ARCHIVE="$REMOTE_BASE/$(basename "$ARCHIVE")"
ssh "$RORQUAL_HOST" "mkdir -p '$REMOTE_BASE'"
scp "$ARCHIVE" "$RORQUAL_HOST:$REMOTE_ARCHIVE"
REMOTE_LOG="$LOCAL_RETURN/REMOTE_ORCHESTRATOR.log"
if ssh "$RORQUAL_HOST" \
    "FR3_RORQUAL_SCRATCH_LINK=/home/rsadve1/links/scratch bash -s -- '$REMOTE_ARCHIVE' '$ARCHIVE_SHA'" \
    < "$PACKAGE_ROOT/wrappers/REMOTE_ORCHESTRATE_V45_HOLDOUT_COMPLETION.sh" \
    | tee "$REMOTE_LOG"; then
  REMOTE_WRAPPER_EXIT_CODE=0
else
  REMOTE_WRAPPER_EXIT_CODE=${PIPESTATUS[0]}
fi
echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE"

REMOTE_RETURN_ZIP="$(grep '^REMOTE_HOLDOUT_COMPLETION_RETURN_ZIP=' "$REMOTE_LOG" | tail -n1 | cut -d= -f2-)"
[[ -n "$REMOTE_RETURN_ZIP" ]]
REMOTE_RETURN_SHA="$(grep '^REMOTE_HOLDOUT_COMPLETION_RETURN_ZIP_SHA256=' "$REMOTE_LOG" | tail -n1 | cut -d= -f2-)"
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
echo 'HOLDOUT_COMPLETION_RETURN_SHA256_GATE=PASS'
echo 'HOLDOUT_COMPLETION_RETURN_ZIP_CRC=PASS'

EXTRACTED="$LOCAL_RETURN/extracted_return"
mkdir -p "$EXTRACTED"
unzip -q "$LOCAL_ZIP" -d "$EXTRACTED"
RETURN_ROOT="$(find "$EXTRACTED" -mindepth 1 -maxdepth 1 -type d | head -n1)"
(
  cd "$RETURN_ROOT"
  sha256sum -c RETURN_MANIFEST.sha256 >/dev/null
)
echo 'HOLDOUT_COMPLETION_RETURN_MANIFEST=PASS'

EVIDENCE_CLONE="$LOCAL_RETURN/github_evidence_clone"
git clone --branch e3-first-sector-p452 \
  git@github.com:afazeliUofT/FR3_CBF_Completion_Package_v1_1.git "$EVIDENCE_CLONE"
EVIDENCE_DEST="$EVIDENCE_CLONE/evidence/phase1_v4_5_holdout_completion_r1"
rm -rf "$EVIDENCE_DEST"
mkdir -p "$EVIDENCE_DEST"
cp "$LOCAL_ZIP.sha256" "$EVIDENCE_DEST/"
python - "$LOG" "$EVIDENCE_DEST/LOCAL_WSL_ORCHESTRATOR.log" \
  "$REMOTE_LOG" "$EVIDENCE_DEST/REMOTE_ORCHESTRATOR.log" <<'PY_SANITIZE_LOGS'
from pathlib import Path
import sys
for source_name, target_name in zip(sys.argv[1::2], sys.argv[2::2]):
    source=Path(source_name)
    target=Path(target_name)
    lines=source.read_text(encoding='utf-8',errors='replace').splitlines()
    target.write_text('\n'.join(line.rstrip() for line in lines)+'\n',encoding='utf-8')
print('GITHUB_LOG_TRAILING_WHITESPACE_NORMALIZATION=PASS')
PY_SANITIZE_LOGS
cp "$RETURN_ROOT/HOLDOUT_COMPLETION_AUDIT.json" "$EVIDENCE_DEST/"
cp "$RETURN_ROOT/RETURN_METADATA.json" "$EVIDENCE_DEST/"
cp "$RETURN_ROOT/RETURN_MANIFEST.sha256" "$EVIDENCE_DEST/"
mkdir -p "$EVIDENCE_DEST/merged"
for name in PHASE1_MERGED_AUDIT.json PHASE1_BOOTSTRAP_SUMMARY.json \
  PHASE1_SEED_CLUSTER_EFFECTS.csv PHASE1_METHOD_ENDPOINT_SUMMARY.csv \
  PHASE1_PASS_SPECIFIC_EFFECTS.csv PHASE1_LEAVE_ONE_PASS_OUT.csv \
  PHASE1_ACTION_AND_RUNTIME_SUMMARY.json PHASE1_SEED_RESULT_HASH_INDEX.csv; do
  [[ -f "$RETURN_ROOT/merged/$name" ]] && cp "$RETURN_ROOT/merged/$name" "$EVIDENCE_DEST/merged/"
done
mkdir -p "$EVIDENCE_CLONE/paper/twc_v4_5_draft_start/tables" \
         "$EVIDENCE_CLONE/paper/twc_v4_5_draft_start/data"
cp "$RETURN_ROOT/paper/holdout_key_results.tex" \
  "$EVIDENCE_CLONE/paper/twc_v4_5_draft_start/tables/holdout_key_results.tex"
cp "$RETURN_ROOT/HOLDOUT_COMPLETION_AUDIT.json" \
  "$EVIDENCE_CLONE/paper/twc_v4_5_draft_start/data/HOLDOUT_COMPLETION_AUDIT.json"
git -C "$EVIDENCE_CLONE" add "$EVIDENCE_DEST" \
  paper/twc_v4_5_draft_start/tables/holdout_key_results.tex \
  paper/twc_v4_5_draft_start/data/HOLDOUT_COMPLETION_AUDIT.json
git -C "$EVIDENCE_CLONE" diff --cached --check
if ! git -C "$EVIDENCE_CLONE" diff --cached --quiet; then
  git -C "$EVIDENCE_CLONE" -c user.name='Ali Fazeli' \
    -c user.email='ali.fazeli@utoronto.ca' \
    commit -m 'Complete and audit candidate-v4.5 fresh holdout'
  git -C "$EVIDENCE_CLONE" pull --rebase origin e3-first-sector-p452
  git -C "$EVIDENCE_CLONE" push origin HEAD:e3-first-sector-p452
fi
GIT_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" rev-parse HEAD)"
git -C "$EVIDENCE_CLONE" fetch origin e3-first-sector-p452
GIT_REMOTE_FINAL_COMMIT="$(git -C "$EVIDENCE_CLONE" rev-parse origin/e3-first-sector-p452)"
echo "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT"
echo "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT"

for key in HOLDOUT_RETURN_STATUS HOLDOUT_VALID_RESULT HOLDOUT_SEED_RETURN_COUNT \
  HOLDOUT_SEED_SAFETY_PASS_COUNT HOLDOUT_SEED_ZERO_FLOOR_PASS_COUNT \
  HOLDOUT_PRIMARY_SUPERIORITY_MET HOLDOUT_FLOOR_ZERO PRIMARY_POINT_ESTIMATE \
  PRIMARY_LOWER_95 PRIMARY_UPPER_95 PAPER_WRITING_AUTHORIZED \
  SEED44052_STATE SEED44052_SLURM_EXIT_CODE MERGE_STATE MERGE_SLURM_EXIT_CODE; do
  value="$(grep "^${key}=" "$REMOTE_LOG" | tail -n1 | cut -d= -f2- || true)"
  [[ -n "$value" ]] && echo "$key=$value"
done

rm -rf "$SOURCE_CLONE" "$EVIDENCE_CLONE" "$EXTRACTED"
echo 'LOCAL_RETURN_GITHUB_CLONES_REMOVED=PASS'
echo "LOCAL_HOLDOUT_COMPLETION_RETURN_ZIP=$LOCAL_ZIP"
echo "LOCAL_HOLDOUT_COMPLETION_RETURN_ZIP_SHA256=$(sha256sum "$LOCAL_ZIP" | awk '{print $1}')"
echo 'AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO'
echo 'NEXT_GATE=FINALIZE_13_PAGE_TWC_MANUSCRIPT_AND_ONE_COMPACT_PRACTICALITY_SECTION'
echo "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
echo 'WSL_TERMINAL_CLOSE_REQUESTED=NO'

if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
fi
exit "$REMOTE_WRAPPER_EXIT_CODE"
