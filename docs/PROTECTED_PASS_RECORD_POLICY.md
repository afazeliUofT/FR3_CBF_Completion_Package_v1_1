# Protected-pass record policy

The existing validated pass is normalized into slot 0. Four additional passes
are selected on the four consecutive UTC peak dates following slot 0. On each
date, the highest-elevation complete pass above 5 degrees is selected before
any controller calculation. Ties are resolved by earliest start time.

All five records reuse the exact archived RCM-1 TLE used by slot 0. The TLE age
at each pass peak is checked against the frozen 14-day limit. This supplies
reproducible temporal geometry diversity; it is not independent ephemeris-error
calibration and does not claim that the public station actually tracked the
modelled object.

Each record contains:

- detailed and protected-window one-second tracks;
- archived TLE and source record;
- SA.509 multiple- and single-entry site gains;
- corrected long-term P.452 p=20% coupling;
- corrected short-term P.452 p=0.005% coupling;
- exact -150 and -133 dBW/10 MHz allowance arrays;
- immutable hashes and a geometry/coupling screening summary.

The phase-1 campaign candidate remains non-executable until independent source
review returns PASS and a separate authorization token is issued.
