# Distributed local IA-RZF architecture correction

Run only:

```bash
bash RUN_DISTRIBUTED_IA_RZF_ARCHITECTURE_DROPIN.sh
```

This drop-in:

1. removes WMMSE as the main operational architecture;
2. freezes local RZF plus a closed-form minimum-deviation incumbent-leakage
   projection;
3. freezes the certified aggregate-to-local scalar budget decomposition;
4. records the exact information that may and may not cross BS boundaries;
5. writes a paper-ready mathematical system-model section;
6. updates the canonical project-status files;
7. runs a deterministic 57-sector local-channel software audit;
8. verifies every local budget, the aggregate certificate, and power
   nonincrease;
9. pushes all source and evidence to the existing GitHub branch.

The deterministic local channels are a software audit only. The next stage is
the standards-aligned 57-sector local-channel experiment with real rate,
loading, latency, controller, runtime, uncertainty, and repetition evidence.
