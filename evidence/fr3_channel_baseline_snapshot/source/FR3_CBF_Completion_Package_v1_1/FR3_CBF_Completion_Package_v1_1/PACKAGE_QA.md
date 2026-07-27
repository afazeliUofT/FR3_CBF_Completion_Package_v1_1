# Package QA record

Package version: 1.1.0

Checks performed before distribution:

- YAML parsed and status values validated.
- User-supplied P.530 archive hash matched `3c0081a11950070ca4879ba91b8b655f4b5749bc5aad2f95bbf0928452836113`.
- Python source and scripts compiled without syntax errors.
- Unit tests passed, including P.530 transition continuity, grid interpolation, safety budgets, conformal calibration, bundle validation, PSD factorization, and layered budget allocation.
- Demo S1, E1, E2, E3, and calibration workflows executed successfully.
- Submission-readiness checker correctly returned `False` because real evidence and open items remain.
- All three PDFs were rendered to page images and visually checked for clipping, overlap, missing glyphs, and broken equations.

Important: passing package QA proves that the distributed software paths run. It does not turn demo data into paper evidence and does not verify an external P.452 implementation, real TAFL pairing, operator parameters, or physical uncertainty coverage.

The optional CVXPY beam-space solve was not executed in the build container because CVXPY was not installed. Its input validation, PSD square-root identity, and Python syntax were tested. Run `make beam` after installing `requirements-full.txt` and archive the solver/version record before relying on it.
