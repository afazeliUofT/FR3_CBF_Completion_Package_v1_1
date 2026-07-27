#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
printf '\n=== STEP 30: build centralized review folder and upload bundle ===\n'
PYTHONDONTWRITEBYTECODE=1 python3 scripts/24_5_package_e3_first_sector_review.py --config config/e3_first_sector_p452.yaml
REVIEW="$ROOT/results/e3_first_sector_p452_review"; UPLOAD="$REVIEW/review_upload"
echo; echo 'FILES REQUIRED FOR REVIEW:'; cat "$REVIEW/REVIEW_FILES.txt"; echo; echo 'UPLOAD FOLDER CONTENTS:'; find "$UPLOAD" -maxdepth 1 -type f -printf '  %f\n' | sort
if command -v explorer.exe >/dev/null 2>&1; then explorer.exe "$(wslpath -w "$REVIEW")" >/dev/null 2>&1 || true; explorer.exe "$(wslpath -w "$UPLOAD")" >/dev/null 2>&1 || true; explorer.exe "$(wslpath -w "$ROOT/data/real/e3_first_sector_p452")" >/dev/null 2>&1 || true; cmd.exe /C start "" "$(wslpath -w "$REVIEW/REVIEW_INDEX.html")" >/dev/null 2>&1 || true; fi
echo 'WRAPPER 30 PACKAGE/OPEN REVIEW: PASS'
