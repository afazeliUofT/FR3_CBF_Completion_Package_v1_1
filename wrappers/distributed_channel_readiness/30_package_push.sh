#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

EVIDENCE="evidence/distributed_channel_readiness"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"

cp \
  data/real/distributed_channel_readiness/DISTRIBUTED_ARCHITECTURE_INDEPENDENT_REVIEW.json \
  data/real/distributed_channel_readiness/DISTRIBUTED_ARCHITECTURE_INDEPENDENT_REVIEW.md \
  data/real/distributed_channel_readiness/ARCHITECTURE_MANIFEST_REPAIR.json \
  data/real/distributed_channel_readiness/STANDARDS_ALIGNED_DLP_RZF_EXPERIMENT_SPEC.json \
  data/real/distributed_channel_readiness/STANDARDS_ALIGNED_DLP_RZF_EXPERIMENT_SPEC.md \
  "$EVIDENCE/"

cat > "$EVIDENCE/README.md" <<'EOF'
# Distributed channel-experiment readiness

This evidence independently reviews the distributed leakage-projected RZF
architecture, repairs the architecture package manifest, and freezes the next
standards-aligned experiment specification.

The adjacent `evidence/fr3_channel_baseline_snapshot/` directory contains a
human-reviewed text-only source snapshot for code-level reuse. WMMSE is not
adopted as the operational method.
EOF

python3 - <<'PY'
from hashlib import sha256
from pathlib import Path
for root_name in [
    "evidence/distributed_channel_readiness",
    "evidence/fr3_channel_baseline_snapshot",
]:
    root = Path(root_name)
    manifest = root / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("MANIFEST", manifest, len(lines))
PY

STAGE=(
  config/distributed_channel_readiness.yaml
  scripts/28_0_review_distributed_architecture.py
  scripts/28_1_repair_architecture_manifest.py
  scripts/28_2_collect_fr3_channel_snapshot.py
  scripts/28_3_freeze_standards_experiment.py
  tests/test_distributed_channel_readiness.py
  DISTRIBUTED_IA_RZF_ARCHITECTURE_MANIFEST.sha256
  RUN_DISTRIBUTED_CHANNEL_READINESS_DROPIN.sh
  README_DISTRIBUTED_CHANNEL_READINESS.md
  DISTRIBUTED_CHANNEL_READINESS_MANIFEST.sha256
  DISTRIBUTED_CHANNEL_READINESS_TEST_REPORT.txt
  wrappers/distributed_channel_readiness
  evidence/distributed_channel_readiness
  evidence/fr3_channel_baseline_snapshot
)

# Remove any cache/bytecode files that were accidentally tracked by the
# previous architecture commit. .gitignore does not untrack existing files.
mapfile -t TRACKED_CACHE_PATHS < <(
  git ls-files   | grep -E '(^|/)(__pycache__|\.pytest_cache)(/|$)|\.(pyc|pyo)$'   || true
)
if ((${#TRACKED_CACHE_PATHS[@]} > 0)); then
  printf 'REMOVING TRACKED CACHE ARTIFACT: %s\n' "${TRACKED_CACHE_PATHS[@]}"
  git rm -f --cached --ignore-unmatch -- "${TRACKED_CACHE_PATHS[@]}"
fi

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c evidence/distributed_channel_readiness/EVIDENCE_MANIFEST.sha256
sha256sum -c evidence/fr3_channel_baseline_snapshot/EVIDENCE_MANIFEST.sha256

git commit -m "Review distributed architecture and snapshot FR3 channel baseline"
git push
COMMIT="$(git rev-parse HEAD)"

echo "WRAPPER 30 PACKAGE/PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "NEXT REVIEW FILES:"
echo "  evidence/distributed_channel_readiness/DISTRIBUTED_ARCHITECTURE_INDEPENDENT_REVIEW.json"
echo "  evidence/distributed_channel_readiness/STANDARDS_ALIGNED_DLP_RZF_EXPERIMENT_SPEC.json"
echo "  evidence/fr3_channel_baseline_snapshot/SNAPSHOT_METADATA.json"
echo "  evidence/fr3_channel_baseline_snapshot/SOURCE_INVENTORY.csv"
echo "  evidence/fr3_channel_baseline_snapshot/BINARY_CANDIDATES.csv"
echo "  evidence/fr3_channel_baseline_snapshot/REVIEW_PRIORITY.md"
echo "  evidence/fr3_channel_baseline_snapshot/source/"
