# P.452 Pilot Coordinate-Convention Hotfix

## Defect corrected

The previous pilot-preparation script converted western-hemisphere longitude
from signed degrees (for example, `-78.91669444`) to the `[0, 360)` interval
(for example, `281.08330556`) using `% 360.0`.

The pinned ITU-R P.452-18 MATLAB v18.0 implementation passes longitude to its
refractivity-map interpolation in the signed range `[-180, 180]`. The wrapped
value therefore caused MATLAB to stop with:

```text
Longitude must be within the range -180 to 180 degrees
```

## Changes

- Preserves signed longitude in `[-180, 180]`.
- Validates all profile and terminal longitudes and latitudes in Python.
- Records the coordinate convention and exact `tl_p452` argument order.
- Adds a strict pre-MATLAB input gate:
  `scripts/21_2_preflight_p452_pilot_inputs.py`.
- Adds the same coordinate checks inside MATLAB before `tl_p452` is called.
- Clears stale MATLAB outputs at the beginning of each new MATLAB run.
- Extends the final pilot validator to verify the coordinates and convention.
- Adds regression tests for western-hemisphere coordinates and rejects the
  invalid wrapped value `281.08330556`.

## Claim boundary

This hotfix changes only coordinate representation and validation. It does not
change the selected path, terrain, P.452 model, time percentages, polarization
branches, terminal gains, clutter choice, or coast-distance assumptions.

The pilot remains a pipeline audit and is not paper evidence.

## Recommended application

After extracting the hotfix at the repository root, run:

```bash
bash RUN_P452_COORDINATE_REPAIR.sh
```

The wrapper executes in its own shell process, archives the invalid pilot,
runs the regression tests, regenerates the inputs, proves that the reviewed
profile and GeoJSON are unchanged, freezes the corrected inputs, and runs the
strict pre-MATLAB gate. It stops before launching MATLAB.
