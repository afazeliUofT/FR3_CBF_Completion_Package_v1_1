#!/usr/bin/env bash
# WSL orchestrator: local release gates, isolated Git staging/push, CPU-only
# Rorqual diagnostic, compact return retrieval, evidence push, and final report.
set -Eeuo pipefail

PACKAGE_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PACKAGE_ROOT="$(realpath "$PACKAGE_ROOT")"
REPO="${FR3_REPO_ROOT:-/home/afazeli2006/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
BRANCH="e3-first-sector-p452"
EXPECTED_BASE="76a62cda5d649cad25a6a45ccb5f0f757a99a269"
HOST="${FR3_RORQUAL_HOST:-rsadve1@rorqual.alliancecan.ca}"
REMOTE_BASE="/lustre10/scratch/rsadve1/FR3_PHASE1_RORQUAL_SMOKE_5037b4e33448_20260801_031008"
REMOTE_SCRATCH_LINK="/home/rsadve1/links/scratch"
EXPECTED_CHANNEL_RECORD_SHA256="bf55f7a071bc00fdc9e73075bcf2b3f9da3bd07843e3795e134d4bdb3c4fa0d9"
EXPECTED_FREQUENCY_ARRAY_SHA256="c4ac7fb56da5d3f8182836e2a99ab2ef1dd7b17bf76332abbc198d1ae6b6a093"
DOWNLOADS="${FR3_DOWNLOADS:-/mnt/c/Users/alifa/Downloads}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_RETURN="$DOWNLOADS/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_RETURN_$STAMP"
LOCAL_LOG="$LOCAL_RETURN/LOCAL_WSL_ORCHESTRATOR.log"
LOCAL_CHECKS="$LOCAL_RETURN/local_checks"
GIT_WORK="$LOCAL_RETURN/github_working_clone"
REMOTE_RUN_ROOT="$REMOTE_SCRATCH_LINK/FR3_FLOOR_FEASIBILITY_CANDIDATE_V4_2_$STAMP"
TARGET_REL="tools/floor_feasibility_candidate_v4_2_dropin_v1"
EVIDENCE_REL="evidence/phase1_floor_feasibility_candidate_v4_2_dropin_v1"
mkdir -p "$LOCAL_RETURN" "$LOCAL_CHECKS"
exec > >(tee "$LOCAL_LOG") 2>&1

CONTROL_PATH="/tmp/fr3_floor_v4_2_${UID}_$$_%C"
SSH_OPTS=(-o ControlMaster=auto -o ControlPersist=20m -o ControlPath="$CONTROL_PATH" -o ServerAliveInterval=60 -o ServerAliveCountMax=5)
SCP_OPTS=(-o ControlMaster=auto -o ControlPersist=20m -o ControlPath="$CONTROL_PATH" -o ServerAliveInterval=60 -o ServerAliveCountMax=5)
REMOTE_WRAPPER_EXIT_CODE="NOT_STARTED"
RETRIEVAL_EXIT_CODE="NOT_STARTED"
RETURN_ZIP=""
RETURN_SHA=""
LOCAL_FAILURE_STAGE="INITIALIZATION"
FINAL_REPORT_PRINTED=0
LOCAL_HEAD_BEFORE="UNKNOWN"
REMOTE_HEAD_BEFORE="UNKNOWN"
SOURCE_COMMIT="NOT_REACHED"
FINAL_COMMIT="NOT_REACHED"
REMOTE_FINAL_COMMIT="NOT_REACHED"
NEXT_GATE="CPU_ONLY_RORQUAL_EXACT_SEED43999_FEASIBILITY_DIAGNOSTIC"

close_control() { ssh "${SSH_OPTS[@]}" -O exit "$HOST" >/dev/null 2>&1 || true; }
open_return() {
  if command -v explorer.exe >/dev/null 2>&1; then
    explorer.exe "$(wslpath -w "$LOCAL_RETURN")" >/dev/null 2>&1 || true
  fi
}
package_local_failure() {
  local code="$1"
  if [[ -n "${RETURN_ZIP:-}" && -f "${RETURN_ZIP:-}" ]]; then return 0; fi
  if find "$LOCAL_RETURN/remote_return" -maxdepth 1 -type f -name 'FR3_RORQUAL_FLOOR_FEASIBILITY_CANDIDATE_V4_2_*.zip' -print -quit 2>/dev/null | grep -q .; then return 0; fi
  cat > "$LOCAL_RETURN/LOCAL_FAILURE_STATUS.env" <<EOF_FAIL
LOCAL_WRAPPER_EXIT_CODE=$code
REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE
DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$RETRIEVAL_EXIT_CODE
LOCAL_FAILURE_STAGE=$LOCAL_FAILURE_STAGE
GIT_HEAD_BEFORE=$LOCAL_HEAD_BEFORE
GIT_REMOTE_HEAD_BEFORE=$REMOTE_HEAD_BEFORE
CANDIDATE_SOURCE_COMMIT=$SOURCE_COMMIT
GIT_FINAL_COMMIT=$FINAL_COMMIT
GIT_REMOTE_FINAL_COMMIT=$REMOTE_FINAL_COMMIT
CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO
NEXT_GATE=DIAGNOSE_LOCAL_WSL_ORCHESTRATOR_FAILURE
EOF_FAIL
  rm -rf "$LOCAL_RETURN/pycache" "$LOCAL_RETURN/.pytest_cache" 2>/dev/null || true
  find "$LOCAL_RETURN" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$LOCAL_RETURN" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
  local zip_path="$LOCAL_RETURN/FR3_LOCAL_FLOOR_FEASIBILITY_CANDIDATE_V4_2_FAILURE_${STAMP}.zip"
  if python3 - "$LOCAL_RETURN" "$zip_path" <<'PY'
from pathlib import Path
import sys,zipfile
root,out=map(Path,sys.argv[1:])
forbidden_dirs={'__pycache__','.pytest_cache','pycache','.git'}
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,allowZip64=True) as z:
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path == out or path.name == out.name+'.sha256': continue
        if path.suffix.lower() in {'.zip','.pyc','.pyo'}: continue
        if forbidden_dirs.intersection(path.parts): continue
        z.write(path,path.relative_to(root).as_posix())
