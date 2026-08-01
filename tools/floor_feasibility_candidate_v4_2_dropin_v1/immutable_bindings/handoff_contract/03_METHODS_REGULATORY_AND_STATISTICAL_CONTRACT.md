
# Methods, Regulatory, Architecture, and Statistical Contract

## Primary architecture and physical model

- 57 sectors, 228 users.
- Generic 64T64R declared architecture:
  - 128 physical polarization ports;
  - 64 RF chains;
  - 32 dual-polarized disjoint subarrays;
  - 6-bit analog phase;
  - local digital RZF;
  - two protected modes;
  - minimum remaining digital dimension observed: 58.
- Primary earth-station antenna pattern:
  SA.509 multiple-entry.
- Sensitivity:
  SA.509 single-entry.
- Primary declared physical envelope:
  - null-depth cap 65 dB;
  - normalized-coupling uplift 3 dB.
- These are deterministic engineering scenarios, not confidence bounds.

## Regulatory engineering criteria

Long term:

- P.452 `p = 20%`;
- threshold `-150 dBW/10 MHz`.

Short term:

- P.452 `p = 0.005%`;
- threshold `-133 dBW/10 MHz`.

Both are reported. Do not substitute P.530 for the P.452 coexistence path
without a documented scientific reason. P.530 is included only as a
supplemental source/reference because it appeared in earlier fixed-service
work.

## Timing and control

- update interval: 5 seconds;
- command delay: 1 update;
- per-mode slew: 3 dB/update;
- predictive horizon: full remaining protected pass in candidate v3;
- local fail-safe latency is declared but not measured;
- message-loss fail-safe and token/entry-point locks are part of the reviewed
  package chain.

## Fairness

- primary objective: constrained moving-average proportional fairness;
- not sum rate;
- moving-average time constant: 100 seconds;
- initialization: full-load nominal user rates;
- inactive semantics: backlogged/unscheduled user receives a zero-rate EMA
  update;
- eligible threshold: 0.1 bit/s/Hz;
- current hard floor:
  `max(0.1, 0.9 * current-load nominal rate)`.

## Eight methods

1. predictive constrained PF + sector-selective fallback;
2. safe static constrained PF + sector-selective fallback;
3. delayed reactive-myopic constrained PF + same fallback;
4. delayed unshielded myopic diagnostic;
5. unshielded virtual-queue diagnostic;
6. uniform protected-tone backoff;
7. hard spatial null / exact mute;
8. instantaneous common-scale noncausal reference.

The noncausal reference is not a practical comparator. Unshielded myopic and
virtual queue are negative controls.

## Confirmatory campaign design

- channel/topology seeds: `44000--44029`;
- five fixed protected-pass blocks;
- 150 seed-pass cells;
- eight methods per cell;
- 1,200 method evaluations;
- one channel generated per seed and reused across passes/methods;
- primary endpoint:
  final moving-average sum-log utility;
- mandatory secondary:
  duration-weighted mean moving-PF utility;
- primary paired comparison:
  predictive minus safe static;
- five pass effects averaged within seed;
- 30 seed clusters bootstrapped 10,000 times;
- five passes are fixed blocks, not an iid orbital-pass population;
- no outcome-based exclusion or imputation.

## Confirmatory go rule

The campaign cannot pass unless:

1. predictive safety violations are zero in all 150 cells;
2. predictive floor-violation user-seconds are zero in all cells;
3. provenance/completeness checks pass;
4. the lower 95% seed-cluster bootstrap bound for predictive-minus-static
   final moving-PF utility is greater than zero.

The current Rorqual smoke demonstrates that criterion 2 is not yet robust
across seeds.
