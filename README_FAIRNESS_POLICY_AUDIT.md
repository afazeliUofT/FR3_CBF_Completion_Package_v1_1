# FR3 fairness policy audit

Do not run the earlier local-controller milestone v1.

Run only:

```bash
bash RUN_FAIRNESS_POLICY_AUDIT_DROPIN.sh
```

This local-only audit verifies the validated full-topology data, separates
coverage-limited users from controller-induced outages, evaluates PF utility,
geometric mean, Jain index, absolute outage counts, fifth percentile, minimum,
total-band/protected-band, and indoor/outdoor groups, and freezes a constrained
proportional-fairness policy for the next controller implementation.

The primary one-seed diagnostic floor is:

```text
eligible if nominal total-band SE >= 0.1 bit/s/Hz
required safe rate >= max(0.1 bit/s/Hz, 0.9*nominal rate)
```

The 0.05/0.1/0.25 serviceability and 0.8/0.9/0.95 relative-floor grids are
retained as sensitivity analyses. No indoor-specific optimization weight is
used until a multi-seed O2I audit supports one.
