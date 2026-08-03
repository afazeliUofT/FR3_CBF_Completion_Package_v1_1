# Build validation

The release must pass:

- Python and Bash syntax;
- focused tests using the real R1 and holdout archives;
- exact-data five-pass assembly using real completed pass traces;
- repaired seed validator;
- real R1 timeout/MaxRSS audit;
- pass-independence source audit;
- success/partial return packaging;
- clean Git normal-push and stale-push simulations;
- ZIP CRC and internal manifests;
- no cache or compiled artifacts.

The real Rorqual pass-parallel calculation is intentionally not executed in the
build environment; it is the next gate.
