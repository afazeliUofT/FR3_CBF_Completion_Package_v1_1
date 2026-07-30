# Robust delayed-safety and baseline milestone

Run only:

```bash
bash RUN_ROBUST_DELAYED_SAFETY_BASELINES_DROPIN.sh
```

This local-only milestone:

- formalizes the finite-pass delayed reachability safety certificate;
- machine-checks recursive feasibility and the explicit ramp-to-safe fallback;
- tests 0, 1, and 3 dB deterministic coupling upper bounds;
- tests one additional stale-message interval;
- tests two dropped coordinator commands;
- adds virtual-queue/Lyapunov-style long-term baselines;
- retains constrained proportional fairness and eligible-user floors;
- quantifies the frozen local-cost-table approximation gap.

The result remains one seed and one pass. The dB uncertainty bounds are smoke
tests rather than held-out calibrated error models. No cluster job is
submitted.
