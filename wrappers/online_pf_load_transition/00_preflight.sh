#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/src:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

[[ "$(git branch --show-current)" == "e3-first-sector-p452" ]] || {
  echo "ERROR: wrong Git branch"
  exit 2
}
git merge-base --is-ancestor \
  83ce40b0f1edb285d529f866ee40d2d5d60ed8cf HEAD
ORIGIN="$(git remote get-url origin)"
[[ "$ORIGIN" == *"afazeliUofT/FR3_CBF_Completion_Package_v1_1"* ]]
git diff --cached --quiet || {
  echo "ERROR: pre-existing staged changes"
  git diff --cached --name-status
  exit 3
}

DATA="data/real/full_topology_export_18696267_validated_v4/output"
[[ -f "$DATA/FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json" ]]
[[ -f "$DATA/frequency_response.npy" ]]
[[ -f "src/fr3_cbf/constrained_pf_safety.py" ]]
[[ -f "src/fr3_cbf/robust_delayed_safety.py" ]]

mapfile -t TRACKED_COMPILED < <(
  git ls-files | grep -E '(^|/)(__pycache__/|.*\.py[co]$)' || true
)
UNEXPECTED=()
for path in "${TRACKED_COMPILED[@]}"; do
  case "$path" in
    src/fr3_cbf/__pycache__/robust_delayed_safety.cpython-313.pyc|\
    tests/__pycache__/test_robust_delayed_safety.cpython-313-pytest-9.0.2.pyc)
      ;;
    *) UNEXPECTED+=("$path") ;;
  esac
done
if [[ "${#UNEXPECTED[@]}" -gt 0 ]]; then
  echo "ERROR: unexpected tracked compiled artifacts:"
  printf '  %s\n' "${UNEXPECTED[@]}"
  exit 4
fi
echo "TRACKED COMPILED-ARTIFACT PREFLIGHT: ${#TRACKED_COMPILED[@]} known artifact(s) scheduled for removal"

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  -q -p no:cacheprovider \
  tests/test_online_pf_load_transition.py

echo "ONLINE PF LOAD-TRANSITION PREFLIGHT: PASS"
