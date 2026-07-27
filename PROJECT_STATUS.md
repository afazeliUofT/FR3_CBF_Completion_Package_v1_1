# Current Project Status

## Status date

27 July 2026

## Status in one sentence

The standards/data foundation, validated propagation engine, E3 geometry, all
19 terrestrial paths, mechanism audit, and 57-sector full-load stress screen
are complete. WMMSE has been removed as the main operational architecture.
The proposed deployable method is distributed local RZF plus a closed-form
local incumbent-leakage projection under certified slowly updated scalar
per-BS budgets.

## Completed

- Operator-independent standards and claim boundary.
- Public TAFL pairing, terrain processing, P.530/S1 analysis.
- P.452-18 v18.0 reference validation under MATLAB R2026a.
- E3 earth-station record, archived pass, SA.509 pattern, 19-site/57-sector
  modelled layout.
- Manual review of all 19 terrain paths and 798-row P.452 audit.
- P.452 mechanism-isolation audit.
- 57-sector, 587-sample, 84-scenario full-load reference feasibility screen.
- Distributed architecture decision: local RZF, local leakage projection, and
  certified scalar leakage budgets without network-wide UE CSI.

## Current scientific gate

Build the standards-aligned 57-sector local-channel experiment:

1. generate reproducible local UE channels and user layouts;
2. implement local RZF and hybrid/codebook variants;
3. verify each actual transmitted composite precoder against its local budget;
4. compare static, myopic, virtual-queue, and predictive/CBF budget updates
   under identical information, latency, and update-rate limits;
5. report cellular rates, local/aggregate leakage, action changes, runtime, and
   feasibility without using a central joint beamformer.

## Remaining major paper gates

1. Complete the paper-grade E3 distributed-beam and dynamic-budget experiment.
2. E1 real static fixed-service continuity experiment.
3. E2 dynamic rate-limit trap.
4. Held-out uncertainty calibration.
5. Layered runtime and scalability evidence.
6. Statistical campaign, confidence intervals, and ablations.
7. Results-complete manuscript, reproducibility release, and adversarial review.

## Claim boundaries

- The full-load 57-sector screen is a severe reference envelope, not a paper
  result or compliance determination.
- WMMSE is not the proposed operational method.
- RZF and projection are established ingredients; novelty must come from the
  certified dynamic budget architecture and evidence.
- No O-RAN compliance claim is made without implemented interfaces and measured
  timing.
