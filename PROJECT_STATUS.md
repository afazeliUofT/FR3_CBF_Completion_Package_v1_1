<!-- BEGIN PHASE1 INDEPENDENT REVIEW ROUND2 -->
## Phase-1 independent review round 2

Candidate v3:

- commit: `be9053dd18deaeef6ab87597e706ab45092ea8cf`;
- ZIP SHA-256: `f7b47fd3a07e30987b7f0901df1706d6127774d32284e7d3b0da38185d810161`;
- verdict:
  `PASS_FOR_IMMUTABLE_JOB_PACKAGE_PREPARATION_NOT_EXECUTION`;
- campaign execution authorized: `NO`.

The campaign contract, fixed-pass statistical plan, method information classes,
source snapshot, compute DAG, five pass records, and execution locks pass
review. The immutable job package must implement the reactive-myopic fallback,
use the v3 contract as the sole canonical source, preserve channel reuse, and
pass a separate independent review before any execution token is issued.

**Next gate:** `BUILD_AND_INDEPENDENTLY_REVIEW_IMMUTABLE_PHASE1_NIBI_JOB_PACKAGE`
<!-- END PHASE1 INDEPENDENT REVIEW ROUND2 -->

<!-- BEGIN PHASE1 INDEPENDENT REVIEW ROUND1 -->
## Phase-1 independent review round 1

Candidate v2 at commit `f26af9f3ff595f6b6ae9b468c79683e53bc8b450`
passed architecture, five-pass provenance, manifest, and execution-lock checks,
but received:

`REQUIRES_REVISION_BEFORE_INDEPENDENT_PASS`

Candidate v3 now freezes:

- one primary declared envelope: 65 dB null cap and 3 dB uplift;
- exact method information/fallback classes;
- a reactive-myopic comparator with the same emergency fallback;
- exact variable-pass-length load semantics;
- a seed-cluster paired statistical plan with passes treated as fixed blocks;
- immutable source/config snapshots;
- one-channel-generation-per-seed compute DAG.

Campaign execution remains unauthorized.

**Next gate:** `INDEPENDENTLY_REVIEW_PHASE1_CAMPAIGN_CANDIDATE_V3`
<!-- END PHASE1 INDEPENDENT REVIEW ROUND1 -->

<!-- BEGIN FIVE PROTECTED PASS RECORDS -->
## Five immutable protected-pass records

- pass records ready: `5 / 5`;
- selection: four predeclared consecutive UTC peak dates after slot 0;
- daily rule: highest complete visible pass by peak elevation before any
  controller calculation;
- orbit engine: Skyfield;
- TLE policy: exact archived slot-0 TLE, with age checked against the frozen
  14-day limit;
- criteria per pass: long/short P.452 percentile pairing and both SA.509
  multiple-/single-entry patterns;
- campaign execution authorized: `NO`.

These passes provide temporal geometry diversity under one archived orbital
record. They do not constitute independent ephemeris-error calibration.

**Next gate:** `INDEPENDENTLY_REVIEW_COMPLETE_PHASE1_CAMPAIGN_CANDIDATE`
<!-- END FIVE PROTECTED PASS RECORDS -->

<!-- BEGIN PRACTICAL 64T64R ARCHITECTURE -->
## Generic practical 64T64R architecture mapping

- selected primary: `generic_64t64r_subarray_6bit`;
- 64 RF chains over 128 polarization ports using 32 dual-polarized disjoint subarrays;
- nominal network-sum retention versus 128-port upper reference: `98.660021%`;
- primary safety violations: `0`;
- primary eligible-floor violations: `0`;
- minimum digital nullspace dimension: `58`;
- 32-RF-chain sensitivity floor violations: `None`.

This is a generic declared architecture, not a vendor-product or calibrated-hardware model. The phase-1 campaign review candidate is execution-blocked until four additional protected-pass records and independent review are available.

**Next gate:** `ACQUIRE_FOUR_ADDITIONAL_PROTECTED_PASS_RECORDS_AND_INDEPENDENTLY_REVIEW_PHASE1_CAMPAIGN_CANDIDATE`
<!-- END PRACTICAL 64T64R ARCHITECTURE -->

<!-- BEGIN DECLARED ENVELOPE SECTOR BACKOFF -->
## Declared-envelope sector-selective protected-tone fallback

Measured OTA array/CSI calibration remains unavailable. The project
therefore freezes explicit deterministic engineering scenarios rather
than claiming a calibrated physical uncertainty distribution.

