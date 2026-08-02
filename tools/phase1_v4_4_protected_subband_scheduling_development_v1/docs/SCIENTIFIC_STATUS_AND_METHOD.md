# Scientific status and method

## Diagnosis

The complete 11-seed diagnosis contains 1,736 unresolved v4.3 intervals. 1,284
are jointly infeasible under global fixed-q/fixed-RZF stream-power control, 182
are feasible only in the global fixed-beam class, 108 are solver-uncertified,
and 162 are already certifiable under an expanded local fixed-beam class. No
affected user is individually fixed-beam infeasible. The conservative sum of
isolated protected-resource demand is below 0.415 in every interval. These facts
do not prove a deployable schedule, but they rule out further fixed-beam power
redistribution as a complete solution and identify scheduling as the minimal
scientifically justified next degree of freedom.

## Candidate v4.4 development action

Candidate v4.3 remains the first hierarchy. Scheduling is invoked only after
`NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND`. The protected subband is time-shared over
2,000 physical 0.5-ms NR slots per second, with the same schedule repeated in
each physical second of the control interval. q commands and RZF directions are
frozen. Critical sectors are the serving sectors of the current floor-deficit
users; each can use baseline, one singleton per deficit stream, full-active, or
mute. One fixed total set of 0, 2, or at most 4 external/EESS guard sectors may
be muted in nonbaseline modes. An 8-guard oracle is diagnostic only.

A continuous floor-first LP constrains every active eligible-user floor and
every physical-second long/short EESS row. The solution is quantized by largest
remainder to exactly 2,000 slots; if the unchanged exact audit fails, a bounded
integer master is used. Every mode has stream coefficients in [0,1], so total
sector and per-RF-chain conducted-power sums remain below the full post-mode
envelope. Minimum intervention is secondary; sum rate is not the primary
objective.

Solver reserves of 5e-4 bit/s/Hz and 1e-6 normalized EESS are constraint
tightenings. The scientific floor and EESS acceptance tolerances remain
unchanged.

## Claim boundary

This is post-campaign development on 11 observed failures, not fresh
confirmation, calibration, or regulatory compliance. Information-exchange
locality, serialized signalling, and PA/EVM effects remain one compact
practicality study. If all 11 seeds pass within the four-guard scope, freeze
v4.4 and begin the TWC draft immediately while fresh seeds 44030-44059 run as a
holdout.
