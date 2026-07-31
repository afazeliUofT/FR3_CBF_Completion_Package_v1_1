# Five protected-pass records and phase-1 candidate v2

Run only:

```bash
bash RUN_PROTECTED_PASS_RECORDS_PHASE1_DROPIN.sh
```

The local-only stage normalizes the current validated pass into slot 0,
generates four predeclared additional visible passes with the exact archived
TLE and Skyfield, derives corrected long-/short-term coupling arrays for both
SA.509 patterns, creates immutable pass records, and builds a complete
five-pass phase-1 campaign review candidate.

The candidate remains non-executable. No cluster job is submitted and no
execution authorization is granted.
