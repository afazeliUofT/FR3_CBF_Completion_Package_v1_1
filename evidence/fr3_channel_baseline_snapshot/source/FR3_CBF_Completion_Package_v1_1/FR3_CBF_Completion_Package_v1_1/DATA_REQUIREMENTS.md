# Data Requirements

## 1. Fixed-service incumbent receiver table

Template: `data/templates/incumbents_fs.csv`

Required: receiver coordinates, height, channel centre/bandwidth, antenna gain/pattern or documented fallback, azimuth, licence/source identifiers, and provenance. Missing quantities must be uncertainty intervals or explicit unknowns, not invented precise values.

## 2. Paired fixed links for S1

Template: `data/templates/paired_fs_links.csv`

S1 needs the wanted link, not only the protected receiver. Required: endpoints, antenna altitudes AMSL, mean terrain elevation, frequency, fade margin, and incremental-outage allocation. Pair only through a trusted database relation/key. Do not use nearest-neighbour pairing as evidence.

## 3. Base-station sectors

Template: `data/templates/bs_sectors.csv`

Record coordinates, height, azimuth, downtilt, array geometry, conducted power, element pattern, loading/activity, and provenance.

## 4. P.452 coupling

Template: `data/templates/p452_coupling.csv` or NPZ bundle.

This package deliberately does not disguise free-space or P.1411 demo coupling as P.452-18. Supply a validated P.452-18 result or independently verified export. State whether clutter is included in the profile calculation or applied separately.

## 5. Earth station and TLE

Templates: `data/templates/earth_station.csv` and `data/external/tle/active_case.tle`.

Record site, altitude, dish gain/pattern, minimum elevation, target mission, source, and whether each field is public, measured, or modelled. Archive TLE retrieval time.

## 6. Calibration data

Template: `data/templates/calibration_residuals.csv`.

Possible residuals: path-loss dB, pointing degree, location metre, activity/loading, ephemeris, antenna-pattern dB, and forecast error. Split calibration/test data before selecting quantiles.

## 7. Result provenance

Every real result directory must contain:

- exact configuration;
- code/archive hash;
- input hashes;
- seeds;
- environment information;
- raw trajectories;
- summary table;
- figure-generation record;
- warnings and slack events.
