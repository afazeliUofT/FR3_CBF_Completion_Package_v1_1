
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
for f in IEEEtran.cls tikz.sty algorithm.sty algorithmic.sty balance.sty; do
  if ! kpsewhich "$f" >/dev/null 2>&1; then
    echo "MISSING_LATEX_COMPONENT=$f" >&2
    echo "On Ubuntu/WSL install texlive-publishers texlive-pictures texlive-science texlive-latex-extra." >&2
    exit 2
  fi
done
latexmk -C FR3_TWC_v4_5_independent_review_candidate_v2.tex >/dev/null 2>&1 || true
latexmk -pdf -interaction=nonstopmode -halt-on-error FR3_TWC_v4_5_independent_review_candidate_v2.tex
pdfinfo FR3_TWC_v4_5_independent_review_candidate_v2.pdf | grep '^Pages:'
