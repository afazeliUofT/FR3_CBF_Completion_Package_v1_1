#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

EVIDENCE="evidence/distributed_ia_rzf_architecture"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE/work" "$EVIDENCE/review"

cp \
  data/real/distributed_ia_rzf_architecture/DISTRIBUTED_IA_RZF_ARCHITECTURE_DECISION.json \
  data/real/distributed_ia_rzf_architecture/DISTRIBUTED_ARCHITECTURE_STATUS_SYNC.json \
  data/real/distributed_ia_rzf_architecture/prototype_static_sector_models.csv \
  data/real/distributed_ia_rzf_architecture/prototype_sector_time_metrics.csv.gz \
  data/real/distributed_ia_rzf_architecture/prototype_time_summary.csv \
  data/real/distributed_ia_rzf_architecture/DISTRIBUTED_IA_RZF_PROTOTYPE_AUDIT.json \
  data/real/distributed_ia_rzf_architecture/DISTRIBUTED_IA_RZF_VALIDATION.json \
  data/real/distributed_ia_rzf_architecture/DISTRIBUTED_IA_RZF_VALIDATION.md \
  "$EVIDENCE/work/"

cp \
  results/distributed_ia_rzf_architecture/prototype_aggregate_interference.png \
  results/distributed_ia_rzf_architecture/prototype_rate_retention.png \
  results/distributed_ia_rzf_architecture/prototype_peak_projection_scales.png \
  "$EVIDENCE/review/"

cat > "$EVIDENCE/README.md" <<'EOF'
# Distributed local RZF and certified leakage-budget architecture

This evidence replaces WMMSE as the main operational architecture. Each BS
uses only local UE CSI, one local incumbent steering vector, and one scalar
received-interference budget.

The included 57-sector run uses deterministic seeded local channels only to
audit the software and aggregate certificate. It is not the standards-aligned
paper channel experiment.
EOF

python3 - <<'PY'
from hashlib import sha256
from pathlib import Path
root = Path("evidence/distributed_ia_rzf_architecture")
manifest = root / "EVIDENCE_MANIFEST.sha256"
lines = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path != manifest:
        lines.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.as_posix()}")
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("EVIDENCE MANIFEST:", manifest, len(lines))
PY

STAGE=(
  config/distributed_ia_rzf_architecture.yaml
  src/fr3_cbf/distributed_precoding.py
  scripts/27_0_freeze_distributed_ia_rzf_architecture.py
  scripts/27_1_run_distributed_ia_rzf_prototype.py
  scripts/27_2_validate_distributed_ia_rzf.py
  tests/test_distributed_precoding.py
  docs/DISTRIBUTED_IA_RZF_ARCHITECTURE.md
  paper_ready/distributed_ia_rzf_system_model.tex
  PROJECT_STATUS.md
  NEXT_IMMEDIATE_STEP.md
  config/current_audited_state.yaml
  RUN_DISTRIBUTED_IA_RZF_ARCHITECTURE_DROPIN.sh
  README_DISTRIBUTED_IA_RZF_ARCHITECTURE.md
  DISTRIBUTED_IA_RZF_ARCHITECTURE_MANIFEST.sha256
  DISTRIBUTED_IA_RZF_ARCHITECTURE_TEST_REPORT.txt
  wrappers/distributed_ia_rzf
  evidence/distributed_ia_rzf_architecture
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c evidence/distributed_ia_rzf_architecture/EVIDENCE_MANIFEST.sha256

git commit -m "Replace WMMSE plan with distributed local IA-RZF architecture"
git push
COMMIT="$(git rev-parse HEAD)"

echo "WRAPPER 30 PACKAGE/PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "NEXT REVIEW FILES:"
echo "  evidence/distributed_ia_rzf_architecture/work/DISTRIBUTED_IA_RZF_ARCHITECTURE_DECISION.json"
echo "  evidence/distributed_ia_rzf_architecture/work/DISTRIBUTED_IA_RZF_PROTOTYPE_AUDIT.json"
echo "  evidence/distributed_ia_rzf_architecture/work/DISTRIBUTED_IA_RZF_VALIDATION.json"
echo "  evidence/distributed_ia_rzf_architecture/work/prototype_time_summary.csv"
echo "  docs/DISTRIBUTED_IA_RZF_ARCHITECTURE.md"
echo "  paper_ready/distributed_ia_rzf_system_model.tex"
