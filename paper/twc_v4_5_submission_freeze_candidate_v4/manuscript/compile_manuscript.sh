#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
MAIN="FR3_TWC_v4_5_submission_freeze_candidate_v4.tex"
PDF="${MAIN%.tex}.pdf"
for f in IEEEtran.cls tikz.sty algorithm.sty algorithmic.sty balance.sty; do
  if ! kpsewhich "$f" >/dev/null 2>&1; then
    echo "MISSING_LATEX_COMPONENT=$f" >&2
    echo "On Ubuntu/WSL install texlive-publishers texlive-pictures texlive-science texlive-latex-extra." >&2
    exit 2
  fi
done
latexmk -C "$MAIN" >/dev/null 2>&1 || true
latexmk -pdf -interaction=nonstopmode -halt-on-error "$MAIN"
PAGES="$(pdfinfo "$PDF" | awk '/^Pages:/ {print $2}')"
[[ "$PAGES" == "13" ]] || {
  echo "UNEXPECTED_PDF_PAGE_COUNT=$PAGES" >&2
  exit 3
}
echo "LATEX_COMPILATION=PASS"
echo "MANUSCRIPT_PDF_PAGE_COUNT=$PAGES"
echo "MANUSCRIPT_PDF=$PDF"
