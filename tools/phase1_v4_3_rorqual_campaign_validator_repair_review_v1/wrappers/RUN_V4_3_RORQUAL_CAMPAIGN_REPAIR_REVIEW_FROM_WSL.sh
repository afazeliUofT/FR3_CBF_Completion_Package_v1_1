#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE_ROOT="${1:?package root is required}"
DOWNLOADS="${FR3_DOWNLOADS:-/mnt/c/Users/alifa/Downloads}"
REPO="${FR3_REPO_ROOT:?FR3_REPO_ROOT is required}"
BRANCH="e3-first-sector-p452"
REQUIRED_ANCESTOR="fa00b2a4d81b98a2089c992f56fdca63e23c24f3"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
RETURN_DIR="$DOWNLOADS/FR3_V4_3_RORQUAL_CAMPAIGN_REPAIR_REVIEW_RETURN_$STAMP"
WORK="$HOME/fr3_v4_3_rorqual_campaign_repair_review_runs/$STAMP"
AUDIT="$WORK/audit"
BUILD="$WORK/build"
REVIEW="$WORK/review"
CLONE="$WORK/github_working_clone"
LOG="$RETURN_DIR/LOCAL_WSL_ORCHESTRATOR.log"
STATUS_FILE="$WORK/WORKFLOW_STATUS.env"
mkdir -p "$RETURN_DIR" "$WORK"

GIT_HEAD_BEFORE="NOT_AVAILABLE"
GIT_REMOTE_HEAD_BEFORE="NOT_AVAILABLE"
GIT_REPAIR_REVIEW_COMMIT="NOT_AVAILABLE"
GIT_FINAL_COMMIT="NOT_AVAILABLE"
GIT_REMOTE_FINAL_COMMIT="NOT_AVAILABLE"
GITHUB_NEWER_WORK_OVERWRITTEN="NO"
WORKFLOW_RC=0
RETURN_PACKAGING_RC=99

