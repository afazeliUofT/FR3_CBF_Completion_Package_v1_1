# Phase-1 immutable job-package independent review

Run only:

```bash
bash RUN_PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_DROPIN.sh
```

This local-only stage verifies the immutable phase-1 job package and records an
independent verdict permitting only preparation of a noncampaign Nibi
deployment smoke.

It does not connect to Nibi, issue an authorization token, submit a Slurm job,
run the 30-seed campaign, or merge campaign results.