with zipfile.ZipFile(out) as z:
    bad=z.testzip()
    if bad is not None: raise RuntimeError(f'bad ZIP member: {bad}')
PY
  then
    (cd "$LOCAL_RETURN"; sha256sum "$(basename "$zip_path")" > "$(basename "$zip_path").sha256"; sha256sum -c "$(basename "$zip_path").sha256" >/dev/null; unzip -t "$(basename "$zip_path")" >/dev/null) || true
    echo "LOCAL_FAILURE_RETURN_ZIP=$zip_path"
    echo "LOCAL_FAILURE_RETURN_ZIP_SHA256=$(sha256sum "$zip_path" | awk '{print $1}')"
    echo "RETURN_TO_CHATGPT=$zip_path"
    echo "RETURN_TO_CHATGPT=$zip_path.sha256"
    echo "RETURN_TO_CHATGPT=$LOCAL_LOG"
  else
    echo "LOCAL_FAILURE_PACKAGING=FAILED"
    echo "RETURN_TO_CHATGPT=$LOCAL_LOG"
  fi
}
on_exit() {
  local code=$?
  trap - EXIT ERR
  if (( code != 0 )); then package_local_failure "$code" || true; fi
  if [[ "$FINAL_REPORT_PRINTED" -eq 0 ]]; then
    echo "LOCAL_WRAPPER_EXIT_CODE=$code"
    echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE"
    echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$RETRIEVAL_EXIT_CODE"
    echo "GIT_FINAL_COMMIT=$FINAL_COMMIT"
    echo "GIT_REMOTE_FINAL_COMMIT=$REMOTE_FINAL_COMMIT"
    echo "CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO"
    echo "NEXT_GATE=$NEXT_GATE"
    echo "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN"
  fi
  close_control
  open_return
  exit "$code"
}
trap on_exit EXIT
on_error() {
  local code=$?
  trap - ERR
  echo "LOCAL_WRAPPER_UNEXPECTED_ERROR_CODE=$code"
  echo "LOCAL_WRAPPER_UNEXPECTED_ERROR_COMMAND=${BASH_COMMAND:-unknown}"
  echo "LOCAL_FAILURE_STAGE=$LOCAL_FAILURE_STAGE"
  exit "$code"
}
trap on_error ERR

printf '%s\n' \
  '=================================================================' \
  'FR3 FLOOR-FEASIBILITY CANDIDATE V4.2 — WSL ORCHESTRATOR' \
  '=================================================================' \
  "PACKAGE_ROOT=$PACKAGE_ROOT" \
  "REPO=$REPO" \
  "LOCAL_RETURN=$LOCAL_RETURN" \
  'RORQUAL_REQUIRED=YES_CPU_ONLY' \
  'H100_CHANNEL_REGENERATION=NO' \
  'PRESERVED_SEED43999_CHANNEL_REUSED=YES' \
  'CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO'

LOCAL_FAILURE_STAGE="PACKAGE_INTEGRITY"
[[ -d "$PACKAGE_ROOT" && -f "$PACKAGE_ROOT/PACKAGE_MANIFEST.sha256" && -f "$PACKAGE_ROOT/SOURCE_PAYLOAD_MANIFEST.sha256" ]] || { echo "ERROR: invalid extracted package root"; exit 2; }
(cd "$PACKAGE_ROOT"; sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null; sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null)
echo "INTERNAL_MANIFEST_VERIFICATION=PASS"
echo "SOURCE_PAYLOAD_MANIFEST_VERIFICATION=PASS"