Primary long-term SA.509 single-entry engineering screen:

- null-depth cap: `65 dB`;
- residual normalized-coupling uplift: `3 dB`;
- sector-selective long-term violation seconds: `0`;
- sector-selective paired short-term violation seconds: `0`;
- sector-selective eligible-user floor violations: `0`;
- uniform-backoff eligible-user floor violations: `19`;
- sector-selective mean PF utility: `95.669746245`;
- uniform-backoff mean PF utility: `93.567054214`;
- sector-selective mean protected-band retention: `92.159165%`;
- uniform-backoff mean protected-band retention: `84.502692%`.

The 60 dB + 3 dB boundary case is safety-feasible only by using
the explicit sector fail-safe and still causes `3` eligible-user floor violations. This shows that the deterministic scenario matrix
does not replace practical calibration or architecture mapping.

The multi-seed campaign remains unauthorized.

**Next gate:** `MAP_PRACTICAL_64T64R_OR_HYBRID_ARCHITECTURE_AND_INDEPENDENTLY_REVIEW_PHASE1_CAMPAIGN_BUNDLE`
<!-- END DECLARED ENVELOPE SECTOR BACKOFF -->

<!-- BEGIN PHYSICAL IMPAIRMENT SENSITIVITY -->
## Practical null-depth and physical-impairment sensitivity

The corrected ideal-digital controller remains valid, but practical array/CSI
calibration is not yet available. In the one-seed long-term single-entry
sensitivity:

- clipping the protected-mode attenuation to 60 dB produces
  `582` violation seconds;
- a conservative uniform protected-tone fallback then requires
  `6.911` dB backoff;
- at a 67 dB cap, the corresponding fallback is
  `1.558` dB;
- assumed differential phase/gain, steering, and phase-quantization errors can
  break the near-zero-margin solution;
- these are deterministic sensitivity tests, not empirical calibration.

The multi-seed campaign is frozen as a phased design but remains unauthorized.

**Next gate:** `ACQUIRE_OR_DECLARE_ARRAY_CSI_CALIBRATION_ENVELOPE_AND_IMPLEMENT_NULL_FLOOR_AWARE_SECTOR_BACKOFF`
<!-- END PHYSICAL IMPAIRMENT SENSITIVITY -->

<!-- BEGIN CORRECTED DUAL-CRITERION CONTROLLERS -->
## Corrected EESS dual-criterion controller reevaluation

The online constrained-PF controller platform has been rerun locally with:

- short term: P.452 `p=0.005%`, `-133 dBW/10 MHz`;
- long term: P.452 `p=20%`, `-150 dBW/10 MHz`;
- SA.509 multiple-entry primary pattern;
- SA.509 single-entry `+3 dB` sensitivity;
- provisional ideal-digital action grid `0--70 dB`;
- exact hard-null upper reference.

Primary long-term multiple-entry result:

- delayed-myopic violation seconds:
  `67`;
- predictive violation seconds:
  `0`;
- predictive PF utility:
  `95.751060416`;
- static PF utility:
  `95.703501965`;
- predictive mean protected-band retention:
  `95.948175%`;
- predictive minimum eligible-user floor ratio:
  `1.001008`.

Single-entry long-term sensitivity:

- delayed-myopic violation seconds:
  `58`;
- predictive violation seconds:
  `0`;
- predictive PF utility:
  `95.733459313`.

The long-term normalized constraint elementwise dominates the paired short-term
constraint by at least
`13.897 dB`
in this deterministic percentile-matched model. The short-term runs remain
reported separately for transparency.

All predictive cases and the 70 dB terminal action pass the finite-pass safety
certificate with zero eligible-user floor violations. This remains an ideal
one-seed engineering compatibility result, not regulatory-compliance evidence
or a paper result.

**Next gate:** `CALIBRATE_ARRAY_CSI_NULL_DEPTH_AND_PHYSICAL_UNCERTAINTY_THEN_FREEZE_PHASED_CAMPAIGN`
<!-- END CORRECTED DUAL-CRITERION CONTROLLERS -->

<!-- BEGIN EESS DUAL CRITERION CORRECTION -->
## EESS dual-criterion correction

The historical controller platform combined P.452 `p=20%` with the
`-133 dBW/10 MHz` short-term threshold. It remains valid as algorithmic
one-seed evidence, but not as a final regulatory test.

The corrected percentile-matched terrestrial single-entry tests are:

