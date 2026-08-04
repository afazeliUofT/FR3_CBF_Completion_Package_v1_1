
# LaTeX dependencies

The included PDF is precompiled and is the review-authoritative rendering.
To rebuild the source on Ubuntu/WSL, install:

```bash
sudo apt-get update
sudo apt-get install -y latexmk texlive-latex-base texlive-latex-recommended   texlive-latex-extra texlive-fonts-recommended texlive-publishers   texlive-pictures texlive-science poppler-utils
```

The source uses IEEEtran, TikZ, `algorithm`, and `algorithmic`. The last user-side
final-edit wrapper failed at `latexmk`, but its failure bundle did not retain the
detailed LaTeX transcript, so the exact missing `.sty` file is not established.
The build-environment compile succeeded and the included PDF passed preflight.
