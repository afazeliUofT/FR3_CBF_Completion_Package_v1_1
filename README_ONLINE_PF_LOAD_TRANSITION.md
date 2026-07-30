# Online moving-average PF with load transitions

Run only:

```bash
bash RUN_ONLINE_PF_LOAD_TRANSITION_DROPIN.sh
```

This local-only milestone:

- recomputes local RZF and protected-mode leakage for deterministic user
  arrivals/departures using the validated full channel;
- updates 100-second exponential moving-average PF weights online;
- preserves the constrained-PF active-user floors;
- compares online predictive, online myopic, static robust, and frozen-table
  predictive controllers;
- tests 1 dB and 3 dB upper-coupling smoke margins and two dropped commands;
- repairs the saturation wording of the finite-pass safety theorem by checking
  the actual clipped candidate `F(q)=min(q+rho,Q)`;
- removes accidentally tracked compiled Python artifacts;
- freezes, but does not submit, the multi-seed/multi-pass campaign design.

This remains one channel/topology seed, one protected pass, and a deterministic
load stress test. No cluster job is submitted.

Numerical reproduction policy: full-load local RZF is checked with a strict
per-user absolute error and a separate aggregate relative error. A single
absolute threshold is not reused for both one user and a 228-user sum.
