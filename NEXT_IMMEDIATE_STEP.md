# Next Immediate Step

## Gate

`CALIBRATE_ARRAY_CSI_NULL_DEPTH_AND_PHYSICAL_UNCERTAINTY_THEN_FREEZE_PHASED_CAMPAIGN`

1. Do not launch the multi-seed campaign yet.
2. Convert the ideal 60--70 dB spatial-mode attenuation requirement into explicit array/CSI/quantization null-depth sensitivity cases.
3. Separate source-referenced deterministic engineering bounds from held-out calibrated uncertainty; do not relabel 1/3 dB smoke tests.
4. Quantify whether a practical 64T64R or hybrid architecture can meet the long-term criterion without hidden power shutdown.
5. Freeze a phased paired campaign: primary seed/pass block first, then rotations, loads, delays, O2I, pattern, and array sensitivities.
6. Preserve both inactive-user PF semantics: backlogged-unscheduled decay and departed-user removal/freeze.
