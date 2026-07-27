# Paper Completion Checklist

## Standards and data

- [ ] Exact edition and clause/table are recorded for every numeric criterion.
- [ ] ITU-R engineering criteria are not described as Canadian licensing law.
- [ ] +19 dB is supported by the real S1 gate or removed/relabelled.
- [ ] EESS thresholds use absolute antenna-output power in the stated bandwidth.
- [ ] P.452/P.2108 clutter is not double counted.
- [ ] Cellular power is labelled conducted/TRP/EIRP.
- [ ] Real incumbent records and pairing provenance are archived.

## Mathematics

- [ ] Timing order is explicit.
- [ ] Robust physical set is independent of the chosen beam.
- [ ] Probability statement uses finite uncertainty epochs.
- [ ] Exceedance-budget proof and implementation match.
- [ ] EMA is a margin governor, not the time-percentage proof.
- [ ] Every certified result has zero emergency slack.
- [ ] Hybrid results are re-verified after factorization.

## Experiments

- [ ] E1 uses real GTA data and validated coupling.
- [ ] E2 contains a reproducible rate-limit trap.
- [ ] E3 uses archived TLE and documented station fields.
- [ ] Baselines include static robust, myopic, and queue-based methods.
- [ ] Coverage, violations, utility, conservatism, action changes, and runtime are reported.
- [ ] Confidence intervals and seed counts are reported.
- [ ] Demo outputs are not used as evidence.

## Claims

- [ ] No claim that CBFs themselves are new.
- [ ] No infinite-horizon probability claim from fixed per-slot risk.
- [ ] No claim that synthetic calibration certifies the physical world.
- [ ] No global optimality claim for WMMSE.
- [ ] No O-RAN compliance claim without measured runtime and exact clauses.
- [ ] No direct hybrid implementability claim without verification.

## Reproducibility

- [ ] Configurations and input hashes are archived.
- [ ] Tests pass in a clean environment.
- [ ] Raw and processed result files are retained.
- [ ] Figure scripts reproduce every paper figure.
- [ ] Final archive has a SHA-256 manifest.
