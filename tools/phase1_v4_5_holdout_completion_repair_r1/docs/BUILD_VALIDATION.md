# Build validation

Completed in the build environment:

- exact SHA/CRC/manifest audit of the incomplete holdout return;
- exact revalidation of all 29 complete seed results with the repaired payload equation;
- deterministic reproduction of the 7,776-mode library under the 8,192 implementation guard;
- Python and Bash syntax checks;
- focused tests, including completed-audit and return-packaging regressions;
- synthetic 30-seed end-to-end merge and preregistered bootstrap using a duplicated seed only as a pipeline dry run;
- normal source/evidence Git push simulation, stale non-force push rejection, and rebase recovery;
- success and local/remote failure-return path checks;
- terminal-continuation policy check;
- ZIP CRC, source manifest, package manifest, and forbidden-artifact scans.

Not executable in the build environment:

- the real seed-44052 preserved-channel computation on Rorqual;
- the resulting real 30-seed merge. These are the sole next execution gate.
