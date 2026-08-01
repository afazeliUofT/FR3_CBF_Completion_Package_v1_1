
# Executive Scientific Status

## Research objective

Develop a practical, distributed FR3 coexistence controller for a cellular
network sharing spectrum with an Earth-exploration satellite service (EESS)
earth station. The controller must protect the incumbent under delayed and
slew-limited actuation while preserving user fairness.

The work intentionally moved away from centralized WMMSE. The primary
architecture is local RZF plus distributed/local mode attenuation and a sparse
sector-selective emergency fallback. Sum rate is not the primary objective.
The frozen utility is constrained moving-average proportional fairness.

## Core contribution currently supported

A predictive constrained-PF controller can use a preloaded ephemeris-derived
future coupling envelope to maintain a hard incumbent-interference constraint
under one-update delay and 3 dB/update attenuation slew. Safe static, reactive
myopic with the same fallback, unsafe unshielded myopic, virtual-queue,
uniform-backoff, hard-null/mute, and noncausal common-scale references are
separated explicitly.

The platform includes:

- 57 sectors and 228 users;
- five protected pass geometries;
- practical generic 64-RF-chain / 128-port / 6-bit subarray architecture;
- corrected EESS long-term and short-term criteria;
- a 65 dB declared null-depth cap and 3 dB declared coupling uplift;
- one cellular channel per seed reused over all passes and methods;
- 30 predeclared confirmatory seeds and 1,200 method/pass/seed evaluations;
- paired seed-cluster bootstrap statistics;
- immutable package, result schema, execution locks, and review chain.

## Correct regulatory engineering tests

The historical `p=20%` / `-133 dBW` combination was corrected.

- Long term:
  P.452 `p=20%`, threshold `-150 dBW/10 MHz`.
- Short term:
  P.452 `p=0.005%`, threshold `-133 dBW/10 MHz`.
- SA.509 multiple-entry is the primary aggregate-network earth-station pattern.
- SA.509 single-entry is retained as a conservative +3 dB sensitivity.
- These are engineering tests, not a universal licensing conclusion.

## Major successful milestones

### Robust delayed safety

For the original validated seed/pass:

- delayed myopic: 39 or more safety-violation seconds depending on milestone;
- predictive: 0 safety violations;
- 1 dB case with two dropped commands: 0 violations;
- 3 dB case: 0 violations;
- virtual queue remains unsafe for instantaneous protection.

### Online moving-average PF and load transitions

The deterministic load sequence was:

`228 -> 114 -> 228 -> 57 -> 171 -> 114 active users`.

The predictive method remained safe under load transitions and message drops.
The online-PF increment over frozen local tables was small, while the safety
benefit over delayed myopic was decisive.

### Corrected dual criteria

Under all four long/short and multiple/single pattern cases, the ideal
fully-digital predictive controller had zero incumbent violations. The
long-term criterion was the harder normalized constraint in the frozen
realization.

### Practical null-depth and selective fallback

Uniform protected-tone backoff can recover safety but causes severe fairness
loss at insufficient null depth. Sector-selective fallback is much better. In
the one-seed 65 dB / 3 dB single-entry screen, selective fallback had zero
eligible-floor violations while uniform backoff had 19.

### Generic 64T64R architecture

The selected declared primary is:

- 64 RF chains;
- 128 polarization ports;
- 32 dual-polarized disjoint subarrays;
- 6-bit analog phase;
- digital RZF and protected-mode control after the analog network.

One-seed nominal network-sum retention versus the 128-port upper reference was
about 98.66%, with 58 minimum remaining digital dimensions and no local-rank
failures.

### Campaign package

Candidate v3, its round-2 review, the immutable Nibi job package, and the job
package independent review passed their respective preparation gates. The full
campaign remained locked pending a noncampaign deployment smoke.

## Rorqual excluded smoke

### H100 smoke job

- Rorqual job: `18041525`;
- excluded seed: `43999`;
- user seed: `87998`;
- channel seed: `87999`;
- H100 environment, channel generation, architecture construction, and
  incumbent-safety computation reached the controller evaluation;
- job stopped at `pass 0: predictive floor hard gate failed`;
- observed host MaxRSS was only about 2.24 GiB despite a conservative 124 GiB
  request;
- no evidence of an OOM or GPU failure.

### CPU diagnostic

- Rorqual CPU job: `18059211`;
- reused the preserved H100 channel;
- H100 regeneration: no;
- 16 CPUs, 32 GiB requested;
- elapsed: 1 minute 50 seconds;
- MaxRSS: approximately 367 MiB;
- completed successfully;
- current GitHub evidence commit:
  `76a62cda5d649cad25a6a45ccb5f0f757a99a269`.

## Current diagnostic result

The diagnostic evaluated all five passes and all eight methods without
enforcing the hard floor gate.

For the predictive controller:

- eligible users: `205`;
- long-term EESS violations: `0`;
- short-term EESS violations: `0`;
- floor-violation user-intervals: `104`;
- floor-violation user-seconds: `519`;
- unique pass-user pairs: `7`;
- minimum floor ratio: `0.810696983385736`;
- maximum normalized floor shortfall: `0.18930301661426396`;
- classification: `MATERIAL`.

Pass results:

| Pass | User-seconds | User-intervals | Users | Min ratio | Max shortfall |
|---:|---:|---:|---:|---:|---:|
| 0 | 135 | 27 | 1 | 0.972665 | 2.7335% |
| 1 | 135 | 27 | 1 | 0.972819 | 2.7181% |
| 2 | 55 | 11 | 1 | 0.972632 | 2.7368% |
| 3 | 79 | 16 | 2 | 0.810697 | 18.9303% |
| 4 | 115 | 23 | 2 | 0.810703 | 18.9297% |

Affected users:

1. `E3_SITE_02_SEC_3_UE_4`
   - affected in every pass;
   - 500 of the 519 violation user-seconds;
   - minimum ratio about 0.97245;
   - persistent, moderate shortfall.
2. `E3_SITE_07_SEC_1_UE_2`
   - affected only in the final extended intervals of passes 3 and 4;
   - 19 violation user-seconds;
   - minimum ratio about 0.81070;
   - likely tied to the absolute 0.1 bit/s/Hz floor and the variable-pass
     extension/load rule.

## Scientific interpretation

This is not an incumbent-safety failure. It is a fairness-feasibility blocker.

The fact that safe static, reactive myopic, uniform backoff, and common-scale
references also exhibit floor violations indicates that the issue is not
merely a predictive-controller coding bug. It may arise from:

- infeasibility of the current floor under the frozen 65 dB/3 dB envelope;
- the current action space (mode attenuation and sector power scale) lacking a
  floor-restoring degree of freedom;
- the floor definition using 90% of **current-load nominal rate**, which can
  become demanding in low-load phases;
- the absolute 0.1 bit/s/Hz floor at the extended final phases;
- lack of user-specific power/scheduling/reassignment actions in the fallback;
- a combination of the above.

The next stage must distinguish these possibilities quantitatively.
