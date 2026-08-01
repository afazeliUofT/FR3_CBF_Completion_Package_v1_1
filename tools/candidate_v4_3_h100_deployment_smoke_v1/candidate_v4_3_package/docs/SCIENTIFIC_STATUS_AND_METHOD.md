# Scientific status and method

## Source-supported status

The v4.2 Rorqual run used the preserved seed-43999 channel and reproduced the
reviewed predictive trace: zero long/short EESS violations, 519 floor-violation
user-seconds, and 104 violating user-intervals. V4.2 repaired every one of the
104 original affected intervals. The remaining 16 candidate violations were
new boundary residuals with maximum normalized shortfall
`2.419707002352053e-10`.

The v4.2 strict post-mode stream comparator was feasible in all 98 intervals
that required stream redistribution. Hence the nine actions that used broader
`q=0` headroom were unnecessary.

## Root cause

`E3_SITE_02_SEC_3_UE_4` is persistently constrained by same-sector fixed-RZF
stream competition. A common sector scalar cannot transfer protected-tone
power among streams, so it cannot close the approximately 2.7 percent worst
relative-floor deficit.

`E3_SITE_07_SEC_1_UE_2` is on the absolute 0.1 b/s/Hz branch in the terminal
extension. Its current-load nominal rate is below 0.1, and its deficit is
external-interference dominated. Sparse external-sector backoff provided a
feasible witness in all four affected user-intervals, so admission-policy
revision is not yet justified.

## V4.3 method

V4.3 keeps the floor and EESS audit unchanged and tightens only the numerical
witness-recovery problem. Every active hard inequality is row-normalized and
its right-hand side is reduced by `1e-8`. HiGHS primal/dual tolerances are
`1e-9`; a solution is deployable only when its original normalized constraints
retain at least a `5e-9` interior margin.

The selected stream action must satisfy the strict post-mode sector budget.
The broader `q=0` envelope remains an oracle and is never selected. Every
candidate is then recomputed through the exact nonlinear rate equations and
physical-second long/short EESS audit.

A fixed-reserve LP failure means only that no certified interior witness was
found at that reserve. It is not promoted to an infeasibility proof for the
untightened physical action class.

## Claim boundary

Seed 43999 is excluded diagnostic evidence only. A v4.3 pass cannot authorize
the confirmatory campaign. It advances the work to independent review and a
separate excluded H100 deployment smoke.
