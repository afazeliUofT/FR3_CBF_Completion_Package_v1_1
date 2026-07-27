# Distributed architecture review and FR3 channel-readiness drop-in

Run only:

```bash
bash RUN_DISTRIBUTED_CHANNEL_READINESS_DROPIN.sh
```

The drop-in:

1. independently reviews the distributed leakage-projected RZF architecture;
2. records that the deterministic prototype did not test inter-cell rates,
   standards channels, rate-limited budgets, delays, hybrid factorization, or
   statistics;
3. repairs the architecture source-package manifest by removing cache and
   bytecode entries;
4. collects a bounded text-only snapshot of the existing FR3 channel/topology
   implementation;
5. strips notebook outputs and screens for common secret patterns;
6. opens the snapshot and requires explicit manual review before public push;
7. freezes the Release-19 standards-aligned experiment specification;
8. pushes all source and evidence to the existing GitHub branch.

Default external source root:

```text
/mnt/c/Users/alifa/OneDrive/Projects/FR3_MainWork_For_Journal
```

Override without editing the package:

```bash
FR3_CHANNEL_SOURCE_ROOT='/correct/path' \
  bash RUN_DISTRIBUTED_CHANNEL_READINESS_DROPIN.sh
```

The package also removes any previously tracked `__pycache__`, `.pytest_cache`, `.pyc`, and `.pyo` artifacts from the Git index and rebuilds the architecture manifest without them.
