# Clean Sionna 2.0.1 channel qualification drop-in

Run only:

```bash
bash RUN_SIONNA2_CHANNEL_QUALIFICATION_DROPIN.sh
```

The drop-in:

1. closes the reviewed FR3 channel-source snapshot;
2. records whether a reusable executable channel baseline exists;
3. creates an isolated CPU virtual environment outside the repository;
4. verifies the official `sionna-no-rt==2.0.1` wheel SHA-256;
5. installs `torch==2.9.1` and Sionna 2.0.1;
6. runs one-ring UMa and UMi channel API pilots at 8.15 GHz;
7. verifies topology sizes, antenna counts, finite coefficients, delays, and
   seeded CPU reproducibility;
8. corrects the UMi sensitivity height to its model-consistent 10 m value;
9. preserves the exact Release-19 V19.4.0 mapping as an open gate;
10. updates project status and pushes all review evidence to GitHub.

The virtual environment and downloaded wheels are not committed. The output is
qualification evidence only, not a paper result.

The qualification calls the Sionna 2.0.1 UMa/UMi system-level channel model with its documented `num_time_samples` keyword and accepts the official CPU PyTorch wheel's local `+cpu` version suffix while enforcing base version 2.9.1.