- long term: P.452 `p=20%`, threshold `-150 dBW/10 MHz`;
- short term: P.452 `p=0.005%`, threshold `-133 dBW/10 MHz`;
- both criteria must be met.

No new P.452 or channel-generation job is needed. The existing all-sector table
already includes `p=0.005%`.

For the SA.509 multiple-entry aggregate-network pattern, required common
attenuation ranges are:

- short term: `34.592` to `48.636` dB;
- long term: `49.381` to `63.383` dB.

The current 60 dB action grid is insufficient for part of the long-term case.
A provisional 70 dB grid plus an exact hard-null endpoint is required for the
next local controller rerun. The SA.509 single-entry pattern is retained as a
+3 dB sensitivity.

**Next gate:** `RERUN_LOCAL_CONTROLLERS_WITH_CORRECTED_DUAL_CRITERIA_QMAX70_AND_PATTERN_SENSITIVITY`
<!-- END EESS DUAL CRITERION CORRECTION -->

<!-- BEGIN ONLINE MOVING-AVERAGE PF LOAD TRANSITIONS -->
## Online moving-average PF with deterministic load transitions

Validated one-seed load sequence:

- 118 five-second intervals over the 587-second pass;
- active users per phase: 228, 114, 228, 57, 171, 114;
- four recomputed local-RZF/load states;
- 100-second exponential moving-average PF time constant;
- one-update delay and 3 dB/update mode-attenuation slew.

Results:

- online delayed-myopic 1 dB upper-bound violation seconds:
  `55`;
- online predictive 1 dB violation seconds:
  `0`;
- online predictive 1 dB with two dropped commands:
  `0` violations and
  `2` fail-safe commands;
- online predictive 3 dB violation seconds:
  `0`;
- all predictive active eligible-user floor violations: `0`;
- online 1 dB moving-PF utility: `95.962861771`;
- frozen-table predictive moving-PF utility:
  `95.957091240`;
- static robust moving-PF utility: `95.833441183`.

The saturation statement of the finite-pass theorem is repaired by checking the
actual clipped candidate `F(q)=min(q+rho,Q)` against the next envelope. This
remains one seed, one pass, a deterministic load stress test, and an
uncalibrated uncertainty screen.

**Next gate:** `CALIBRATE_UNCERTAINTY_AND_PREPARE_MULTI_SEED_MULTI_PASS_CAMPAIGN`
<!-- END ONLINE MOVING-AVERAGE PF LOAD TRANSITIONS -->

<!-- BEGIN ROBUST DELAYED SAFETY MILESTONE -->
## Robust delayed-safety theorem and baseline milestone

A finite-pass robust reachability certificate now matches the implemented
predictive filter. It includes known delay, a 3 dB/update per-mode slew limit,
a full-pass geometry envelope, multiplicative coupling bounds, a preloaded
initial action, and a ramp-to-safe message-loss fallback.

One-seed primary results:

- nominal predictive upper-bound violations: `0`;
- 1 dB robust case with two dropped commands: `0` violations and `2` fail-safe commands;
- 3 dB robust upper-bound violations: `0`;
- all robust eligible-user floor violations: `0`;
- virtual-queue gain-1 instantaneous violation seconds:
  `169`;
- 3 dB robust predictive mean PF utility:
  `132.382157793`.

The virtual queue is a long-term baseline and does not provide the hard
instantaneous guarantee. Uncertainty bounds are deterministic smoke-test
bounds, not yet held-out calibrated error models.

**Next gate:** `ONLINE_MOVING_AVERAGE_PF_LOAD_TRANSITIONS_AND_MULTI_SEED_PREP`
<!-- END ROBUST DELAYED SAFETY MILESTONE -->

<!-- BEGIN CONSTRAINED PF CONTROLLER MILESTONE -->
## Constrained proportional-fair controller milestone

Primary frozen scenario:

- update interval: 5 s;
- message/action delay: 1 update;
- attenuation slew: 3 dB/update;
- predictive horizon: 10 updates;
- eligible users: 207;
- coverage-limited users reported separately: 21;
- eligible floor: `max(0.1, 0.9 R_nominal)` bit/s/Hz.

Results:

- delayed-myopic incumbent violation seconds:
  `39`;
- predictive incumbent violation seconds:
  `0`;
- predictive eligible-user floor violations:
  `0`;
- predictive mean PF utility:
  `132.464839322`;
- static-safe mean PF utility:
  `132.263101034`;
- predictive mean eligible-user geometric rate:
  `1.895342143` bit/s/Hz;
