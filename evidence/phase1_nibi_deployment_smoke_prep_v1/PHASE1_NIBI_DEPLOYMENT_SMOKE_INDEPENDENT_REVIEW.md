# Independent review of the noncampaign Nibi deployment-smoke package

## Verdict

`PASS_FOR_SINGLE_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_EXECUTION_ONLY`

This review permits exactly one excluded deployment smoke using seed `43999`,
which lies outside the confirmatory seed range `44000--44029`.

The smoke is bound to:

- immutable job-package commit
  `20d65eeb0fcc53f649a4f3f716fa2780406b4810`;
- immutable package ID
  `bd18734787de7396b9de4bf8c0b9ba4d191c6346a7cb83e969499622067a8129`;
- job-package ZIP SHA-256
  `a81f1808f75119e64a0f7f631a54230f3e722efa8d17dcf032ee1296f2bb76be`;
- candidate-v3 SHA-256
  `f7b47fd3a07e30987b7f0901df1706d6127774d32284e7d3b0da38185d810161`;
- independent job-package review commit
  `74d7ae7354903b9fcade76515b0765286309f7ca`.

## Required execution boundaries

1. The token scope is `NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY`.
2. The token seed is exactly `43999`; campaign seeds and merge are forbidden.
3. Every result is marked
   `EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS`.
4. The exact resolved Nibi Python environment is frozen before submission and
   its SHA-256 is included in a seven-day, single-job smoke token.
5. One H100 job is submitted without a Slurm array.
6. The return includes package/source hashes, environment lock, GPU/driver
   record, token, Slurm accounting, stdout/stderr, channel fingerprints,
   all-eight-method outputs, and failure diagnostics when needed.
7. Full phase-1 execution remains unauthorized.

## Claim boundary

A successful deployment smoke establishes only that the immutable package can
execute end to end on Nibi under the recorded environment. It is not a
confirmatory seed, paper result, calibration result, or compliance result.
