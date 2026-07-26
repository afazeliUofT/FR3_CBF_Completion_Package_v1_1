# Next Immediate Step

## Gate

First actual modelled cellular-sector-to-EESS-earth-station P.452 path.

## Inputs already frozen

- `data/real/earth_station.csv`
- `data/real/bs_sites.csv`
- `data/real/bs_sectors.csv`
- `data/real/e3_reference_case/e3_track_selected_pass_1s.csv`
- `data/real/e3_pattern_layout_review/selected_pass_off_axis_summary.csv`
- validated ITU-R P.452-18 v18.0 implementation
- official P.452 digital products
- archived MRDEM layout subset

## Required sequence

1. Select one audit sector using a deterministic rule independent of its final
   P.452 result.
2. Create a single site-to-station link-input CSV.
3. Build and visually review its 30 m MRDEM terrain profile.
4. Freeze propagation assumptions before running MATLAB:
   - zero terminal gains inside P.452;
   - explicit clutter treatment;
   - signed coordinates;
   - declared propagation time-percentage grid.
5. Calculate P.452 basic transmission loss.
6. Apply BS directional gain, earth-station off-axis gain, bandwidth
   conversion, activity, and polarization terms outside P.452 exactly once.
7. Validate all dB/linear conversions and hashes.
8. Label the output as a one-sector accounting audit.

## Stop condition

Do not scale to 57 sectors until the one-sector result has:

- reviewed terrain;
- validated P.452 output;
- explicit gain accounting;
- no clutter or antenna-gain double counting;
- explicit time-percentage interpretation;
- a complete audit and SHA-256 evidence manifest.