LOCAL_FAILURE_STAGE="GIT_READ_ONLY_PREFLIGHT_AND_ISOLATED_CLONE"
[[ -d "$REPO/.git" ]] || { echo "ERROR: repository not found: $REPO"; exit 3; }
git -C "$REPO" fetch --prune origin "$BRANCH"
LOCAL_HEAD_BEFORE="$(git -C "$REPO" rev-parse HEAD)"
REMOTE_HEAD_BEFORE="$(git -C "$REPO" rev-parse "origin/$BRANCH")"
git -C "$REPO" merge-base --is-ancestor "$EXPECTED_BASE" "origin/$BRANCH" || { echo "ERROR: expected reviewed base is not an ancestor of remote branch"; exit 4; }
ORIGIN_URL="$(git -C "$REPO" remote get-url origin)"
git clone --no-hardlinks "$REPO" "$GIT_WORK" >/dev/null
git -C "$GIT_WORK" remote set-url origin "$ORIGIN_URL"
git -C "$GIT_WORK" fetch --prune origin "$BRANCH"
git -C "$GIT_WORK" checkout -B "$BRANCH" "origin/$BRANCH" >/dev/null
[[ -z "$(git -C "$GIT_WORK" status --porcelain)" ]] || { echo "ERROR: isolated clone is not clean"; exit 5; }
if [[ -z "$(git -C "$GIT_WORK" config user.name || true)" ]]; then git -C "$GIT_WORK" config user.name "Ali Fazeli"; fi
if [[ -z "$(git -C "$GIT_WORK" config user.email || true)" ]]; then git -C "$GIT_WORK" config user.email "ali.fazeli@utoronto.ca"; fi
echo "GIT_HEAD_BEFORE=$LOCAL_HEAD_BEFORE"
echo "GIT_REMOTE_HEAD_BEFORE=$REMOTE_HEAD_BEFORE"
echo "GIT_STAGING_WORKTREE=$GIT_WORK"
echo "LOCAL_REPOSITORY_WORKTREE_MODIFIED=NO"
echo "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

LOCAL_FAILURE_STAGE="LOCAL_ENVIRONMENT_AND_RELEASE_GATES"
VENV="$REPO/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then python3 -m venv "$VENV"; fi
if ! "$VENV/bin/python" - <<'PY' >/dev/null 2>&1
import numpy,pandas,scipy,pytest
from scipy.optimize import milp
PY
then
  "$VENV/bin/python" -m pip install 'numpy>=1.26,<3' 'pandas>=2.1,<3' 'scipy>=1.11,<2' 'pytest>=8,<10'
fi
source "$VENV/bin/activate"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export PYTHONPYCACHEPREFIX="$LOCAL_RETURN/pycache"
"$VENV/bin/python" - "$PACKAGE_ROOT" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1]); count=0
for path in sorted(root.rglob('*.py')):
    compile(path.read_text(encoding='utf-8'),str(path),'exec'); count+=1
print('PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS')
print(f'PYTHON_SYNTAX_FILE_COUNT={count}')
PY
while IFS= read -r script; do bash -n "$script"; done < <(find "$PACKAGE_ROOT" -type f -name '*.sh' -print | sort)
echo "BASH_SYNTAX_CHECK=PASS"
PYTHONPATH="$PACKAGE_ROOT/src" "$VENV/bin/python" -m pytest -q -p no:cacheprovider "$PACKAGE_ROOT/tests" | tee "$LOCAL_CHECKS/PYTEST.txt"
PYTHONPATH="$PACKAGE_ROOT/src" "$VENV/bin/python" "$PACKAGE_ROOT/scripts/audit_packaged_diagnostic.py" --evidence-root "$PACKAGE_ROOT/immutable_bindings/latest_diagnostic_evidence" --handoff-state "$PACKAGE_ROOT/immutable_bindings/handoff_contract/HANDOFF_STATE.json" --output "$LOCAL_CHECKS/PACKAGED_DIAGNOSTIC_AUDIT.json" | tee "$LOCAL_CHECKS/PACKAGED_DIAGNOSTIC_AUDIT.txt"
PYTHONPATH="$PACKAGE_ROOT/src" "$VENV/bin/python" "$PACKAGE_ROOT/scripts/regress_original_validated_topology.py" --data-root "$PACKAGE_ROOT/test_data/original_validated_minimal" --output "$LOCAL_CHECKS/ORIGINAL_VALIDATED_REGRESSION.json" | tee "$LOCAL_CHECKS/ORIGINAL_VALIDATED_REGRESSION.txt"
PYTHONPATH="$PACKAGE_ROOT/src" "$VENV/bin/python" "$PACKAGE_ROOT/scripts/randomized_model_audit.py" --output "$LOCAL_CHECKS/RANDOMIZED_MODEL_AUDIT.json" | tee "$LOCAL_CHECKS/RANDOMIZED_MODEL_AUDIT.txt"
if find "$PACKAGE_ROOT" \( -type d -name __pycache__ -o -type d -name .pytest_cache -o -type f \( -name '*.pyc' -o -name '*.pyo' \) \) -print -quit | grep -q .; then echo "ERROR: compiled/cache artifacts appeared in package"; exit 7; fi
echo "LOCAL_QUALITY_GATE=PASS"
echo "STRICT_LOCAL_SCOPE_UNIT_GATE=PASS"

