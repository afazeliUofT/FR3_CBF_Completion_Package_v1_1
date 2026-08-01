# Build validation

Before release this package must pass:

- Python AST syntax checks;
- Bash `-n` checks;
- focused pytest regressions;
- exact frozen-return independent review;
- a CPU self-replay of the H100 comparison auditor;
- success and failure return-packaging simulations;
- package/source manifest checks;
- ZIP CRC and extraction checks;
- clean Git source/evidence push simulation with stale-push rejection;
- forbidden compiled/cache artifact scan.

The real H100/Slurm job is intentionally not run in the build environment.
