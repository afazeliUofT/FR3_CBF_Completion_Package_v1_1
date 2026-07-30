# Declared array/CSI engineering scenario matrix v1

Measured OTA array/CSI residual data are unavailable. This stage therefore
selects the **deterministic-engineering-scenario branch** of the calibration
gate. It does not relabel assumed values as measurements or confidence bounds.

The declared scenario matrix is:

- protected-mode null-depth caps: 60, 65, and 67 dB;
- residual normalized-coupling uplifts: 0, 1, and 3 dB;
- sector protected-tone backoff: 0--12 dB plus an exact mute endpoint.

The primary decisive screen is the long-term SA.509 single-entry sensitivity
with a 65 dB null-depth cap and a 3 dB residual-coupling uplift. The 60 dB plus
3 dB case is retained as a boundary stress.

These numbers are **not**:

- measured OTA calibration statistics;
- 95% or other probabilistic bounds;
- source-referenced hardware guarantees;
- practical regulatory-compliance evidence.

They are transparent one-seed engineering stresses used to test whether a
sector-selective fail-safe can preserve hard incumbent safety and user floors
better than a uniform protected-tone backoff.

The array/CSI calibration template remains the route for replacing this
scenario matrix with measured or source-referenced bounds. Until a practical
64T64R or hybrid architecture is mapped and an immutable phase-1 bundle is
independently reviewed, the multi-seed campaign remains unauthorized.
