# Current Project Status

## Status date

27 July 2026

## Status in one sentence

The propagation/E3 foundation, distributed DLP-RZF architecture, Sionna 2.0.1
CPU qualification, custom 57-sector adapter, used-subset V19.4.0 mapping, and
exact dual-polarized Sionna port-order audit are complete as non-paper evidence.
A self-contained Nibi H100 bundle for the one-seed 57-sector/four-user DLP-RZF
pilot is prepared but has not yet been executed or independently accepted.

## Current gate

`INDEPENDENT_REVIEW_THEN_RUN_NIBI_ONE_SEED_GPU_PILOT`

## Completed in the preparation stage

- Clause-level used-subset ETSI TR 138 901 V19.4.0 mapping for a non-paper pilot.
- Explicit Release-19 delta gaps retained; no full V19.4 certification claim.
- 8x8 dual-cross Sionna port positions and polarization index sets audited.
- Far-field justification for the reduced pilot array.
- Reviewable Nibi H100 source bundle with 57 sectors, four users per sector,
  nine frequency samples, local RZF, all inter-cell interference, and protected-
  tone dual-polarization DLP projection.

## Immediate requirements

1. Independently review the generated GitHub source and bundle manifest.
2. Run the one-seed Nibi H100 pilot only after that review.
3. Validate power, SINR, rate, leakage, port order, runtime, and GPU memory.
4. Keep the result explicitly non-paper evidence.
5. Complete Release-19 delta patches/sensitivities before the final campaign.
