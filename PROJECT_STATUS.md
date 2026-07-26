# Current Project Status

## Status date

26 July 2026

## Status in one sentence

The mathematical and standards framework, public fixed-service audit,
validated P.452-18 engine, and E3 station/pass/pattern/layout preparation are
substantially complete. The next scientific gate is the first actual
cellular-sector-to-earth-station P.452 path. Paper-grade E1-E3 results,
uncertainty calibration, runtime measurements, statistical repetitions, and
the final manuscript remain incomplete.

## Completed

- Research question and defensible novelty boundary.
- Canonical beam-space and layered safety-filter system model.
- Exact prefix exceedance-budget logic and reserve-margin CBF.
- Operator-independent publication scope.
- Frozen public TAFL source and audited TX-RX pairing.
- Seventy frequency-specific GTA fixed-link records representing reviewed
  physical paths.
- MRDEM terrain processing and reviewed P.530 wanted-link inputs.
- Conditional S1 allocation analysis.
- Rejection of +19 dB as a uniform always-on fixed-service cap.
- P.530 warning disposition.
- P.452-18 v18.0 reference implementation validated under MATLAB R2026a.
- Project-specific P.452 profile/MATLAB/export pilot.
- Public/modelled E3 earth-station record.
- Archived TLE and selected complete satellite pass.
- ITU-R SA.509-3 reference antenna-pattern model, with explicit claim boundary.
- Frozen deterministic 19-site/57-sector E3 UMa reference layout.

## Current scientific gate

Build and audit one actual cellular-sector-to-earth-station path:

1. select one sector deterministically;
2. build and review its MRDEM terrain profile;
3. calculate P.452 basic transmission loss with zero terminal antenna gains;
4. apply BS directional gain and earth-station off-axis gain separately;
5. verify bandwidth, power, clutter, polarization, and time-percentage
   accounting;
6. retain the result as a one-sector accounting audit, not yet a paper result.

## Remaining major paper gates

1. Full E3 sector-level coupling and drifting-geometry experiment.
2. E1 real static fixed-service continuity experiment.
3. E2 dynamic rate-limit experiment.
4. Held-out uncertainty calibration.
5. Practical layered implementation and runtime/scalability evidence.
6. Frozen statistical campaign with confidence intervals and ablations.
7. Results-complete manuscript, reproducibility release, and adversarial review.

## Claim boundaries

- No unique operator-specific fixed-service short-term cap is claimed.
- +19 dB is not used as a uniform always-on fixed-service cap.
- The E3 station coordinate, phase-centre height, antenna pattern, and cellular
  layout contain explicitly labelled model decisions.
- Synthetic or model-based calibration does not certify physical deployment.
- The architecture is called O-RAN-inspired unless exact interfaces and
  measured timing support a stronger claim.
