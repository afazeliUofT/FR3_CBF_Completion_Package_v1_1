# Build and Release Validation

The release was checked with:

- package and source manifests;
- Python and Bash syntax checks;
- five focused regression tests;
- exact second-round-verdict binding;
- exact SA.509 count/fraction reconstruction;
- clean IEEEtran compilation to 13 pages;
- undefined-citation/reference and overfull-box scans;
- PDF preflight and 13-page visual rendering;
- render comparison against candidate v3, showing changes only on pages 3-4 where the approved wording/table polish occurs;
- nested evidence ZIP CRC and basename-only sidecar checks;
- normal non-force Git push simulation;
- stale non-force push rejection simulation;
- compiled/cache-artifact scan.

No cluster or simulation was used to build this package.