LOCAL_FAILURE_STAGE="SOURCE_STAGING_COMMIT_AND_PUSH"
TARGET="$GIT_WORK/$TARGET_REL"
if [[ -e "$TARGET" ]]; then
  echo "ERROR: candidate target already exists on the fetched branch; no newer or prior work was overwritten"
  echo "EXISTING_TARGET=$TARGET_REL"
  exit 6
fi
mkdir -p "$TARGET"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude '__pycache__/' --exclude '*.pyc' --exclude '*.pyo' --exclude '.pytest_cache/' "$PACKAGE_ROOT/" "$TARGET/"
else
  cp -a "$PACKAGE_ROOT/." "$TARGET/"
  find "$TARGET" -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
  find "$TARGET" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
fi
mkdir -p "$TARGET/local_diagnostics"
cp -a "$LOCAL_CHECKS/." "$TARGET/local_diagnostics/"
"$VENV/bin/python" - "$TARGET" <<'PY'
from pathlib import Path
import hashlib,sys
root=Path(sys.argv[1]); manifest=root/'PACKAGE_MANIFEST.sha256'; lines=[]
for path in sorted(root.rglob('*')):
    if path.is_file() and path != manifest:
        lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(root).as_posix())
manifest.write_text('\n'.join(lines)+'\n',encoding='utf-8')
PY
(cd "$TARGET"; sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null; sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null)
git -C "$GIT_WORK" add -- "$TARGET_REL"
if ! git -C "$GIT_WORK" diff --cached --quiet; then
  git -C "$GIT_WORK" diff --cached --check
  git -C "$GIT_WORK" commit -m "Add candidate-v4.2 bounded floor-feasibility repair" >/dev/null
fi
SOURCE_COMMIT="$(git -C "$GIT_WORK" rev-parse HEAD)"
git -C "$GIT_WORK" fetch origin "$BRANCH"
REMOTE_NOW="$(git -C "$GIT_WORK" rev-parse "origin/$BRANCH")"
PARENT_FOR_PUSH="$(git -C "$GIT_WORK" rev-parse "${SOURCE_COMMIT}^" 2>/dev/null || echo "$SOURCE_COMMIT")"
if [[ "$REMOTE_NOW" != "$PARENT_FOR_PUSH" && "$REMOTE_NOW" != "$SOURCE_COMMIT" ]]; then
  echo "ERROR: remote branch advanced during source staging; no overwrite attempted"
  echo "REMOTE_HEAD_NEW=$REMOTE_NOW"
  exit 8
fi
git -C "$GIT_WORK" push origin "$BRANCH"
REMOTE_SOURCE_COMMIT="$(git -C "$GIT_WORK" ls-remote --heads origin "$BRANCH" | awk '{print $1}')"
[[ "$REMOTE_SOURCE_COMMIT" == "$SOURCE_COMMIT" ]] || { echo "ERROR: source commit was not pushed exactly"; exit 9; }
echo "CANDIDATE_SOURCE_COMMIT=$SOURCE_COMMIT"
COMMIT_CHECK="$LOCAL_RETURN/committed_source_check"
mkdir -p "$COMMIT_CHECK"
git -C "$GIT_WORK" archive "$SOURCE_COMMIT" "$TARGET_REL" | tar -x -C "$COMMIT_CHECK"
(cd "$COMMIT_CHECK/$TARGET_REL"; sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null; sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null)
echo "COMMITTED_PACKAGE_MANIFEST_VERIFICATION=PASS"
echo "COMMITTED_SOURCE_MANIFEST_VERIFICATION=PASS"