workflow() {
  echo "================================================================="
  echo "FR3 V4.3 — RORQUAL CAMPAIGN VALIDATOR REPAIR AND LOCKED REVIEW"
  echo "================================================================="
  printf '%s\n' \
    "PACKAGE_ROOT=$PACKAGE_ROOT" \
    "REPO=$REPO" \
    "NIBI_REQUIRED=NO" \
    "RORQUAL_REQUIRED=NO" \
    "CLUSTER_CONTACTED=NO" \
    "CAMPAIGN_EXECUTION_AUTHORIZED=NO"

  (
    cd "$PACKAGE_ROOT"
    sha256sum -c PACKAGE_MANIFEST.sha256 >/dev/null
    sha256sum -c SOURCE_PAYLOAD_MANIFEST.sha256 >/dev/null
  )
  echo "INTERNAL_MANIFEST_VERIFICATION=PASS"
  echo "SOURCE_PAYLOAD_MANIFEST_VERIFICATION=PASS"

  VENV="$REPO/.venv"
  if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
  fi
  source "$VENV/bin/activate"
  PYTHON="$(command -v python)"
  [[ "$PYTHON" == "$VENV/bin/python" ]]
  echo "REPO_VENV_ACTIVATED=YES"
  if ! "$PYTHON" - <<'PY' >/dev/null 2>&1
import numpy, pandas, scipy, pytest
PY
  then
    "$PYTHON" -m pip install -r "$PACKAGE_ROOT/requirements.txt"
  fi
  "$PYTHON" - <<'PY' >/dev/null
import numpy, pandas, scipy, pytest
PY
  echo "LOCAL_VENV_DEPENDENCY_GATE=PASS"

  "$PYTHON" - "$PACKAGE_ROOT" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
files=sorted(root.rglob('*.py'))
for path in files:
    compile(path.read_bytes(), str(path), 'exec')
print('PYTHON_IN_MEMORY_SYNTAX_CHECK=PASS')
print('PYTHON_SYNTAX_FILE_COUNT=' + str(len(files)))
PY
  while IFS= read -r script; do
    bash -n "$script"
  done < <(find "$PACKAGE_ROOT" -type f \( -name '*.sh' -o -name '*.sbatch' \) -print)
  echo "BASH_SYNTAX_CHECK=PASS"
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m pytest -q -p no:cacheprovider "$PACKAGE_ROOT/tests"

  ORIGIN="$(git -C "$REPO" remote get-url origin)"
  git clone --branch "$BRANCH" --single-branch "$ORIGIN" "$CLONE"
  git -C "$CLONE" fetch origin "$BRANCH"
  git -C "$CLONE" reset --hard "origin/$BRANCH"
  GIT_HEAD_BEFORE="$(git -C "$REPO" rev-parse HEAD)"
  GIT_REMOTE_HEAD_BEFORE="$(git -C "$CLONE" rev-parse HEAD)"
  git -C "$CLONE" merge-base --is-ancestor "$REQUIRED_ANCESTOR" HEAD
  echo "GITHUB_REQUIRED_ANCESTOR_GATE=PASS"
  printf '%s\n' \
    "GIT_HEAD_BEFORE=$GIT_HEAD_BEFORE" \
    "GIT_REMOTE_HEAD_BEFORE=$GIT_REMOTE_HEAD_BEFORE" \
    "GITHUB_NEWER_WORK_OVERWRITTEN=NO"

  "$PYTHON" "$PACKAGE_ROOT/scripts/audit_and_reclassify_smoke.py" \
    --output-root "$AUDIT"
  "$PYTHON" "$PACKAGE_ROOT/scripts/build_rorqual_campaign_package.py" \
    --audit-root "$AUDIT" \
    --output-root "$BUILD"
  "$PYTHON" "$PACKAGE_ROOT/scripts/independent_review_rorqual_campaign.py" \
    --audit-root "$AUDIT" \
    --build-root "$BUILD" \
    --output-root "$REVIEW"

  SMOKE_EVIDENCE="$CLONE/evidence/phase1_v4_3_rorqual_final_worker_smoke_v1_job_18132931"
  CAMPAIGN_DIR="$CLONE/campaign/phase1_rorqual_job_package_v4_3_r2"
  REVIEW_DIR="$CLONE/evidence/phase1_rorqual_job_package_v4_3_r2_review"
  TOOL_DIR="$CLONE/tools/phase1_v4_3_rorqual_campaign_validator_repair_review_v1"
  for target in "$SMOKE_EVIDENCE" "$CAMPAIGN_DIR" "$REVIEW_DIR" "$TOOL_DIR"; do
    if [[ -e "$target" ]]; then
      echo "ERROR_EXISTING_TARGET_PATH_REFUSED=$target"
      return 73
    fi
  done
  mkdir -p "$SMOKE_EVIDENCE" "$CAMPAIGN_DIR/source_snapshot" "$REVIEW_DIR" "$TOOL_DIR"

  cp "$AUDIT/SMOKE_RECLASSIFICATION_VERDICT.json" "$SMOKE_EVIDENCE/"
  cp "$AUDIT/GEOMETRIC_MEAN_DEFINITION_AUDIT.csv" "$SMOKE_EVIDENCE/"
  cp "$AUDIT/EXCLUDED_SEED_PAIRED_EFFECT_SUMMARY.csv" "$SMOKE_EVIDENCE/"
  cp "$AUDIT/CORRECTED_VALIDATOR_STRUCTURAL.log" "$SMOKE_EVIDENCE/"
  cp "$AUDIT/CORRECTED_VALIDATOR_SCIENTIFIC.log" "$SMOKE_EVIDENCE/"
  cp "$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_3_FINAL_WORKER_SMOKE_43999_18132931.zip.sha256" "$SMOKE_EVIDENCE/"
  "$PYTHON" - "$PACKAGE_ROOT/immutable_bindings/FR3_RORQUAL_V4_3_FINAL_WORKER_SMOKE_43999_18132931.zip" "$SMOKE_EVIDENCE" <<'PY'
from pathlib import Path
import sys, zipfile
archive=Path(sys.argv[1]); out=Path(sys.argv[2])
with zipfile.ZipFile(archive) as z:
    roots={Path(n).parts[0] for n in z.namelist() if n and not n.endswith('/')}
    if len(roots)!=1: raise SystemExit('unexpected return root')
    root=next(iter(roots))
    mapping={
      f'{root}/RETURN_METADATA.json':'RETURN_METADATA.json',
      f'{root}/provenance/FINAL_WORKER_SMOKE_AUDIT.json':'LEGACY_FINAL_WORKER_SMOKE_AUDIT.json',
      f'{root}/result/SEED_RESULT.json':'SEED_RESULT.json',
      f'{root}/result/CELL_SUMMARY.csv':'CELL_SUMMARY.csv',
      f'{root}/result/PRIMARY_PAIRED_EFFECTS.csv':'PRIMARY_PAIRED_EFFECTS.csv',
      f'{root}/channel/CHANNEL_RECORD.json':'CHANNEL_RECORD.json',
      f'{root}/logs/sacct-18132931.txt':'sacct-18132931.txt',
    }
    for source,target in mapping.items():
        (out/target).write_bytes(z.read(source))
PY

  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip" "$CAMPAIGN_DIR/"
  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip.sha256" "$CAMPAIGN_DIR/"
  cp "$BUILD/BUILD_AUDIT.json" "$CAMPAIGN_DIR/"
  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_ROOT/JOB_PACKAGE_CONTRACT.json" "$CAMPAIGN_DIR/"
  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_ROOT/PHASE1_CAMPAIGN_CONTRACT_V4_3.json" "$CAMPAIGN_DIR/"
  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_ROOT/RESULT_SCHEMA.json" "$CAMPAIGN_DIR/"
  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_ROOT/AUTHORIZATION_TOKEN_TEMPLATE.json" "$CAMPAIGN_DIR/"
  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_ROOT/README_JOB_PACKAGE.md" "$CAMPAIGN_DIR/"
  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_ROOT/validate_seed_result.py" "$CAMPAIGN_DIR/source_snapshot/"
  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_ROOT/validate_merged_results.py" "$CAMPAIGN_DIR/source_snapshot/"
  cp "$BUILD/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_ROOT/validator_contract.py" "$CAMPAIGN_DIR/source_snapshot/"

  cp "$REVIEW/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_INDEPENDENT_REVIEW.zip" "$REVIEW_DIR/"
  cp "$REVIEW/FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_INDEPENDENT_REVIEW.zip.sha256" "$REVIEW_DIR/"
  cp "$REVIEW/INDEPENDENT_REVIEW_VERDICT.json" "$REVIEW_DIR/"
  cp "$REVIEW/REVIEW_CHECK_SUMMARY.json" "$REVIEW_DIR/"
  cp "$AUDIT/SMOKE_RECLASSIFICATION_VERDICT.json" "$REVIEW_DIR/"

  for item in PACKAGE_VERSION.json README.md requirements.txt config docs scripts templates tests wrappers; do
    if [[ -e "$PACKAGE_ROOT/$item" ]]; then
      cp -a "$PACKAGE_ROOT/$item" "$TOOL_DIR/"
    fi
  done
  rm -rf "$TOOL_DIR"/**/__pycache__ "$TOOL_DIR"/**/.pytest_cache 2>/dev/null || true
  find "$TOOL_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

  # Normalize only the GitHub copy of the human-readable orchestrator log.
  "$PYTHON" - "$LOG" "$SMOKE_EVIDENCE/LOCAL_WSL_ORCHESTRATOR.log" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]); target=Path(sys.argv[2])
