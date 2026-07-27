#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

rm -rf evidence/e3_first_sector_human_review evidence/e3_all_site_terrain_review
mkdir -p evidence/e3_first_sector_human_review evidence/e3_all_site_terrain_review

cp -a data/real/e3_first_sector_human_review/. \
  evidence/e3_first_sector_human_review/

cp \
  data/real/e3_all_site_terrain_review/site_links_input.csv \
  data/real/e3_all_site_terrain_review/site_links_with_terrain.csv \
  data/real/e3_all_site_terrain_review/ALL_SITE_TERRAIN_REVIEW_AUDIT.json \
  data/real/e3_all_site_terrain_review/ALL_SITE_TERRAIN_REVIEW_AUDIT.md \
  data/real/e3_all_site_terrain_review/terrain_profile_samples_review.csv \
  data/real/e3_all_site_terrain_review/all_site_profile_qc_metrics.csv \
  evidence/e3_all_site_terrain_review/

mkdir -p evidence/e3_all_site_terrain_review/terrain_review
cp \
  data/real/e3_all_site_terrain_review/terrain_review/terrain_summary.csv \
  data/real/e3_all_site_terrain_review/terrain_review/terrain_profile_samples.csv.gz \
  data/real/e3_all_site_terrain_review/terrain_review/TERRAIN_AUDIT.json \
  data/real/e3_all_site_terrain_review/terrain_review/all_19_site_profiles_review.pdf \
  evidence/e3_all_site_terrain_review/terrain_review/

cat > evidence/e3_first_sector_human_review/README.md <<'EOF'
# Independent one-sector review

This evidence closes the Site-18 one-sector P.452/gain-accounting stage as an
internally correct accounting audit under declared assumptions. It is not a
paper result or compliance determination.
EOF

cat > evidence/e3_all_site_terrain_review/README.md <<'EOF'
# E3 all-site terrain review

This directory contains one MRDEM profile for each of the 19 unique modelled
BS sites to the reference earth station. The three sectors at a site share the
same terrestrial propagation path. Human review is required before all-site
P.452 execution.
EOF

python3 - <<'PY'
from hashlib import sha256
from pathlib import Path
for root_name in [
    "evidence/e3_first_sector_human_review",
    "evidence/e3_all_site_terrain_review",
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
  config/e3_all_site_terrain_review.yaml
  scripts/24_6_independent_review_e3_first_sector.py
  scripts/24_7_prepare_e3_all_site_links.py
  scripts/24_8_validate_e3_all_site_terrain.py
  tests/test_e3_human_review_allsite_dropin.py
  RUN_E3_ONE_SECTOR_REVIEW_AND_ALL_SITE_TERRAIN_DROPIN.sh
  README_E3_ONE_SECTOR_REVIEW_ALL_SITE_TERRAIN.md
  E3_ONE_SECTOR_REVIEW_ALL_SITE_TERRAIN_MANIFEST.sha256
  E3_ONE_SECTOR_REVIEW_ALL_SITE_TERRAIN_TEST_REPORT.txt
  wrappers/e3_human_review_allsite
  evidence/e3_first_sector_human_review
  evidence/e3_all_site_terrain_review
)
git add -- "${STAGE[@]}"
git diff --cached --check
sha256sum -c evidence/e3_first_sector_human_review/EVIDENCE_MANIFEST.sha256
sha256sum -c evidence/e3_all_site_terrain_review/EVIDENCE_MANIFEST.sha256

git commit -m "Close one-sector audit and prepare all-site E3 terrain review"
git push
COMMIT="$(git rev-parse HEAD)"

echo "WRAPPER 30 PACKAGE/PUSH: PASS"
echo "Commit: $COMMIT"
echo "Branch: $(git branch --show-current)"
echo "GitHub: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "NEXT REVIEW FILES ON GITHUB:"
echo "  evidence/e3_first_sector_human_review/ONE_SECTOR_HUMAN_REVIEW_DECISION.json"
echo "  evidence/e3_first_sector_human_review/required_backoff_summary.csv"
echo "  evidence/e3_all_site_terrain_review/ALL_SITE_TERRAIN_REVIEW_AUDIT.json"
echo "  evidence/e3_all_site_terrain_review/terrain_review/terrain_summary.csv"
echo "  evidence/e3_all_site_terrain_review/terrain_profile_samples_review.csv"
echo "  evidence/e3_all_site_terrain_review/all_site_profile_qc_metrics.csv"
echo "  evidence/e3_all_site_terrain_review/terrain_review/all_19_site_profiles_review.pdf"