LOCAL_FAILURE_STAGE="REMOTE_PAYLOAD_AND_RORQUAL_CPU_RUN"
PAYLOAD="$LOCAL_RETURN/FR3_FLOOR_CANDIDATE_V4_2_REMOTE_PAYLOAD.tar.gz"
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' -czf "$PAYLOAD" -C "$TARGET" src scripts config wrappers SOURCE_PAYLOAD_MANIFEST.sha256 immutable_bindings/IMMUTABLE_INPUT_BINDINGS.json PACKAGE_VERSION.json
PAYLOAD_SHA="$(sha256sum "$PAYLOAD" | awk '{print $1}')"
printf '%s  %s\n' "$PAYLOAD_SHA" "$(basename "$PAYLOAD")" > "$PAYLOAD.sha256"
echo "REMOTE_PAYLOAD_SHA256=$PAYLOAD_SHA"
ssh "${SSH_OPTS[@]}" "$HOST" "mkdir -p '$REMOTE_RUN_ROOT/payload' '$REMOTE_RUN_ROOT/return'"
scp "${SCP_OPTS[@]}" "$PAYLOAD" "${HOST}:${REMOTE_RUN_ROOT}/payload.tar.gz"
REMOTE_PAYLOAD_ACTUAL="$(ssh "${SSH_OPTS[@]}" "$HOST" "sha256sum '$REMOTE_RUN_ROOT/payload.tar.gz'" | awk '{print $1}')"
echo "REMOTE_PAYLOAD_SHA256_RECOMPUTED=$REMOTE_PAYLOAD_ACTUAL"
[[ "$REMOTE_PAYLOAD_ACTUAL" == "$PAYLOAD_SHA" ]] || { echo "ERROR: remote payload SHA-256 mismatch"; exit 10; }
ssh "${SSH_OPTS[@]}" "$HOST" "tar -xzf '$REMOTE_RUN_ROOT/payload.tar.gz' -C '$REMOTE_RUN_ROOT/payload'"
echo "REMOTE_CPU_DIAGNOSTIC_SUBMITTED_ONLY=YES"
if ssh "${SSH_OPTS[@]}" "$HOST" "REMOTE_RUN_ROOT='$REMOTE_RUN_ROOT' REMOTE_BASE='$REMOTE_BASE' SOURCE_COMMIT='$SOURCE_COMMIT' EXPECTED_CHANNEL_RECORD_SHA256='$EXPECTED_CHANNEL_RECORD_SHA256' EXPECTED_FREQUENCY_ARRAY_SHA256='$EXPECTED_FREQUENCY_ARRAY_SHA256' CPUS=16 MEMORY_GIB=64 TIME_LIMIT=06:00:00 POLL_SECONDS=20 bash '$REMOTE_RUN_ROOT/payload/wrappers/REMOTE_ORCHESTRATE_FR3_FLOOR_CANDIDATE_V4_2.sh'"; then
  REMOTE_WRAPPER_EXIT_CODE=0
else
  REMOTE_WRAPPER_EXIT_CODE=$?
fi
echo "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE"

LOCAL_FAILURE_STAGE="REMOTE_RETURN_RETRIEVAL"
mkdir -p "$LOCAL_RETURN/remote_return"
if scp "${SCP_OPTS[@]}" -r "${HOST}:${REMOTE_RUN_ROOT}/return/." "$LOCAL_RETURN/remote_return/"; then RETRIEVAL_EXIT_CODE=0; else RETRIEVAL_EXIT_CODE=$?; fi
echo "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$RETRIEVAL_EXIT_CODE"
[[ "$RETRIEVAL_EXIT_CODE" -eq 0 ]] || exit "$RETRIEVAL_EXIT_CODE"
RETURN_ZIP="$(find "$LOCAL_RETURN/remote_return" -maxdepth 1 -type f -name 'FR3_RORQUAL_FLOOR_FEASIBILITY_CANDIDATE_V4_2_*.zip' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
[[ -f "$RETURN_ZIP" ]] || { echo "ERROR: compact remote return ZIP missing"; exit 11; }
RETURN_SHA="$RETURN_ZIP.sha256"
[[ -f "$RETURN_SHA" ]] || { echo "ERROR: compact return sidecar missing"; exit 12; }
(cd "$(dirname "$RETURN_ZIP")"; sha256sum -c "$(basename "$RETURN_SHA")" >/dev/null; unzip -t "$(basename "$RETURN_ZIP")" >/dev/null)
LOCAL_RETURN_ZIP_SHA256="$(sha256sum "$RETURN_ZIP" | awk '{print $1}')"
echo "LOCAL_RETURN_ZIP=$RETURN_ZIP"
echo "LOCAL_RETURN_ZIP_SHA256=$LOCAL_RETURN_ZIP_SHA256"
EXTRACTED_RETURN="$LOCAL_RETURN/extracted_remote_return"
mkdir -p "$EXTRACTED_RETURN"
unzip -q "$RETURN_ZIP" -d "$EXTRACTED_RETURN"
if [[ -f "$EXTRACTED_RETURN/summary/OUTPUT_MANIFEST.sha256" ]]; then (cd "$EXTRACTED_RETURN/summary"; sha256sum -c OUTPUT_MANIFEST.sha256 >/dev/null); echo "REMOTE_SUMMARY_MANIFEST_VERIFICATION=PASS"; fi

LOCAL_FAILURE_STAGE="EVIDENCE_STAGING_COMMIT_AND_PUSH"
EVIDENCE="$GIT_WORK/$EVIDENCE_REL"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"
python3 - "$EXTRACTED_RETURN" "$EVIDENCE" <<'PY'
from pathlib import Path
import shutil,sys
src,dst=map(Path,sys.argv[1:]); keep={'.json','.csv','.txt','.env','.sha256','.md','.out','.err','.sbatch'}
for path in sorted(src.rglob('*')):
    if path.is_file() and path.suffix in keep:
        target=dst/path.relative_to(src); target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,target)
