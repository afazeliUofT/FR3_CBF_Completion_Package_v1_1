# FR3 Candidate v4.2 — Floor/EESS Feasibility Repair

## Purpose

This standalone drop-in advances the excluded seed-43999 diagnostic without
modifying the immutable reviewed phase-1 package, the user-floor policy, or
either EESS gate. It does not authorize confirmatory seeds 44000--44029.

## Substantial result

At fixed protected-mode commands and fixed RZF beam directions, every active
eligible-user floor is exactly equivalent to a linear SINR inequality in
protected-stream power scales. The physical-second long- and short-term EESS
constraints are linear in the same variables. Candidate v4.2 therefore returns
an exact feasible witness, a class-specific infeasibility certificate, or an
explicit unresolved result; it never hides failure by changing a tolerance.

A pre-release implementation incorrectly constrained redistribution to the
already mode-attenuated fallback power, effectively charging the 65/3 dB mode
attenuation twice. Candidate v4.2 corrects the physical power row to

`sum_k P_q,bk x_bk <= s_b sum_k P_0,bk`,

where `P_q,bk` is actual post-mode conducted stream power, `P_0,bk` is the
original `q=0` nominal conducted stream power, and `s_b` is the reviewed
fallback sector scalar. The stricter post-mode row is retained only as a
reported comparator. The fixed 65/3 dB command, beam directions, floor, EESS
constraints, and numerical gates remain unchanged.

The selected deployable action is limited to:

- serving sectors of currently floor-violating users;
- at most two dominant external interferers per violating user;
- at most two dominant EESS contributors;
- all other sectors frozen at the sequential reviewed fallback action.

Global LP/MILP solves are diagnostic oracles only. Hard floor/EESS feasibility
is primary; minimum weighted L1 action deviation is secondary. Sum rate is not
the primary objective.

## Current status and distance from a strong TWC paper

The package locally reproduces the floor definition, eligibility rule, five
variable-length passes, all eight reviewed methods, and the material seed-43999
failure. It passes 16 focused regressions, deterministic randomized algebraic
checks, and an original validated full-topology regression using the real
128-port protected precoder. Both frozen 65/3 dB orientations satisfy the
`q=0` physical envelope on that archived topology.

A strong TWC paper has **not** yet been reached. The immediate missing result is
the CPU-only exact run on Rorqual against the preserved raw seed-43999 channel.
A pass would be one excluded diagnostic witness, not confirmatory evidence.
Independent review, a separate excluded deployment smoke, the preregistered
30-seed campaign, statistical analysis, ablations/complexity, and manuscript
integration would remain.

## Exact next gate

Run the one-block WSL command supplied with this release. It verifies the frozen
ZIP, runs all local gates, stages source in an isolated clean Git clone, pushes
without force, reuses the preserved Rorqual channel, submits a CPU-only Slurm
job, retrieves a compact return even on scientific failure, and pushes
reviewable text evidence to

`evidence/phase1_floor_feasibility_candidate_v4_2_dropin_v1`.

The user's current repository working tree is not used for staging and is not
overwritten.
