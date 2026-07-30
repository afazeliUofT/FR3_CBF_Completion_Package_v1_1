# Practical null-depth and array/CSI sensitivity audit

Run only:

```bash
bash RUN_PHYSICAL_IMPAIRMENT_SENSITIVITY_DROPIN.sh
```

The local-only stage preserves the ideal corrected dual-criterion result while
quantifying how implementable null-depth caps, protected-tone fallback,
assumed differential port gain/phase errors, steering errors, error
correlation, and phase quantization affect the worst long-term cases.

All perturbation levels are deterministic engineering sensitivities. They are
not measured or statistically calibrated hardware/CSI uncertainty. The stage
freezes the calibration requirements and a phased campaign design but does not
authorize campaign execution.
