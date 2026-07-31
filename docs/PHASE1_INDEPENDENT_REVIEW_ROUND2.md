# Phase-1 candidate v3 independent review — round 2

## Verdict

`PASS_FOR_IMMUTABLE_JOB_PACKAGE_PREPARATION_NOT_EXECUTION`

Reviewed candidate:

- commit: `be9053dd18deaeef6ab87597e706ab45092ea8cf`;
- candidate ZIP SHA-256:
  `f7b47fd3a07e30987b7f0901df1706d6127774d32284e7d3b0da38185d810161`;
- review-prep ZIP SHA-256:
  `505f5a54e3ce42992ed21ed5636ae3cb611dbc89be9eb15321c043a63b2745da`.

Candidate v3 resolves the round-1 campaign-design defects:

1. one primary 64T64R, 65 dB null-cap, 3 dB uplift scenario;
2. explicit practical, diagnostic, safe-reference, and noncausal method classes;
3. a reactive-myopic comparator contract with the same sector fallback;
4. exact variable-pass-length and inactive-user PF semantics;
5. a paired seed-cluster statistical plan with five passes treated as fixed
   blocks;
6. a source/config snapshot and one-channel-generation-per-seed compute DAG;
7. five immutable pass records and working execution locks.

## Scope of this PASS

This PASS authorizes only construction of an immutable job-array package. It
does not authorize Nibi execution, does not certify the not-yet-implemented
reactive-myopic fallback, and does not convert deterministic array/CSI
engineering scenarios into calibrated uncertainty or regulatory compliance.

## Mandatory job-package requirements

- Parse `PHASE1_CAMPAIGN_CONTRACT_V3.json` as the sole canonical contract.
  Legacy v2 fields retained in `CAMPAIGN_METADATA.json` must be ignored.
- Implement and test the reactive-myopic comparator with the same
  sector-selective emergency fallback and no future coupling information.
- Use the final moving-average sum-log utility as the primary endpoint exactly
  as preregistered; report duration-weighted mean moving-PF utility as a
  mandatory secondary endpoint.
- Bind every source/config file by SHA-256 to candidate v3 or to an explicitly
  reviewed new job-package file.
- Generate each cellular channel seed once and reuse it over all five passes
  and every method.
- Keep submission scripts locked until the job package receives independent
  PASS and a separate authorization token.

## Nonblocking boundaries

The five passes use one archived TLE and are fixed geometry blocks, not an iid
sample of all orbital passes. The 100 ms fallback latency is declared but not
measured. Practical compatibility, calibration, compliance, and paper-result
claims remain prohibited.
