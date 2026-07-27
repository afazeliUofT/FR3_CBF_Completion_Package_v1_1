#!/usr/bin/env bash
set -Eeuo pipefail
REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
mkdir -p logs/e3_human_review_allsite
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/e3_human_review_allsite/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 160 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/e3_human_review_allsite")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "E3 ONE-SECTOR REVIEW + ALL-19-SITE TERRAIN DROP-IN"
echo "================================================================="
echo "Repository: $REPO_ROOT"
echo "Log: $MASTER_LOG"

WRAPPERS=(
  00_preflight
  10_one_sector_review
  20_all_site_terrain
  30_package_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/e3_human_review_allsite/${name}.sh"
  log="logs/e3_human_review_allsite/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > "logs/e3_human_review_allsite/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
echo
echo "================================================================="
echo "E3 ONE-SECTOR REVIEW + ALL-SITE TERRAIN DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Branch URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/tree/e3-first-sector-p452"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Next gate: HUMAN_REVIEW_OF_ALL_19_SITE_TERRAIN_BEFORE_P452_SCALING"
echo "Review files:"
echo "  evidence/e3_first_sector_human_review/ONE_SECTOR_HUMAN_REVIEW_DECISION.json"
echo "  evidence/e3_first_sector_human_review/required_backoff_summary.csv"
echo "  evidence/e3_all_site_terrain_review/ALL_SITE_TERRAIN_REVIEW_AUDIT.json"
echo "  evidence/e3_all_site_terrain_review/terrain_review/terrain_summary.csv"
echo "  evidence/e3_all_site_terrain_review/terrain_profile_samples_review.csv"
echo "  evidence/e3_all_site_terrain_review/all_site_profile_qc_metrics.csv"
echo "  evidence/e3_all_site_terrain_review/terrain_review/all_19_site_profiles_review.pdf"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/e3_first_sector_human_review")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/e3_all_site_terrain_review")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/e3_all_site_terrain_review/terrain_review/all_19_site_profiles_review.pdf")" >/dev/null 2>&1 || true
fi
if command -v cmd.exe >/dev/null 2>&1; then
  cmd.exe /c start "" "https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT" >/dev/null 2>&1 || true
fi
