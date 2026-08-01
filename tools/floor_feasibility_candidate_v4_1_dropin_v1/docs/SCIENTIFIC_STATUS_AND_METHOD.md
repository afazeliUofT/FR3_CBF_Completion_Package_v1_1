# Scientific status and method

## Source-supported facts

The frozen active-user floor is
`max(0.1, 0.9 * current-load nominal total-band rate)` for users whose full-load
nominal total-band rate is at least `0.1 bit/s/Hz`. The excluded seed-43999
predictive trace has zero long- and short-term EESS violations but 519
floor-violation user-seconds, 104 floor-violation user-intervals, minimum floor
ratio `0.810696983385736`, and maximum normalized shortfall
`0.18930301661426396`. Only `E3_SITE_02_SEC_3_UE_4` (500 user-seconds) and
`E3_SITE_07_SEC_1_UE_2` (19 user-seconds) are affected.

The reviewed fallback constructs each sector’s local cost from that sector’s
served users and coordinates sectors through an incumbent-interference price.
It does not impose coupled network-wide user floors during action selection.
A sector scalar also scales all four protected streams together.

## Scientific inference

The persistent approximately 2.7% shortfall of `E3_SITE_02_SEC_3_UE_4` is a
systematic allocation defect consistent with unpriced cross-sector floor
coupling and/or same-sector stream imbalance. The terminal 81.07% ratio of
`E3_SITE_07_SEC_1_UE_2` is a distinct low-rate extension case on the absolute
0.1 floor and may require concentrated stream power or a fixed-class
infeasibility/admission certificate.

## Exact formulation

For fixed modes and beam directions, the floor condition is equivalent to a
linear inequality of the form

`gamma * (interference + noise) - desired <= 0`,

where `gamma` is obtained exactly from the required protected-subband rate.
Each physical-second EESS ratio is linear in the same stream-power scales.
Candidate v4.1 therefore implements:

1. a global continuous sector-scale LP feasibility oracle;
2. a bounded sparse local frozen-grid MILP repair, including up to two
   EESS-headroom contributors selected from violated or most-binding stressed
   physical-second rows;
3. a global frozen-grid MILP oracle when needed;
4. a bounded local fixed-RZF stream-power LP with serving-sector power budgets;
5. a global fixed-beam stream-power LP oracle;
6. an all-other-streams-muted EESS-safe single-user upper bound.

The selected repair is lexicographic: hard floors and both EESS criteria first,
then minimum action deviation. No sum-rate primary objective is used.

## Assumptions requiring validation

The preserved raw channel must be used on Rorqual to determine which action
class is feasible for every affected interval. Practical latency, signalling,
and support for per-stream RZF reweighting require later deployment validation.
No calibration or regulatory-compliance claim is made.