PY
cp -p "$LOCAL_LOG" "$EVIDENCE/LOCAL_WSL_ORCHESTRATOR.log"
cp -p "$RETURN_SHA" "$EVIDENCE/"
cp -p "$LOCAL_CHECKS"/*.json "$EVIDENCE/" 2>/dev/null || true
python3 - "$EVIDENCE" "$REMOTE_WRAPPER_EXIT_CODE" "$LOCAL_RETURN_ZIP_SHA256" <<'PY'
from pathlib import Path
import hashlib,json,sys
evidence=Path(sys.argv[1]); remote_exit=int(sys.argv[2]); zip_sha=sys.argv[3]
values={}; status=evidence/'summary/RUN_STATUS.env'
if status.is_file():
    for line in status.read_text().splitlines():
        if '=' in line:
            k,v=line.split('=',1); values[k]=v
record={'schema_version':1,'candidate_version':'v4.2','status':'COLLECTED_FOR_INDEPENDENT_REVIEW','remote_wrapper_exit_code':remote_exit,'return_zip_sha256':zip_sha,'scientific_status':values.get('CANDIDATE_STATUS','UNKNOWN'),'confirmatory_campaign_authorized':False,'next_gate':values.get('NEXT_GATE','DIAGNOSE_REMOTE_RETURN')}
(evidence/'COLLECTION_STATUS.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
manifest=evidence/'EVIDENCE_MANIFEST.sha256'; lines=[]
for path in sorted(evidence.rglob('*')):
    if path.is_file() and path != manifest: lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(evidence).as_posix())
manifest.write_text('\n'.join(lines)+'\n')
PY
git -C "$GIT_WORK" add -- "$TARGET_REL" "$EVIDENCE_REL"
if ! git -C "$GIT_WORK" diff --cached --quiet; then
  git -C "$GIT_WORK" diff --cached --check
  git -C "$GIT_WORK" commit -m "Collect candidate-v4.2 excluded-seed feasibility evidence" >/dev/null
fi
FINAL_COMMIT="$(git -C "$GIT_WORK" rev-parse HEAD)"
git -C "$GIT_WORK" fetch origin "$BRANCH"
REMOTE_BEFORE_EVIDENCE_PUSH="$(git -C "$GIT_WORK" rev-parse "origin/$BRANCH")"
if [[ "$REMOTE_BEFORE_EVIDENCE_PUSH" != "$SOURCE_COMMIT" && "$REMOTE_BEFORE_EVIDENCE_PUSH" != "$FINAL_COMMIT" ]]; then
  echo "ERROR: remote branch advanced before evidence push; no overwrite attempted"
  echo "REMOTE_HEAD_NEW=$REMOTE_BEFORE_EVIDENCE_PUSH"
  exit 13
fi
git -C "$GIT_WORK" push origin "$BRANCH"
REMOTE_FINAL_COMMIT="$(git -C "$GIT_WORK" ls-remote --heads origin "$BRANCH" | awk '{print $1}')"
[[ "$FINAL_COMMIT" == "$REMOTE_FINAL_COMMIT" ]] || { echo "ERROR: final evidence commit does not equal remote branch"; exit 14; }

REMOTE_SUMMARY="$EXTRACTED_RETURN/slurm/REMOTE_RUN_SUMMARY.env"
RUN_STATUS="$EXTRACTED_RETURN/summary/RUN_STATUS.env"
value_from() { local file=$1 key=$2; [[ -f "$file" ]] && sed -n "s/^${key}=//p" "$file" | tail -n1 || true; }
SLURM_JOB_ID="$(value_from "$REMOTE_SUMMARY" SLURM_JOB_ID)"
SLURM_ACCOUNT="$(value_from "$REMOTE_SUMMARY" SLURM_ACCOUNT)"
SLURM_STATE="$(value_from "$REMOTE_SUMMARY" SLURM_STATE)"
SLURM_EXIT_CODE="$(value_from "$REMOTE_SUMMARY" SLURM_EXIT_CODE)"
SLURM_MAXRSS="$(value_from "$REMOTE_SUMMARY" SLURM_MAXRSS)"
SCIENTIFIC_SCRIPT_EXIT_CODE="$(value_from "$RUN_STATUS" SCIENTIFIC_SCRIPT_EXIT_CODE)"
CANDIDATE_STATUS="$(value_from "$RUN_STATUS" CANDIDATE_STATUS)"
NEXT_GATE="$(value_from "$RUN_STATUS" NEXT_GATE)"; NEXT_GATE="${NEXT_GATE:-DIAGNOSE_REMOTE_RETURN}"
CANDIDATE_LONG="$(value_from "$RUN_STATUS" CANDIDATE_LONG_VIOLATION_SECONDS)"
CANDIDATE_SHORT="$(value_from "$RUN_STATUS" CANDIDATE_SHORT_VIOLATION_SECONDS)"
CANDIDATE_FLOOR="$(value_from "$RUN_STATUS" CANDIDATE_FLOOR_VIOLATION_USER_SECONDS)"
CANDIDATE_FLOOR_INTERVALS="$(value_from "$RUN_STATUS" CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS)"
STRICT_SCOPE="$(value_from "$RUN_STATUS" STRICT_LOCAL_SCOPE_GATE)"
MAX_EXTERNAL="$(value_from "$RUN_STATUS" MAX_EXTERNAL_INTERFERERS_PER_VIOLATING_USER)"
MAX_EESS="$(value_from "$RUN_STATUS" MAX_EESS_BACKOFF_SECTORS)"
CONTINUOUS_INFEASIBLE="$(value_from "$RUN_STATUS" CONTINUOUS_SECTOR_PROVEN_INFEASIBLE_INTERVALS)"
GLOBAL_GRID_INFEASIBLE="$(value_from "$RUN_STATUS" GLOBAL_FROZEN_GRID_PROVEN_INFEASIBLE_INTERVALS)"
LOCAL_GRID_REPAIRED="$(value_from "$RUN_STATUS" LOCAL_FROZEN_GRID_REPAIRED_INTERVALS)"
LOCAL_STREAM_REPAIRED="$(value_from "$RUN_STATUS" LOCAL_STREAM_POWER_REPAIRED_INTERVALS)"
LOCAL_STREAM_INFEASIBLE="$(value_from "$RUN_STATUS" LOCAL_STREAM_POWER_PROVEN_INFEASIBLE_INTERVALS)"
GLOBAL_STREAM_INFEASIBLE="$(value_from "$RUN_STATUS" GLOBAL_STREAM_PROVEN_INFEASIBLE_INTERVALS)"
UNRESOLVED_DEPLOYABLE="$(value_from "$RUN_STATUS" UNRESOLVED_DEPLOYABLE_INTERVALS)"
NETWORK_SHUTDOWN="$(value_from "$RUN_STATUS" NETWORK_WIDE_SHUTDOWN_INTERVALS)"
Q0_GATE="$(value_from "$RUN_STATUS" Q0_POWER_ENVELOPE_GATE)"
MAX_Q0_RATIO="$(value_from "$RUN_STATUS" MAXIMUM_Q0_NOMINAL_POWER_ENVELOPE_RATIO)"
MAX_STRICT_POST_MODE_RATIO="$(value_from "$RUN_STATUS" MAXIMUM_STRICT_POST_MODE_BASELINE_POWER_RATIO)"
Q0_HEADROOM_INTERVALS="$(value_from "$RUN_STATUS" Q0_HEADROOM_USED_INTERVALS)"
STRICT_POST_MODE_FEASIBLE="$(value_from "$RUN_STATUS" STRICT_POST_MODE_STREAM_FEASIBLE_INTERVALS)"
STRICT_POST_MODE_INFEASIBLE="$(value_from "$RUN_STATUS" STRICT_POST_MODE_STREAM_INFEASIBLE_INTERVALS)"
MIN_MODE_TO_Q0_RATIO="$(value_from "$RUN_STATUS" MINIMUM_MODE_ADJUSTED_TO_Q0_POWER_RATIO)"
MAX_MODE_TO_Q0_RATIO="$(value_from "$RUN_STATUS" MAXIMUM_MODE_ADJUSTED_TO_Q0_POWER_RATIO)"
CHANNEL_SHA="$(value_from "$REMOTE_SUMMARY" CHANNEL_RECORD_SHA256)"
ARRAY_SHA="$(value_from "$REMOTE_SUMMARY" FREQUENCY_RESPONSE_ARRAY_SHA256)"
SOURCE_MANIFEST_SHA="$(value_from "$REMOTE_SUMMARY" SOURCE_PAYLOAD_MANIFEST_SHA256)"

FINAL_EXIT="$REMOTE_WRAPPER_EXIT_CODE"
printf '%s\n' \
  '=================================================================' \
  'FR3 FLOOR-FEASIBILITY CANDIDATE V4.2 — FINAL REPORT' \
  '=================================================================' \
  "LOCAL_WRAPPER_EXIT_CODE=$FINAL_EXIT" \
  "REMOTE_WRAPPER_EXIT_CODE=$REMOTE_WRAPPER_EXIT_CODE" \
  "DIAGNOSTIC_RETRIEVAL_EXIT_CODE=$RETRIEVAL_EXIT_CODE" \
  "SCIENTIFIC_SCRIPT_EXIT_CODE=${SCIENTIFIC_SCRIPT_EXIT_CODE:-UNKNOWN}" \
  "SLURM_JOB_ID=${SLURM_JOB_ID:-UNKNOWN}" \
  "SLURM_ACCOUNT=${SLURM_ACCOUNT:-UNKNOWN}" \
  "SLURM_STATE=${SLURM_STATE:-UNKNOWN}" \
  "SLURM_EXIT_CODE=${SLURM_EXIT_CODE:-UNKNOWN}" \
  "SLURM_MAXRSS=${SLURM_MAXRSS:-UNKNOWN}" \
  "REMOTE_PAYLOAD_SHA256=$PAYLOAD_SHA" \
  "SOURCE_PAYLOAD_MANIFEST_SHA256=${SOURCE_MANIFEST_SHA:-UNKNOWN}" \
  "REMOTE_RETURN_ZIP_SHA256=$LOCAL_RETURN_ZIP_SHA256" \
  "LOCAL_RETURN_ZIP_SHA256=$LOCAL_RETURN_ZIP_SHA256" \
  "CHANNEL_RECORD_SHA256=${CHANNEL_SHA:-UNKNOWN}" \
  "FREQUENCY_RESPONSE_ARRAY_SHA256=${ARRAY_SHA:-UNKNOWN}" \
  "CANDIDATE_STATUS=${CANDIDATE_STATUS:-UNKNOWN}" \
  "CANDIDATE_LONG_VIOLATION_SECONDS=${CANDIDATE_LONG:-UNKNOWN}" \
  "CANDIDATE_SHORT_VIOLATION_SECONDS=${CANDIDATE_SHORT:-UNKNOWN}" \
  "CANDIDATE_FLOOR_VIOLATION_USER_SECONDS=${CANDIDATE_FLOOR:-UNKNOWN}" \
  "CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS=${CANDIDATE_FLOOR_INTERVALS:-UNKNOWN}" \
  "STRICT_LOCAL_SCOPE_GATE=${STRICT_SCOPE:-UNKNOWN}" \
  "MAX_EXTERNAL_INTERFERERS_PER_VIOLATING_USER=${MAX_EXTERNAL:-UNKNOWN}" \
  "MAX_EESS_BACKOFF_SECTORS=${MAX_EESS:-UNKNOWN}" \
  "CONTINUOUS_SECTOR_PROVEN_INFEASIBLE_INTERVALS=${CONTINUOUS_INFEASIBLE:-UNKNOWN}" \
  "GLOBAL_FROZEN_GRID_PROVEN_INFEASIBLE_INTERVALS=${GLOBAL_GRID_INFEASIBLE:-UNKNOWN}" \
  "LOCAL_FROZEN_GRID_REPAIRED_INTERVALS=${LOCAL_GRID_REPAIRED:-UNKNOWN}" \
  "LOCAL_STREAM_POWER_REPAIRED_INTERVALS=${LOCAL_STREAM_REPAIRED:-UNKNOWN}" \
  "LOCAL_STREAM_POWER_PROVEN_INFEASIBLE_INTERVALS=${LOCAL_STREAM_INFEASIBLE:-UNKNOWN}" \
  "GLOBAL_STREAM_PROVEN_INFEASIBLE_INTERVALS=${GLOBAL_STREAM_INFEASIBLE:-UNKNOWN}" \
  "UNRESOLVED_DEPLOYABLE_INTERVALS=${UNRESOLVED_DEPLOYABLE:-UNKNOWN}" \
  "NETWORK_WIDE_SHUTDOWN_INTERVALS=${NETWORK_SHUTDOWN:-UNKNOWN}" \
  "Q0_POWER_ENVELOPE_GATE=${Q0_GATE:-UNKNOWN}" \
  "MAXIMUM_Q0_NOMINAL_POWER_ENVELOPE_RATIO=${MAX_Q0_RATIO:-UNKNOWN}" \
  "MAXIMUM_STRICT_POST_MODE_BASELINE_POWER_RATIO=${MAX_STRICT_POST_MODE_RATIO:-UNKNOWN}" \
  "Q0_HEADROOM_USED_INTERVALS=${Q0_HEADROOM_INTERVALS:-UNKNOWN}" \
  "STRICT_POST_MODE_STREAM_FEASIBLE_INTERVALS=${STRICT_POST_MODE_FEASIBLE:-UNKNOWN}" \
  "STRICT_POST_MODE_STREAM_INFEASIBLE_INTERVALS=${STRICT_POST_MODE_INFEASIBLE:-UNKNOWN}" \
  "MINIMUM_MODE_ADJUSTED_TO_Q0_POWER_RATIO=${MIN_MODE_TO_Q0_RATIO:-UNKNOWN}" \
  "MAXIMUM_MODE_ADJUSTED_TO_Q0_POWER_RATIO=${MAX_MODE_TO_Q0_RATIO:-UNKNOWN}" \
  "GIT_HEAD_BEFORE=$LOCAL_HEAD_BEFORE" \
  "GIT_REMOTE_HEAD_BEFORE=$REMOTE_HEAD_BEFORE" \
  "CANDIDATE_SOURCE_COMMIT=$SOURCE_COMMIT" \
  "GIT_FINAL_COMMIT=$FINAL_COMMIT" \
  "GIT_REMOTE_FINAL_COMMIT=$REMOTE_FINAL_COMMIT" \
  'CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO' \
  "NEXT_GATE=$NEXT_GATE" \
  "FILES_TO_RETURN_FOLDER=$LOCAL_RETURN" \
  "RETURN_TO_CHATGPT=$RETURN_ZIP" \
  "RETURN_TO_CHATGPT=$RETURN_SHA" \
  "RETURN_TO_CHATGPT=$LOCAL_LOG" \
  '================================================================='
FINAL_REPORT_PRINTED=1
exit "$FINAL_EXIT"
