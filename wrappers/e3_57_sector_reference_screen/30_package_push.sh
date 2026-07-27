#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

EVIDENCE="evidence/e3_57_sector_reference_screen"
rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE/work" "$EVIDENCE/review" "$EVIDENCE/logs"

CORE_FILES=(
  data/real/e3_57_sector_reference_screen/ALL_SITE_P452_HUMAN_REVIEW_DECISION.json
  data/real/e3_57_sector_reference_screen/ALL_SITE_P452_HUMAN_REVIEW_DECISION.md
  data/real/e3_57_sector_reference_screen/site_geometry_loss_classification.csv
  data/real/e3_57_sector_reference_screen/p452_troposcatter_suppressed_probe.csv
  data/real/e3_57_sector_reference_screen/P452_MECHANISM_PROBE_MATLAB_AUDIT.json
  data/real/e3_57_sector_reference_screen/p452_mechanism_probe_site_summary.csv
  data/real/e3_57_sector_reference_screen/P452_MECHANISM_FACTORISATION_DECISION.json
  data/real/e3_57_sector_reference_screen/P452_MECHANISM_FACTORISATION_DECISION.md
)
cp "${CORE_FILES[@]}" "$EVIDENCE/work/"

if [[ -f data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_DECISION.json ]]; then
  SCREEN_FILES=(
    data/real/e3_57_sector_reference_screen/sector_static_reference_accounting.csv
    data/real/e3_57_sector_reference_screen/earth_station_site_gain_timeseries.csv.gz
    data/real/e3_57_sector_reference_screen/network_aggregate_reference_timeseries.csv.gz
    data/real/e3_57_sector_reference_screen/network_reference_scenario_summary.csv
    data/real/e3_57_sector_reference_screen/peak_top_sector_contributions.csv
    data/real/e3_57_sector_reference_screen/dominant_sector_summary.csv
    data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_DECISION.json
    data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_DECISION.md
    data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_VALIDATION.json
    data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_VALIDATION.md
  )
  cp "${SCREEN_FILES[@]}" "$EVIDENCE/work/"
  cp \
    results/e3_57_sector_reference_screen/aggregate_p20_H_multiple.png \
    results/e3_57_sector_reference_screen/required_short_backoff_p20_H_multiple.png \
    results/e3_57_sector_reference_screen/global_peak_top_sector_contributions.png \
    "$EVIDENCE/review/"
  NEXT_GATE="HUMAN_REVIEW_OF_57_SECTOR_REFERENCE_FEASIBILITY_BEFORE_COMPOSITE_BEAM_IMPORT"
  COMMIT_MESSAGE="Add 57-sector E3 reference feasibility and mechanism audit"
else
  cp \
    data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_SKIPPED.json \
    data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_SKIPPED.md \
    "$EVIDENCE/work/"
  NEXT_GATE="MECHANISM_SPECIFIC_GAIN_MODEL_REQUIRED"
  COMMIT_MESSAGE="Add E3 P.452 mechanism audit and scientific-stop evidence"
fi

cp \
  logs/e3_57_sector_reference_screen/00_preflight_review.log \
  logs/e3_57_sector_reference_screen/10_mechanism_probe.log \
  logs/e3_57_sector_reference_screen/20_build_validate.log \
  "$EVIDENCE/logs/"

cat > "$EVIDENCE/README.md" <<EOF
# E3 P.452 mechanism audit and conditional 57-sector screen

This evidence closes the human review of the 19-site P.452 basic-loss audit
and preserves the numerical troposcatter-isolation result.

When the mechanism threshold passes, it also includes the 57-sector reference
aggregate feasibility screen. When it does not pass, the screen is
intentionally skipped and a scientific-stop record is preserved.

Next gate: \`$NEXT_GATE\`
EOF

python3 - <<'PY'
from hashlib import sha256
from pathlib import Path
root = Path("evidence/e3_57_sector_reference_screen")
manifest = root / "EVIDENCE_MANIFEST.sha256"
lines = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path != manifest:
        lines.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.as_posix()}")
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("EVIDENCE MANIFEST:", manifest, "entries=", len(lines))
PY

STAGE=(
  config/e3_57_sector_reference_screen.yaml
  scripts/25_4_human_review_e3_all_site_p452.py
  scripts/25_5_validate_e3_p452_mechanism_probe.py
  scripts/26_0_build_e3_57_sector_reference_screen.py
  scripts/26_1_validate_e3_57_sector_reference_screen.py
  matlab/run_e3_all_site_p452_mechanism_probe.m
  tests/test_e3_57_sector_reference_screen.py
  RUN_E3_57_SECTOR_REFERENCE_SCREEN_DROPIN.sh
  README_E3_57_SECTOR_REFERENCE_SCREEN.md
  E3_57_SECTOR_REFERENCE_SCREEN_MANIFEST.sha256
  E3_57_SECTOR_REFERENCE_SCREEN_TEST_REPORT.txt
  wrappers/e3_57_sector_reference_screen
  evidence/e3_57_sector_reference_screen
)

git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c evidence/e3_57_sector_reference_screen/EVIDENCE_MANIFEST.sha256

git commit -m "$COMMIT_MESSAGE"
git push
COMMIT="$(git rev-parse HEAD)"

echo "WRAPPER 30 PACKAGE/PUSH: PASS"
echo "Commit: $COMMIT"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Next gate: $NEXT_GATE"
echo "REVIEW ROOT: evidence/e3_57_sector_reference_screen/"
