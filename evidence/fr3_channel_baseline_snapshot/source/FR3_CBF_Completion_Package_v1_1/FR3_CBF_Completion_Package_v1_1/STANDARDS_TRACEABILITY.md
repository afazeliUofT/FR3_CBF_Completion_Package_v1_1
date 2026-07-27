# Standards and Model Traceability

The machine-readable source of truth is `config/regulatory_constants.yaml`.

| Object | Primary source | Role |
|---|---|---|
| BS-UE channel | ETSI/3GPP TR 38.901 V19.4.0 | UMa stochastic cellular baseline |
| Terrestrial BS-incumbent path | ITU-R P.452-18 | Interference path between stations on the Earth’s surface |
| Additional clutter | ITU-R P.2108-1 | Only when compatible and not double counted |
| Wanted fixed link | ITU-R P.530-19 | Fade/outage adequacy for S1; not the BS-incumbent path |
| FS aggregate long-term criterion | ITU-R F.758-8 | Engineering sharing criterion with stated scope |
| Canadian 7725-8275 MHz plan | ISED SRSP-307.7 Issue 6 | Channel plan and fixed-service parameters |
| EESS earth-station criteria | ITU-R SA.1027-6 | Absolute aggregate power at antenna output in 10 MHz |

## No-double-counting rules

- Do not add P.2108 clutter when the P.452 implementation already represents the same clutter effect.
- Do not include element gain in path gain and again in the array factor.
- Do not apply full-band/tone-group scaling twice.
- Do not convert an absolute SA.1027 threshold to I/N without a separately justified transformation.
- Do not use P.530 for the cellular-to-incumbent interference path.
- Do not present a MODEL_DECISION or PROVISIONAL value as a mandatory rule.

Before submission, store the exact edition and clause/table for every numeric criterion with the result archive.
