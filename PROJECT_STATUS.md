# Current Project Status

## Status date

27 July 2026

## Status in one sentence

The standards/data foundation, validated P.452 engine, E3 geometry and
propagation audits, 57-sector stress screen, and distributed DLP-RZF
architecture are complete as non-paper evidence. The reviewed FR3 source root
contains no reusable executable cellular channel engine. A clean Sionna 2.0.1
PyTorch implementation has passed a CPU UMa/UMi API qualification and is the
selected pilot candidate. Exact Release-19 V19.4.0 mapping and the frozen
57-sector channel adapter are the current gate.

## Completed

- Public incumbent data, pairing, terrain, P.530/S1, and P.452 validation.
- E3 earth-station/pass/pattern/layout and all 19 terrestrial paths.
- 798-row all-site P.452 audit and mechanism-isolation audit.
- 57-sector full-load reference screen.
- Distributed Leakage-Projected RZF architecture and local/aggregate
  certificate software audit.
- Channel-source review: no reusable executable Sionna UMa/UMi engine found.
- Clean Sionna 2.0.1 / PyTorch 2.9.1 CPU UMa/UMi API qualification.
- Scenario-height correction: UMa primary uses 25 m; UMi sensitivity uses 10 m.

## Current scientific gate

1. Complete an explicit ETSI TR 138 901 V19.4.0 parameter/clause mapping.
2. Build the frozen 19-site/57-sector Sionna topology adapter.
3. Run a one-seed GPU pilot with real inter-cell UE interference and local RZF.
4. Independently reconstruct rates, powers, serving-sector mapping, and DLP-RZF
   leakage constraints.
5. Only then launch the multi-seed, multi-pass dynamic-budget experiment.

## Remaining major paper gates

1. Paper-grade E3 distributed-beam and dynamic-budget experiment.
2. E1 real static fixed-service continuity experiment.
3. E2 dynamic rate-limit trap.
4. Held-out uncertainty calibration.
5. Layered runtime/scalability evidence.
6. Statistical campaign, confidence intervals, and ablations.
7. Results-complete manuscript, reproducibility release, and adversarial review.

## Claim boundaries

- The Sionna API pilot is not a paper result.
- Sionna's general TR 38.901 model label is not by itself certification of
  exact V19.4.0 coverage.
- The full-load 57-sector screen remains a severe sensitivity envelope.
- WMMSE is not the proposed operational method.
