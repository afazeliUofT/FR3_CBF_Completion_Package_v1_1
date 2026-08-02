# Build validation

Required release gates:

- Python and Bash syntax;
- complete focused test suite;
- exact binding to the failed return and its manifest;
- exact comparator reproduction in the preliminary salvage audit;
- NumPy JSON serialization regression;
- scientific-module byte-identity audit;
- success/partial/failure return packaging;
- non-force Git workflow simulation;
- ZIP CRC and internal manifests;
- no cache or compiled artifacts.

The real corrected Rorqual rerun is intentionally not executed in the build
environment.
