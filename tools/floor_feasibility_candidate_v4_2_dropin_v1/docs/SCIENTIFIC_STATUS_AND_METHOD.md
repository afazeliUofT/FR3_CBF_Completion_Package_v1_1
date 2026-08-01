# Scientific status and method

## Source-supported facts

The frozen eligibility rule is full-load nominal total-band rate at least
`0.1 bit/s/Hz`. For each active eligible user, the interval floor is
`max(0.1, 0.9 * current-load nominal total-band rate)`.

The excluded seed-43999 predictive trace has zero long- and short-term EESS
violations but 519 floor-violation user-seconds, 104 floor-violation
user-intervals, minimum floor ratio `0.810696983385736`, and maximum normalized
shortfall `0.18930301661426396`. Only two physical users are affected:

- `E3_SITE_02_SEC_3_UE_4`: 500 violating seconds in all five passes; minimum
  ratio `0.9724542726228104`;
- `E3_SITE_07_SEC_1_UE_2`: 19 seconds in the final two pass extensions; minimum
  ratio `0.810696983385736`; its failing floor branch is the absolute `0.1`
  floor.

Across the packaged five-pass diagnostic, the comparable aggregate results are:

| Method | Long/short EESS violation seconds | Floor user-seconds | Floor user-intervals |
|---|---:|---:|---:|
| Predictive + sector fallback | 0 / 0 | 519 | 104 |
| Safe static + sector fallback | 0 / 0 | 1519 | 304 |
| Reactive myopic + same fallback | 0 / 0 | 559 | 112 |
| Uniform protected-tone backoff | 0 / 0 | 539 | 108 |
| Hard spatial null / exact mute | 0 / 0 | 12867 | 2625 |
| Noncausal common-scale reference | 0 / 0 | 1519 | 304 |

The reviewed fallback builds each sector's cost from its own four served users
and coordinates sectors through an incumbent-interference price. It does not
impose the coupled network-wide user floors during action selection. Its one
sector scalar also scales all four protected streams together.

## Scientific inference

The persistent approximately 2.7% deficit of `E3_SITE_02_SEC_3_UE_4` is not a
numerical-tolerance effect. Its repeatability across all five passes is
consistent with a structural action/coordination defect: the serving-sector
scalar cannot alter the desired-to-same-sector-stream interference balance,
and the incumbent-only price does not price the floor harm created by dominant
external sectors.

The approximately 81.07% terminal ratio of `E3_SITE_07_SEC_1_UE_2` is a
separate low-rate extension case on the absolute floor. It requires either
concentrating available fixed-RZF stream power, suppressing a small number of
external/EESS contributors, or a fixed-action-class infeasibility/admission
certificate. The preserved-channel run computes all three decompositions
(no protection, frozen mode only, and fallback/repair) before assigning the
interval-level root-cause class.

The packaged method comparison supports this diagnosis: EESS-safe common
scaling, static protection, uniform backoff, and even the noncausal common-scale
reference do not solve the floor. Hard null/mute greatly worsens fairness. The
predictive method is the best reviewed safety/fairness compromise but still
lacks a hard coupled-floor feasibility layer.

## Exact candidate formulation

For fixed modes and fixed beam directions, requiring protected-subband rate
`r_req` gives `gamma = 2^(r_req/w_p)-1`, and the floor is equivalent to

`gamma * (interference + noise) - desired <= 0`.

Each physical-second EESS ratio is linear in the same stream-power scales.
Candidate v4.2 applies this lexicographic hierarchy:

1. sequential reviewed distributed fallback;
2. bounded sparse local frozen-grid sector repair;
3. bounded critical-serving-sector fixed-RZF stream redistribution plus sparse
   external/EESS backoff;
4. global continuous-sector, global frozen-grid, and global fixed-beam-stream
   feasibility oracles for classification only;
5. an optimistic single-user EESS-safe upper bound when the deployable class is
   infeasible or unresolved.

For a critical sector `b`, actual candidate conducted power is constrained by

`sum_k P_q,bk x_bk <= s_b sum_k P_0,bk`.

This uses actual post-mode power on the left and the original `q=0` nominal
conducted-power envelope on the right. It permits redistribution of power made
available by mode attenuation without changing the 65/3 dB beam command, and
still subjects every candidate to exact long/short EESS verification. The
stricter `s_b sum_k P_q,bk` row is reported as a diagnostic comparator.

## Assumptions requiring validation

The immediate Rorqual run must establish whether every violating interval is
feasible under this bounded local action class. The interpretation of the
`q=0` nominal envelope as available conducted power, per-stream update latency,
signalling, PA/RF-chain constraints beyond total conducted power, and fixed-RZF
reweighting support require engineering validation before deployment claims.
No calibration or regulatory-compliance claim is made.
