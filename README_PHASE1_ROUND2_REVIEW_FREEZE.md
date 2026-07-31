# Phase-1 candidate v3 round-2 review freeze

Run only:

```bash
bash RUN_PHASE1_ROUND2_REVIEW_FREEZE_DROPIN.sh
```

The local-only stage verifies candidate-v3 immutability and execution locks,
records the round-2 verdict
`PASS_FOR_IMMUTABLE_JOB_PACKAGE_PREPARATION_NOT_EXECUTION`, updates project
status, builds a compact review evidence bundle, commits, and pushes.

It does not generate channels, build the Nibi job package, submit Slurm jobs,
or authorize execution.
