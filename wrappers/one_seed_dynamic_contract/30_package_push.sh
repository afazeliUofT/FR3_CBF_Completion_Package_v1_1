#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

find scripts tests src \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find scripts tests src \
  -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache tests/.pytest_cache

STAGE=(
  .gitattributes
  config/one_seed_18658301_freeze.json
  config/dynamic_safety_experiment_v1.yaml
  config/controller_ready_full_topology_export_v1.yaml
  config/current_audited_state.yaml
  src/fr3_cbf/physical_accounting.py
  scripts/32_0_freeze_nibi_one_seed_18658301.py
  scripts/32_1_validate_one_seed_18658301_freeze.py
  scripts/32_2_sync_status_and_contract.py
  scripts/32_3_build_one_seed_review_bundle.py
  tests/test_one_seed_dynamic_contract.py
  docs/DYNAMIC_SAFETY_EXPERIMENT_CONTRACT.md
  docs/CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_SPEC.md
  wrappers/one_seed_dynamic_contract
  RUN_ONE_SEED_FREEZE_AND_DYNAMIC_CONTRACT_DROPIN.sh
  README_ONE_SEED_FREEZE_AND_DYNAMIC_CONTRACT.md
  ONE_SEED_DYNAMIC_CONTRACT_DROPIN_MANIFEST.sha256
  ONE_SEED_DYNAMIC_CONTRACT_TEST_REPORT.txt
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  ROADMAP.md
  COMPUTE_EXECUTION_STATUS.md
  NIBI_FR3_EXECUTION_SUPERSEDED.md
  evidence/nibi_one_seed_18658301
)

git add -- "${STAGE[@]}"
# Strictly check all authored changes. The sole exclusion is an immutable
# byte-preserved Slurm stdout mirror whose timestamp line contains source
# trailing spaces. Its bytes are verified by the evidence manifest and the
# index/worktree identity check below.
git diff --cached --check -- . \
  ':(exclude)evidence/nibi_one_seed_18658301/source/pilot-18658301.out'

sha256sum -c \
  evidence/nibi_one_seed_18658301/EVIDENCE_MANIFEST.sha256

python3 - <<'PYINDEX'
from pathlib import Path
import hashlib
import subprocess

root = Path("evidence/nibi_one_seed_18658301")
mismatches = []
checked = 0
for path in sorted(root.rglob("*")):
    if not path.is_file():
        continue
    relative = path.as_posix()
    indexed = subprocess.check_output(["git", "show", f":{relative}"])
    working = path.read_bytes()
    if hashlib.sha256(indexed).digest() != hashlib.sha256(working).digest():
        mismatches.append(relative)
    checked += 1

if mismatches:
    raise SystemExit(
        "Index/worktree byte mismatches in immutable evidence: "
        + ", ".join(mismatches)
    )
print(f"IMMUTABLE EVIDENCE INDEX/WORKTREE IDENTITY: PASS ({checked} files)")
PYINDEX

git commit -m \
  "Freeze Nibi one-seed gate and dynamic TWC experiment contract"
git push

COMMIT="$(git rev-parse HEAD)"
REVIEW="evidence/nibi_one_seed_18658301/FR3_ONE_SEED_18658301_DYNAMIC_CONTRACT_REVIEW_v1.zip"
SHA="${REVIEW}.sha256"

(
  cd "$(dirname "$REVIEW")"
  sha256sum -c "$(basename "$SHA")"
  unzip -t "$(basename "$REVIEW")"
)

echo "ONE-SEED FREEZE/DYNAMIC CONTRACT PACKAGE PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Review bundle: $ROOT/$REVIEW"
echo "Review bundle SHA-256: $(sha256sum "$REVIEW" | awk '{print $1}')"
echo "Next gate: INDEPENDENT_REVIEW_THEN_PREPARE_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT"
