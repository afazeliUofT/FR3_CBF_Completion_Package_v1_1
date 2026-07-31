#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: expected branch e3-first-sector-p452"
  exit 2
}
git merge-base --is-ancestor \
  9f3c6ffda7d4c6117406ad1b54ef16404590b32b HEAD

git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

for path in \
  campaign/phase1_candidate_v3/FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip \
  campaign/phase1_candidate_v3/PHASE1_CAMPAIGN_CONTRACT_V3.json \
  campaign/phase1_candidate_v3/source_snapshot/SOURCE_SNAPSHOT_MANIFEST.sha256 \
  evidence/phase1_candidate_v3_round2_review/PHASE1_ROUND2_REVIEW_VERDICT.json \
  evidence/phase1_candidate_v3_round2_review/FR3_PHASE1_CANDIDATE_V3_ROUND2_REVIEW_v1.zip \
  evidence/controller_ready_full_topology_export_prep/FR3_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_NIBI_v1.zip \
  nibi/controller_ready_full_topology_export_v1/run_full_topology_export.py \
  nibi/controller_ready_full_topology_export_v1/export_config.json \
  data/real/full_topology_export_18696267_validated_v4/output/frequency_response.npy \
  data/real/full_topology_export_18696267_validated_v4/output/FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json
 do
  [[ -e "$path" ]] || {
    echo "ERROR: required job-package input is missing: $path"
    exit 4
  }
  echo "OK      $path"
done

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
import hashlib
import json
import tempfile
import zipfile

root = Path.cwd()
cfg = json.loads(
    (root / "config/phase1_nibi_job_package_builder_v1.json").read_text(
        encoding="utf-8"
    )
)
source_cfg = cfg["full_topology_source_bundle"]
bundle = root / source_cfg["path"]

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

if sha256_file(bundle) != source_cfg["sha256"]:
    raise SystemExit("ERROR: reviewed full-topology source-bundle SHA mismatch")
with tempfile.TemporaryDirectory(prefix="fr3_fulltopo_preflight_") as name:
    extracted = Path(name)
    with zipfile.ZipFile(bundle) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise SystemExit(f"ERROR: corrupt source-bundle member: {bad}")
        archive.extractall(extracted)
    manifest = extracted / "BUNDLE_MANIFEST.sha256"
    count = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = extracted / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise SystemExit(f"ERROR: source-bundle manifest mismatch: {relative}")
        count += 1
    metadata = json.loads(
        (extracted / "BUNDLE_METADATA.json").read_text(encoding="utf-8")
    )
    for key in [
        "review_zip_sha256",
        "executed_input_bundle_sha256",
        "return_bundle_sha256",
    ]:
        if metadata.get(key) != source_cfg[key]:
            raise SystemExit(f"ERROR: source-bundle metadata mismatch: {key}")
    for relative, expected in source_cfg["expected_input_sha256"].items():
        path = extracted / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise SystemExit(f"ERROR: source input mismatch: {relative}")
print("REVIEWED FULL-TOPOLOGY SOURCE BUNDLE PREFLIGHT: PASS")
print("Manifest entries:", count)
print("Bound channel-generator inputs:", len(source_cfg["expected_input_sha256"]))
PY

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_phase1_nibi_job_package_builder.py

echo "PHASE-1 NIBI JOB-PACKAGE PREFLIGHT: PASS"
