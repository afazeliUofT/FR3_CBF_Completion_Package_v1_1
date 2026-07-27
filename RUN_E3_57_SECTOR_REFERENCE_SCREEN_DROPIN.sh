#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${FR3_REPO_ROOT:-$HOME/FR3_CBF_Completion_Package_v1_1/FR3_CBF_Completion_Package_v1_1}"
cd "$REPO_ROOT"
mkdir -p logs/e3_57_sector_reference_screen
STAMP="$(date -u +%Y%m%d_%H%M%S)"
MASTER_LOG="logs/e3_57_sector_reference_screen/master_${STAMP}.log"
exec > >(tee "$MASTER_LOG") 2>&1

trap 'code=$?; echo; echo "DROP-IN FAIL: exit=$code command=$BASH_COMMAND"; tail -n 200 "$MASTER_LOG" || true; command -v explorer.exe >/dev/null && explorer.exe "$(wslpath -w "$REPO_ROOT/logs/e3_57_sector_reference_screen")" >/dev/null 2>&1 || true; exit $code' ERR

echo "================================================================="
echo "E3 19-SITE REVIEW + MECHANISM AUDIT + 57-SECTOR REFERENCE SCREEN"
echo "================================================================="
echo "Repository: $REPO_ROOT"
echo "Log: $MASTER_LOG"

WRAPPERS=(
  00_preflight_review
  10_mechanism_probe
  20_build_validate
  30_package_push
)

for name in "${WRAPPERS[@]}"; do
  path="wrappers/e3_57_sector_reference_screen/${name}.sh"
  log="logs/e3_57_sector_reference_screen/${name}.log"
  echo
  echo "=== RUNNING $name ==="
  set +e
  set -o pipefail
  bash "$path" 2>&1 | tee "$log"
  code=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  printf '%s\n' "$code" > "logs/e3_57_sector_reference_screen/${name}.exitcode"
  echo "WRAPPER EXITCODE: $name=$code"
  [[ "$code" -eq 0 ]] || exit "$code"
done

COMMIT="$(git rev-parse HEAD)"
echo
echo "================================================================="
echo "E3 57-SECTOR REFERENCE SCREEN DROP-IN: PASS"
echo "Commit: $COMMIT"
echo "Commit URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT"
echo "Branch URL: https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/tree/e3-first-sector-p452"
NEXT_GATE="$(
  python3 - <<'PY'
import json
from pathlib import Path
root = Path("data/real/e3_57_sector_reference_screen")
screen = root / "E3_57_SECTOR_REFERENCE_SCREEN_DECISION.json"
mechanism = root / "P452_MECHANISM_FACTORISATION_DECISION.json"
if screen.is_file():
    print(json.loads(screen.read_text(encoding="utf-8"))["next_gate"])
else:
    print(json.loads(mechanism.read_text(encoding="utf-8"))["next_gate"])
PY
)"
echo "Next gate: $NEXT_GATE"
echo "Review files:"
echo "  evidence/e3_57_sector_reference_screen/work/ALL_SITE_P452_HUMAN_REVIEW_DECISION.json"
echo "  evidence/e3_57_sector_reference_screen/work/P452_MECHANISM_FACTORISATION_DECISION.json"
echo "  evidence/e3_57_sector_reference_screen/work/E3_57_SECTOR_REFERENCE_SCREEN_DECISION.json"
echo "  evidence/e3_57_sector_reference_screen/work/network_reference_scenario_summary.csv"
echo "  evidence/e3_57_sector_reference_screen/review/"
echo "================================================================="

if command -v explorer.exe >/dev/null 2>&1; then
  explorer.exe "$(wslpath -w "$REPO_ROOT/evidence/e3_57_sector_reference_screen")" >/dev/null 2>&1 || true
  explorer.exe "$(wslpath -w "$REPO_ROOT/logs/e3_57_sector_reference_screen")" >/dev/null 2>&1 || true
fi
if command -v cmd.exe >/dev/null 2>&1; then
  cmd.exe /c start "" "https://github.com/afazeliUofT/FR3_CBF_Completion_Package_v1_1/commit/$COMMIT" >/dev/null 2>&1 || true
fi