text=source.read_text(encoding='utf-8',errors='replace') if source.exists() else ''
target.write_text('\n'.join(line.rstrip() for line in text.splitlines())+'\n',encoding='utf-8')
PY

  git -C "$CLONE" add \
    "evidence/phase1_v4_3_rorqual_final_worker_smoke_v1_job_18132931" \
    "campaign/phase1_rorqual_job_package_v4_3_r2" \
    "evidence/phase1_rorqual_job_package_v4_3_r2_review" \
    "tools/phase1_v4_3_rorqual_campaign_validator_repair_review_v1"
  git -C "$CLONE" diff --cached --check
  git -C "$CLONE" -c user.name="Ali Fazeli" -c user.email="ali.fazeli@utoronto.ca" \
    commit -m "Repair v4.3 campaign validators and review Rorqual-native locked package"
  GIT_REPAIR_REVIEW_COMMIT="$(git -C "$CLONE" rev-parse HEAD)"

  git -C "$CLONE" fetch origin "$BRANCH"
  CURRENT_REMOTE="$(git -C "$CLONE" rev-parse "origin/$BRANCH")"
  PARENT="$(git -C "$CLONE" rev-parse HEAD^)"
  if [[ "$CURRENT_REMOTE" != "$PARENT" ]]; then
    echo "ERROR_STALE_NONFORCE_PUSH_REFUSED=YES"
    echo "REMOTE_HEAD_NOW=$CURRENT_REMOTE"
    echo "LOCAL_COMMIT_PARENT=$PARENT"
    return 74
  fi
  git -C "$CLONE" push origin "HEAD:$BRANCH"
  GIT_FINAL_COMMIT="$(git -C "$CLONE" rev-parse HEAD)"
  git -C "$CLONE" fetch origin "$BRANCH"
  GIT_REMOTE_FINAL_COMMIT="$(git -C "$CLONE" rev-parse "origin/$BRANCH")"
  [[ "$GIT_FINAL_COMMIT" == "$GIT_REMOTE_FINAL_COMMIT" ]]
  cat > "$STATUS_FILE" <<EOF
