# Build validation

Release validation includes:

- Python in-memory syntax: PASS, 8 files;
- Bash syntax: PASS, 1 wrapper;
- focused tests: PASS, 6 tests;
- exact smoke reclassification: PASS;
- corrected structural and scientific validators: PASS;
- exact channel, comparator, candidate-action, trace, and endpoint checks: PASS;
- deterministic Rorqual R2 package build: PASS;
- corrected Rorqual package ID:
  `8473d5504e69347a69a536c43dcae35bec9519a90bc55de3a0712f9e0fb97889`;
- deterministic job-package SHA-256:
  `c106fa6441b15873d0d2d9b29d636434625edcd58f4033a4700589cb91e19e82`;
- independent package review: PASS;
- full-wrapper normal Git push simulation: PASS;
- stale non-force push refusal: PASS;
- expected failure-return packaging: PASS;
- terminal-continuation simulation: PASS;
- policy/scope and compiled/cache-artifact scans: PASS;
- ZIP CRC and internal manifests: PASS after final archive construction.
