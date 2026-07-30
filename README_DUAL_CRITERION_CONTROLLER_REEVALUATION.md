# Corrected EESS dual-criterion controller reevaluation

Run only:

```bash
bash RUN_DUAL_CRITERION_CONTROLLER_REEVALUATION_DROPIN.sh
```

This local-only stage reruns the validated online constrained-PF controller
platform for:

- short term: P.452 p=0.005%, -133 dBW/10 MHz;
- long term: P.452 p=20%, -150 dBW/10 MHz;
- SA.509 multiple-entry primary pattern;
- SA.509 single-entry +3 dB sensitivity.

It uses a provisional ideal-digital 0--70 dB action grid and evaluates an exact
hard-null reference. It compares delayed myopic, predictive, static,
virtual-queue, common-scale, and hard-null methods under the same deterministic
load transitions. It submits no cluster job.

The output is one-seed engineering compatibility evidence. It is not a claim
of regulatory compliance, calibrated physical null depth, or paper-grade
statistical generality.
