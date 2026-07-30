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

The propagation, incumbent, topology, standards-subset, exact steering, and
distributed DLP-RZF foundations are complete as non-paper evidence. Nibi job
18658301 successfully closed the one-seed 57-sector, 228-user software and
physical-accounting gate with zero local budget violations and zero projection
power-increase violations. The dynamic delayed/rate-limited controller and
paper-grade statistical campaign remain open.

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

`FORMALIZE_DELAYED_SAFETY_GUARANTEE_ADD_VIRTUAL_QUEUE_AND_UNCERTAINTY`

## Immediate requirements

1. Formalize the delayed/reachability safety guarantee.
2. Add the virtual-queue baseline under the same fairness and actuation rules.
3. Add uncertainty, message age, and an explicit fail-safe.
4. Quantify frozen local-cost-table approximation error.
5. Expand the controller grid before any multi-seed campaign.
## Open paper gates

- exact long-term incumbent criterion;
- uncertainty calibration;
- practical array/hybrid sensitivity;
- full-topology spatial correlation;
- rate-limit counterexample;
- controller runtime and message overhead;
- multi-seed, multi-pass confidence intervals.
