
# Current Blocker and Required Next Gate

## Current gate name

`FLOOR_FEASIBILITY_AND_POLICY_REPAIR_BEFORE_CONFIRMATORY_CAMPAIGN`

This supersedes the stale repository prose that still refers generally to
reviewing the deployment-smoke return.

## Frozen fairness rule that failed

Eligibility is determined from full-load nominal total-band rate:

\[
u\ \text{eligible}
\iff R^{\mathrm{nom,full}}_u \ge 0.1\ \text{bit/s/Hz}.
\]

At each load state, every active eligible user is assigned:

\[
R^{\mathrm{floor}}_{u,k}
=
\max\left(0.1,\ 0.9R^{\mathrm{nom,current\ load}}_{u,k}\right).
\]

The diagnostic used a strict rate comparison with only a tiny numerical
comparison tolerance. The observed 2.7% and 18.9% shortfalls are too large to
be explained by floating-point error.

## Required scientific questions

The next AI/scientist must answer these in order.

### 1. Is the existing floor feasible in the frozen action space?

For every affected user/interval, compute exact upper bounds under:

1. nominal no-protection action;
2. protected-mode attenuation only;
3. sector-selective backoff/mute;
4. optimized local RZF/user power redistribution while preserving the same
   architecture and incumbent constraint;
5. optional protected-subband scheduling or reassignment.

Return a feasibility certificate, not a heuristic claim.

### 2. Is the floor reference scientifically appropriate?

Compare, without silently changing the preregistration:

- current rule: 90% of current-load nominal;
- 90% of full-load nominal;
- a moving-average/PF-compatible service guarantee;
- explicit outage/admission classification for truly infeasible users.

Any policy change must be independently justified, frozen, and re-reviewed
before confirmatory execution.

### 3. Is the issue controller-specific?

Use the packaged all-method diagnostic. Predictive is safe and generally has
better floor behavior than static or hard-null, but floor violations occur in
multiple safe methods. Quantify:

- action-space feasibility;
- control/fallback contribution;
- user-specific geometry and channel causes;
- load-phase and final-extension effects.

### 4. What repair should be tested first?

Preferred sequence:

1. add an exact floor-feasibility check to each local action table;
2. make sector-selective fallback lexicographic:
   incumbent safety -> floor feasibility -> normalized shortfall -> PF utility
   -> control variation;
3. add user/stream-aware protected-subband power or scheduling adjustment if
   the existing sector-scale action cannot satisfy the floor;
4. produce an explicit infeasibility certificate when no admissible action
   satisfies both safety and floors;
5. only then consider revising the floor policy.

## Required regression matrix

A repair candidate must be evaluated on:

- preserved excluded Rorqual seed `43999`, all five passes and all eight methods;
- the original validated one-seed/full-topology data in this package;
- corrected long and short EESS criteria;
- multiple-entry primary pattern;
- 65 dB null cap and 3 dB declared uplift;
- exact variable-pass-length load schedule;
- the generic 64T64R architecture.

## Hard gates before another H100 smoke

- predictive long-term safety violations: `0`;
- predictive short-term safety violations: `0`;
- predictive eligible-floor violation user-seconds: `0`, unless an
  independently reviewed policy revision explicitly changes the gate;
- reactive-myopic-with-same-fallback safety violations: `0`;
- no hidden network-wide shutdown;
- all mutes/backoffs reported;
- unchanged immutable source inputs or a clearly versioned candidate-v4 source
  snapshot;
- deterministic engineering assumptions still labelled noncalibrated;
- full 30-seed execution remains locked.

## Recommended compute sequence

1. Local/CPU-only analysis first.
2. Reuse the preserved Rorqual seed-43999 channel whenever it still exists.
3. Build a downloadable versioned repair package with tests and manifests.
4. Run a CPU-only all-five-pass diagnostic.
5. Independently review that result.
6. Only then run a new excluded H100 deployment smoke.
7. Only after smoke PASS prepare/review the full 30-seed orchestrator and token.