GIT_HEAD_BEFORE=$GIT_HEAD_BEFORE
GIT_REMOTE_HEAD_BEFORE=$GIT_REMOTE_HEAD_BEFORE
GIT_REPAIR_REVIEW_COMMIT=$GIT_REPAIR_REVIEW_COMMIT
GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT
GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT
GITHUB_NEWER_WORK_OVERWRITTEN=NO
EOF

  printf '%s\n' \
    "GIT_REPAIR_REVIEW_COMMIT=$GIT_REPAIR_REVIEW_COMMIT" \
    "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT" \
    "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT" \
    "GITHUB_NEWER_WORK_OVERWRITTEN=NO" \
    "CLUSTER_CONTACTED=NO" \
    "CAMPAIGN_EXECUTION_AUTHORIZED=NO" \
    "NEXT_GATE=SEPARATE_RORQUAL_30_SEED_CAMPAIGN_AUTHORIZATION_AND_EXECUTION"
}

set +e
(
  set -Eeuo pipefail
  workflow
) > >(tee "$LOG") 2>&1
WORKFLOW_RC=$?
wait || true
set -e

if [[ -f "$STATUS_FILE" ]]; then
  source "$STATUS_FILE"
fi
if [[ -d "$CLONE" ]]; then
  rm -rf "$CLONE"
fi
echo "LOCAL_RETURN_GITHUB_CLONE_REMOVED=PASS" | tee -a "$LOG"

PACKAGER_PYTHON="$REPO/.venv/bin/python"
if [[ ! -x "$PACKAGER_PYTHON" ]]; then
  PACKAGER_PYTHON="$(command -v python3)"
fi
if "$PACKAGER_PYTHON" "$PACKAGE_ROOT/scripts/package_local_return.py" \
    --return-dir "$RETURN_DIR" \
    --audit-root "$AUDIT" \
    --build-root "$BUILD" \
    --review-root "$REVIEW" \
    --log "$LOG" \
    --workflow-exit-code "$WORKFLOW_RC" \
    --git-final-commit "$GIT_FINAL_COMMIT" \
    --git-remote-final-commit "$GIT_REMOTE_FINAL_COMMIT" | tee -a "$LOG"; then
  RETURN_PACKAGING_RC=0
else
  RETURN_PACKAGING_RC=$?
fi

printf '%s\n' \
  "LOCAL_WRAPPER_EXIT_CODE=$WORKFLOW_RC" \
  "RETURN_PACKAGING_EXIT_CODE=$RETURN_PACKAGING_RC" \
  "GIT_HEAD_BEFORE=$GIT_HEAD_BEFORE" \
  "GIT_REMOTE_HEAD_BEFORE=$GIT_REMOTE_HEAD_BEFORE" \
  "GIT_REPAIR_REVIEW_COMMIT=$GIT_REPAIR_REVIEW_COMMIT" \
  "GIT_FINAL_COMMIT=$GIT_FINAL_COMMIT" \
  "GIT_REMOTE_FINAL_COMMIT=$GIT_REMOTE_FINAL_COMMIT" \
  "GITHUB_NEWER_WORK_OVERWRITTEN=$GITHUB_NEWER_WORK_OVERWRITTEN" \
  "CLUSTER_CONTACTED=NO" \
  "CAMPAIGN_EXECUTION_AUTHORIZED=NO" \
  "NEXT_GATE=SEPARATE_RORQUAL_30_SEED_CAMPAIGN_AUTHORIZATION_AND_EXECUTION" \
  "FILES_TO_RETURN_FOLDER=$RETURN_DIR" \
  "WSL_TERMINAL_CLOSE_REQUESTED=NO" | tee -a "$LOG"

if command -v explorer.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$RETURN_DIR")" >/dev/null 2>&1 || true
fi

if [[ "$WORKFLOW_RC" -ne 0 ]]; then
  exit "$WORKFLOW_RC"
fi
exit "$RETURN_PACKAGING_RC"
