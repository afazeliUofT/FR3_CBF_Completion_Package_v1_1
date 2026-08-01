# FR3 Candidate v4.3 — Certified-Interior Floor/EESS Repair

## Purpose

This standalone drop-in advances the excluded seed-43999 diagnostic without
modifying the immutable reviewed phase-1 package, the fairness policy, or either
EESS gate. It does not authorize confirmatory seeds 44000--44029.

## Evidence motivating v4.3

Candidate v4.2 reproduced the reviewed 519 floor-violation user-seconds and 104
violating user-intervals, then repaired all 104 original affected intervals
while preserving zero long- and short-term EESS violations. Its reported
failure consisted of 16 newly introduced one-user boundary misses, totalling 80
user-seconds, with maximum normalized shortfall only
`2.419707002352053e-10`.

All 98 v4.2 stream-repair intervals also had a feasible stricter post-mode
power-budget comparator. Therefore the broader `q=0` power headroom is neither
needed nor selected in v4.3.

## Scientific correction

Candidate v4.3 retains the exact audit thresholds:

- floor comparison tolerance: `1e-12`;
- EESS verification tolerance: `1e-10`.

It does **not** raise either tolerance. Instead, it requires the LP to return an
interior witness by:

- row-normalizing every hard linear inequality;
- tightening each active normalized inequality by `1e-8`;
- setting HiGHS primal and dual feasibility tolerances to `1e-9`;
- certifying a normalized margin of at least `5e-9` before a stream action is
  considered deployable.

The deployable stream action obeys the conservative physical row

`sum_k P_q,bk x_bk <= s_b sum_k P_q,bk`,

where `P_q,bk` is actual post-mode conducted stream power and `s_b` is the
reviewed fallback sector scale. The broader `q=0` envelope is computed only as
a diagnostic oracle and can never be deployed.

The action remains bounded to serving sectors of currently violating users,
at most two dominant external interferers per violating user, and at most two
EESS contributors. All other sectors remain frozen. Fixed 65/3 dB mode commands
and fixed RZF directions are preserved. Hard floor/EESS feasibility is primary;
minimum weighted L1 action movement is secondary; sum rate is not primary.

## Current status and next gate

The package passes local syntax, 18 focused regressions, deterministic
randomized algebraic checks, the original validated full-topology regression,
and a source-bound audit of the v4.2 return. The only missing result is the
CPU-only Rorqual rerun on the preserved seed-43999 channel.

A v4.3 pass would be a substantial excluded-smoke repair result, not
confirmatory evidence. The next gate would be independent review followed by a
separate excluded H100 deployment smoke. Only after that may authorization of
the 30-seed campaign be reconsidered.
