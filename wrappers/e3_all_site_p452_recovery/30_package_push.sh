#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

EVIDENCE="evidence/e3_all_site_p452_basic_loss"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE/work" "$EVIDENCE/review" "$EVIDENCE/logs"

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
  data/real/e3_all_site_p452/ALL_SITE_P452_INDEPENDENT_REVIEW.json \
  data/real/e3_all_site_p452/ALL_SITE_P452_INDEPENDENT_REVIEW.md \
  "$EVIDENCE/work/"

cp \
  results/e3_all_site_p452_review/all_site_loss_vs_distance.png \
  results/e3_all_site_p452_review/all_site_loss_by_site.png \
  results/e3_all_site_p452_review/all_site_p452_sensitivity_spans.png \
  "$EVIDENCE/review/"

cp \
  logs/e3_all_site_p452/00_preflight_and_manual_review.log \
  logs/e3_all_site_p452/10_freeze_prepare.log \
  logs/e3_all_site_p452/20_matlab.log \
  logs/e3_all_site_p452_recovery/00_preflight.log \
  logs/e3_all_site_p452_recovery/10_matlab_retry.log \
  logs/e3_all_site_p452_recovery/20_validate.log \
  "$EVIDENCE/logs/" 2>/dev/null || true

cat > "$EVIDENCE/README.md" <<'EOF'
# E3 19-site P.452 basic-loss audit

This evidence contains one validated P.452-18 sensitivity grid for each of the
19 unique modelled site-to-earth-station terrain paths.

It does not include the final 57-sector composite-beam gains, tracking
earth-station-gain expansion, aggregate network interference, dynamic
controller, paper result, or compliance determination.
EOF

# Normalize only tracked evidence copies; original generated files remain unchanged.
python3 - <<'PY'
from pathlib import Path

root = Path("evidence/e3_all_site_p452_basic_loss")
text_extensions = {
    ".log", ".csv", ".json", ".md", ".txt", ".html",
    ".sha256", ".yaml", ".yml", ".py", ".sh", ".m",
}
strip_trailing_extensions = {".log", ".txt", ".md"}

for path in sorted(root.rglob("*")):
    if not path.is_file() or path.suffix.lower() not in text_extensions:
        continue
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        continue
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if path.suffix.lower() in strip_trailing_extensions:
        text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_bytes(text.encode("utf-8"))

print("TRACKED EVIDENCE TEXT NORMALIZATION: PASS")
PY

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
  scripts/25_3_independent_review_e3_all_site_p452.py
  matlab/run_e3_all_site_p452.m
  tests/test_e3_all_site_p452_dropin.py
  tests/test_e3_all_site_p452_matlab_table_recovery.py
  RUN_E3_ALL_SITE_TERRAIN_FREEZE_AND_P452_DROPIN.sh
  RUN_E3_ALL_SITE_P452_MATLAB_RECOVERY_DROPIN.sh
  README_E3_ALL_SITE_TERRAIN_FREEZE_AND_P452.md
  README_E3_ALL_SITE_P452_MATLAB_RECOVERY.md
  E3_ALL_SITE_TERRAIN_FREEZE_P452_MANIFEST.sha256
  E3_ALL_SITE_TERRAIN_FREEZE_P452_TEST_REPORT.txt
  E3_ALL_SITE_P452_MATLAB_RECOVERY_MANIFEST.sha256
  E3_ALL_SITE_P452_MATLAB_RECOVERY_TEST_REPORT.txt
  wrappers/e3_all_site_p452
  wrappers/e3_all_site_p452_recovery
  evidence/e3_all_site_p452_basic_loss
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c "$EVIDENCE/EVIDENCE_MANIFEST.sha256"

git commit -m "Repair MATLAB table construction and add 19-site P.452 audit"
git push
COMMIT="$(git rev-parse HEAD)"

echo "WRAPPER 30 PACKAGE/PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "NEXT REVIEW FILES:"
echo "  evidence/e3_all_site_p452_basic_loss/work/ALL_SITE_TERRAIN_DECISION.json"
echo "  evidence/e3_all_site_p452_basic_loss/work/ALL_SITE_P452_VALIDATION.json"
echo "  evidence/e3_all_site_p452_basic_loss/work/ALL_SITE_P452_INDEPENDENT_REVIEW.json"
echo "  evidence/e3_all_site_p452_basic_loss/work/all_site_loss_summary.csv"
echo "  evidence/e3_all_site_p452_basic_loss/work/p452_all_site_basic_loss.csv"
echo "  evidence/e3_all_site_p452_basic_loss/review/"
