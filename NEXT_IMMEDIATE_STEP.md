# Next Immediate Step

## Gate

`CALIBRATE_UNCERTAINTY_AND_PREPARE_MULTI_SEED_MULTI_PASS_CAMPAIGN`

## Required sequence

1. Calibrate coupling, pointing, array, and ephemeris upper errors from held-out data or a declared deterministic engineering set; do not use the 1/3 dB smoke margins as paper evidence.
2. Resolve and implement the exact long-term regulatory functional separately from the certified short-term constraint.
3. Freeze one immutable multi-seed/multi-pass experiment package using `config/multi_seed_campaign_spec_v1.json`.
4. Include stochastic arrivals/departures in addition to the deterministic rotating-load stress test.
5. Include layout rotations, O2I stratification, finite-network sensitivity, a practical 64T64R primary case, and the 128-port digital upper reference.
6. Launch the statistical campaign only after independent review of the calibration and campaign package.
