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
