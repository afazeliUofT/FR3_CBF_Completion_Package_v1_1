# Claim Changes from Candidate v2 to Candidate v3

## Strengthened provenance

- The two EESS criteria are now tied directly to ITU-R SA.1027-6, Table 1, including band, bandwidth, exceedance percentages, minimum elevation, and the requirement to satisfy both criteria.
- The P.452-18 implementation validation, MRDEM terrain source, clutter treatment, no-double-count rule, and annual time-percentage semantics are stated.
- The channel claim is version-bound to Sionna 2.0.1 UMa and no longer implies independent TR 38.901 V19.4.0 certification.

## Narrowed claims

- “Pre-registered” is replaced by “Git-frozen and pre-specified before holdout execution.”
- The aggregate network is an engineered single sharing entry by study convention, not a normatively classified single transmitter.
- The EESS safety result is explicitly conditional on the declared SA.509 multiple-entry reference pattern.
- The public Gatineau geometry is not represented as a complete calibrated model of an identified operational station.
- The single-entry SA.509 curve is a conservative frozen-action stress, not a certified real-station bound.
- The paper continues to avoid regulatory-compliance and hardware-calibration claims.

## Added sensitivity

The exact frozen-action SA.509 single-entry sensitivity shows:

- 83,859 long-criterion violation-seconds;
- all 150 pass cells and all 30 seeds affected;
- zero short-criterion violation-seconds;
- maximum long ratio approximately 2.0;
- approximately 3.01 dB additional attenuation required to make the same frozen actions long-safe.

This is not a controller reoptimization and is not presented as an alternate primary result.

## Corrected utility interpretation

The candidate-minus-safe-static effect corresponds to +0.1099% in the epsilon-shifted geometric mean of final moving rates across 228 users. The wording no longer suggests a large raw-capacity gain.

## Unchanged claims

The fresh-holdout statistical results, zero violations under the declared primary model, bounded action scope, fixed post-mode power, floor-burden reductions, and feasibility-conditioned floor semantics are unchanged.