- static-safe mean eligible-user geometric rate:
  `1.893494747` bit/s/Hz.

Network sum rate remains secondary. The milestone is one seed and does not yet
provide a formal delayed-safety theorem, virtual-queue baseline, uncertainty
calibration, or statistical paper evidence.

**Next gate:** `FORMALIZE_DELAYED_SAFETY_GUARANTEE_ADD_VIRTUAL_QUEUE_AND_UNCERTAINTY`
<!-- END CONSTRAINED PF CONTROLLER MILESTONE -->

<!-- BEGIN FAIRNESS POLICY AUDIT -->
## Fairness policy frozen before controller implementation

The controller objective is **constrained proportional fairness**, not network
sum rate.

Primary one-seed diagnostic policy:

- nominal serviceability threshold: 0.1 bit/s/Hz;
- eligible users: `207`;
- coverage-limited users: `21`;
- eligible-user floor: `max(0.1 bit/s/Hz, 0.9 R_nominal)`;
- common-scale reference floor violations: `0`;
- primary utility: `sum log(R_u + 0.001)`;
- report total-band/protected-band, absolute outage, fifth percentile, minimum,
  geometric mean, Jain index, and indoor/outdoor groups.

No indoor-specific optimization weight is assigned from the one-seed result,
because the nominal indoor/outdoor ordering is counterintuitive and must be
audited over multiple channel/topology seeds.

**Next gate:** `IMPLEMENT_CONSTRAINED_PROPORTIONAL_FAIR_STATIC_MYOPIC_AND_PREDICTIVE_CONTROLLERS`
<!-- END FAIRNESS POLICY AUDIT -->

<!-- BEGIN VALIDATED FULL-TOPOLOGY EXPORT -->
## Validated controller-ready full-topology export

- Source H100 job: `18696267`
- Corrected CPU validation job: `18704028`
- Full topology: 228 users, 57 sectors, 128 ports, 9 frequencies
- Full response shape: `[228,57,128,9]`
- V4 validation: `PASS`
- Legacy job-18658301 reproduction: bitwise channel hash match
- Minimum total-band common-scale retention: `99.296767%`
- Minimum protected-band common-scale retention: `93.018752%`
- Claim boundary: `CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_ONE_SEED_NOT_PAPER_RESULT`

The full-versus-chunked network sum differs by only about 0.15%, but the
per-user nominal-rate correlation is only about 0.293. This confirms that the
full topology is necessary for user-level controller evaluation.

The exported pass contains a natural delay/slew safety trap, but no practical
predictive controller has yet been demonstrated.

**Next gate:** `IMPLEMENT_LOCAL_STATIC_MYOPIC_AND_PREDICTIVE_CONTROLLERS`
<!-- END VALIDATED FULL-TOPOLOGY EXPORT -->

# Current Project Status

## Status date

2026-07-29

## Status in one sentence

The public/modelled propagation and full-topology platform, constrained-PF predictive controller, finite-pass robust safety certificate, virtual-queue comparison, and deterministic online-PF load-transition milestone have passed as one-seed non-paper evidence. Calibrated uncertainty and the statistical multi-seed/multi-pass campaign remain open.

## Frozen successful gate

- Job: `18658301`
- GPU: NVIDIA H100 80 GB HBM3
- Sectors/users: 57 / 228
- Users per sector: 4
- BS ports: 128
- Frequency samples: 9
- Protected-pass samples: 587
- Minimum network sum-rate retention: `99.149152%`
- Claim boundary: `ONE_SEED_SOFTWARE_AND_PHYSICAL_ACCOUNTING_GATE_NOT_PAPER_RESULT`

## Current gate

`CALIBRATE_UNCERTAINTY_AND_PREPARE_MULTI_SEED_MULTI_PASS_CAMPAIGN`

## Immediate requirements

1. Calibrate coupling, pointing, array, and ephemeris upper errors.
2. Resolve the exact long-term regulatory functional.
3. Independently review the immutable multi-seed campaign package before submission.
4. Add stochastic traffic, layout rotations, O2I, finite-network, and practical-array sensitivity.
5. Run paired multi-seed/multi-pass statistics only after those gates pass.

## Open paper gates

- exact long-term incumbent criterion;
- uncertainty calibration;
- practical array/hybrid sensitivity;
- full-topology spatial correlation;
- rate-limit counterexample;
- controller runtime and message overhead;
- multi-seed, multi-pass confidence intervals.
