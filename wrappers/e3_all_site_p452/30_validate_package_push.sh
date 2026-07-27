#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

python3 scripts/20_validate_p452_export.py \
  data/real/e3_all_site_p452/p452_all_site_coupling_export.csv

PYTHONDONTWRITEBYTECODE=1 python3 scripts/25_2_validate_e3_all_site_p452.py \
  --config config/e3_all_site_p452.yaml

EVIDENCE="evidence/e3_all_site_p452_basic_loss"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE/work" "$EVIDENCE/review"

cp \
  data/real/e3_all_site_p452/ALL_SITE_TERRAIN_DECISION.json \
  data/real/e3_all_site_p452/ALL_SITE_TERRAIN_DECISION.md \
  data/real/e3_all_site_p452/p452_all_site_profiles.csv \
  data/real/e3_all_site_p452/p452_all_site_site_parameters.csv \
  data/real/e3_all_site_p452/p452_all_site_parameters.json \
  data/real/e3_all_site_p452/ALL_SITE_P452_PREP_AUDIT.json \
  data/real/e3_all_site_p452/p452_all_site_basic_loss.csv \
  data/real/e3_all_site_p452/p452_all_site_coupling_export.csv \
  data/real/e3_all_site_p452/P452_ALL_SITE_MATLAB_AUDIT.json \
  data/real/e3_all_site_p452/all_site_loss_summary.csv \
  data/real/e3_all_site_p452/ALL_SITE_P452_VALIDATION.json \
  data/real/e3_all_site_p452/ALL_SITE_P452_VALIDATION.md \
  "$EVIDENCE/work/"

cp \
  results/e3_all_site_p452_review/all_site_loss_vs_distance.png \
  results/e3_all_site_p452_review/all_site_loss_by_site.png \
  results/e3_all_site_p452_review/all_site_p452_sensitivity_spans.png \
  "$EVIDENCE/review/"

cat > "$EVIDENCE/README.md" <<'EOF'
# E3 19-site P.452 basic-loss audit

This evidence contains one validated P.452-18 basic-loss sensitivity grid for
each of the 19 unique modelled site-to-earth-station paths.

It does not contain the final 57-sector composite-beam gain, earth-station
tracking-gain expansion, aggregate network interference, controller result,
paper result, or compliance determination.
EOF

python3 - <<'PY'
from hashlib import sha256
from pathlib import Path
root = Path("evidence/e3_all_site_p452_basic_loss")
manifest = root / "EVIDENCE_MANIFEST.sha256"
lines = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path != manifest:
        lines.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.as_posix()}")
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("EVIDENCE MANIFEST:", manifest, "entries=", len(lines))
PY

STAGE=(
  config/e3_all_site_p452.yaml
  scripts/24_9_freeze_e3_all_site_terrain.py
  scripts/25_0_prepare_e3_all_site_p452.py
  scripts/25_1_preflight_e3_all_site_p452.py
  scripts/25_2_validate_e3_all_site_p452.py
  matlab/run_e3_all_site_p452.m
  tests/test_e3_all_site_p452_dropin.py
  RUN_E3_ALL_SITE_TERRAIN_FREEZE_AND_P452_DROPIN.sh
  README_E3_ALL_SITE_TERRAIN_FREEZE_AND_P452.md
  E3_ALL_SITE_TERRAIN_FREEZE_P452_MANIFEST.sha256
  E3_ALL_SITE_TERRAIN_FREEZE_P452_TEST_REPORT.txt
  wrappers/e3_all_site_p452
  evidence/e3_all_site_p452_basic_loss
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c evidence/e3_all_site_p452_basic_loss/EVIDENCE_MANIFEST.sha256

git commit -m "Freeze all-site terrain and add 19-site P.452 basic-loss audit"
git push
COMMIT="$(git rev-parse HEAD)"

echo "WRAPPER 30 VALIDATE/PACKAGE/PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "NEXT REVIEW FILES:"
echo "  evidence/e3_all_site_p452_basic_loss/work/ALL_SITE_TERRAIN_DECISION.json"
echo "  evidence/e3_all_site_p452_basic_loss/work/ALL_SITE_P452_VALIDATION.json"
echo "  evidence/e3_all_site_p452_basic_loss/work/all_site_loss_summary.csv"
echo "  evidence/e3_all_site_p452_basic_loss/work/p452_all_site_basic_loss.csv"
echo "  evidence/e3_all_site_p452_basic_loss/review/all_site_loss_vs_distance.png"
echo "  evidence/e3_all_site_p452_basic_loss/review/all_site_loss_by_site.png"
echo "  evidence/e3_all_site_p452_basic_loss/review/all_site_p452_sensitivity_spans.png"
