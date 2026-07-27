# E3 57-sector reference feasibility-screen drop-in

Run only:

```bash
bash RUN_E3_57_SECTOR_REFERENCE_SCREEN_DROPIN.sh
```

The drop-in:

1. closes the human review of the 19-site P.452 basic-loss audit;
2. classifies terrain-supported diffraction-dominated paths;
3. runs a numerical P.452 troposcatter-isolation probe;
4. stops if external direct-gain factorization is not supported;
5. builds sector-specific zero, element-pattern, and coherent-array-envelope
   gain cases for all 57 sectors;
6. computes time-varying SA.509 gain for all 19 sites across the protected
   pass;
7. aggregates all 57 sectors in linear received power;
8. derives long/short required-backoff and common-scale envelopes;
9. ranks dominant sectors at every conditional scenario peak;
10. validates, packages, and pushes all review evidence to GitHub.

This is a reference feasibility screen, not the final composite-WMMSE,
dynamic-controller, paper, or compliance result.

If the numerical mechanism-isolation threshold fails, the same drop-in skips the gain-factorized 57-sector screen, commits the complete diagnostic evidence to GitHub, and reports the mechanism-specific model as the next gate.
