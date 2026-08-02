# Candidate-v4.3 failed-seed feasibility diagnosis

This package performs the next major scientific gate after the 30-seed Rorqual
campaign. It does **not** rerun the campaign and does not regenerate channels.
It reuses the eleven preserved failed-seed channels and determines whether the
remaining floor failures are caused by the bounded two-neighbour distributed
action scope or by fixed-mode/fixed-beam physical infeasibility.

The candidate-v4.3 source, floor, EESS limits, 65/3 dB modes, fixed RZF beams,
and scientific tolerances remain frozen. The diagnostic performs:

1. exact reproduction of every failed seed;
2. strict global fixed-beam stream-power feasibility under every sector's
   post-mode power budget;
3. independent HiGHS dual-simplex and interior-point feasibility cross-checks;
4. expanded local hybrid and all-stream scopes with four or eight dominant
   external sectors per violated user;
5. optimistic single-user bounds when global fixed-beam infeasibility is
   solver-certified.

Only the eleven failed campaign seeds are processed. The jobs are CPU-only on
Rorqual. Workers request 15 minutes and 16 GiB; the merge requests 5 minutes
and 8 GiB. The original four-hour campaign request is not reused.
