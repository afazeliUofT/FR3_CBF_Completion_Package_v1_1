#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

SUPPORTED="$(
  python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(
    Path(
        "data/real/e3_57_sector_reference_screen/"
        "P452_MECHANISM_FACTORISATION_DECISION.json"
    ).read_text(encoding="utf-8")
)
print("true" if data["external_direct_gain_factorization_supported"] else "false")
PY
)"

if [[ "$SUPPORTED" == "true" ]]; then
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/26_0_build_e3_57_sector_reference_screen.py \
    --config config/e3_57_sector_reference_screen.yaml

  PYTHONDONTWRITEBYTECODE=1 python3 scripts/26_1_validate_e3_57_sector_reference_screen.py \
    --config config/e3_57_sector_reference_screen.yaml

  echo
  cat data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_DECISION.md
  echo
  cat data/real/e3_57_sector_reference_screen/E3_57_SECTOR_REFERENCE_SCREEN_VALIDATION.md
  echo "WRAPPER 20 BUILD/VALIDATE: PASS"
else
  python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json

root = Path("data/real/e3_57_sector_reference_screen")
decision = json.loads(
    (root / "P452_MECHANISM_FACTORISATION_DECISION.json").read_text(
        encoding="utf-8"
    )
)
record = {
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "status": "SCIENTIFIC_STOP_MECHANISM_SPECIFIC_GAIN_MODEL_REQUIRED",
    "claim_boundary": "57_SECTOR_REFERENCE_FEASIBILITY_SCREEN_NOT_RUN",
    "reason": decision,
    "next_gate": "MECHANISM_SPECIFIC_GAIN_MODEL_REQUIRED",
}
(root / "E3_57_SECTOR_REFERENCE_SCREEN_SKIPPED.json").write_text(
    json.dumps(record, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
(root / "E3_57_SECTOR_REFERENCE_SCREEN_SKIPPED.md").write_text(
    "# E3 57-sector reference screen: scientific stop\n\n"
    "The P.452 mechanism-isolation audit found a material troposcatter "
    "contribution. The external direct-gain factorization was therefore not "
    "used, and the 57-sector screen was intentionally skipped.\n\n"
    "Next gate: `MECHANISM_SPECIFIC_GAIN_MODEL_REQUIRED`\n",
    encoding="utf-8",
)
print("E3 57-SECTOR REFERENCE SCREEN: SCIENTIFIC STOP RECORDED")
print(json.dumps(record, indent=2))
PY
  echo "WRAPPER 20 BUILD/VALIDATE: SCIENTIFIC STOP RECORDED"
fi
