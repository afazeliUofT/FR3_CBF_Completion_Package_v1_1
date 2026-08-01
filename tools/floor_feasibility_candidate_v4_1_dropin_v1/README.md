# FR3 Candidate v4.1 — Bounded Floor/EESS Feasibility Repair

## Purpose

This standalone drop-in advances the excluded seed-43999 diagnostic without
changing the immutable reviewed phase-1 package, the fairness floor, or either
EESS gate. It does not authorize confirmatory seeds 44000--44029.

## Substantial result

At fixed protected-mode commands and fixed RZF beam directions, every active
eligible-user floor can be written exactly as a linear SINR inequality in
protected-stream power scales. The long- and short-term EESS constraints are
also exact linear inequalities at every physical second. Candidate v4.1 uses
these facts to produce a feasible witness or a class-specific infeasibility or
unresolved certificate rather than hiding the failure with a tolerance change.

The selected deployable action is strictly bounded to:

- serving sectors of currently floor-violating users;
- at most two dominant external interferers per violating user;
- at most two dominant EESS contributors in violated or most-binding
  serving-sector-stressed physical-second rows;
- all other sectors frozen at the sequential reviewed fallback action.

Global LP/MILP solves are diagnostic oracles only. Sum rate is never the primary
objective. The secondary objective is minimum weighted L1 deviation from the
reviewed fallback after all hard floor and EESS constraints are imposed.

## Current status and distance from a strong TWC paper

The floor definition, eligibility, all five variable-length passes, all eight
reviewed methods, and the material seed-43999 failure are locally reproduced.
The original validated full-topology export passes a source-bound no-op and
compatibility regression. The mathematical implementation passes focused and
randomized exact-equivalence tests.

A strong TWC paper has **not** yet been reached. The immediate missing result is
the CPU-only run on Rorqual against the preserved raw seed-43999 channel. A
successful excluded smoke would establish one repaired diagnostic witness, not
confirmatory statistics. Independent review, a separate excluded deployment
smoke, the preregistered 30-seed campaign, statistical analysis/ablations, and
manuscript integration would still remain.

## Exact next gate

Run the single WSL drop-in. It performs local tests first, stages source in an
isolated clean Git clone, pushes normally without force, reuses the preserved
Rorqual channel, submits a CPU-only Slurm job, retrieves a compact ZIP even on
failure, and pushes reviewable text evidence to:

`evidence/phase1_floor_feasibility_candidate_v4_1_dropin_v1`

The user’s existing repository working tree is not modified.
