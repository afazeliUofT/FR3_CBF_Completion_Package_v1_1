# Independent scientific verdict on candidate v4.3

## Verdict

**PASS to one excluded H100-node deployment smoke.** Candidate v4.3 removes the material seed-43999 fairness failure without changing the floor, increasing its verification tolerance, using q=0 headroom, introducing network-wide shutdowns, or violating either EESS criterion.

## Reconstructed hard results

- 5 passes, 590 control intervals, 2,938 physical seconds;
- reviewed predictive trace reproduced at 519 violating user-seconds and 104 violating user-intervals;
- candidate trace: zero floor violations and zero long/short EESS violations;
- 486 no-op intervals, 6 sparse local frozen-grid repairs, and 98 sparse fixed-RZF stream-power repairs;
- 104 repaired intervals covering exactly 519 physical seconds;
- maximum mutable sectors: 5; maximum actually changed sectors: 4;
- strict local action-scope gate: PASS;
- strict post-mode selected-power gate: PASS;
- q=0 envelope deployable actions: 0;
- minimum achieved/floor ratio: `1.0000000004430856`.

## Utility

Relative to the reviewed predictive controller, the five-pass mean final PF change is `-0.0123082`, while the duration-weighted PF change is `+0.00407748`. Candidate v4.3 exceeds safe-static duration-weighted PF in every pass. The repair therefore closes the hard floor defect at negligible utility cost on this excluded seed.

## Interpretation

The floor is feasible on the originally failing intervals under frozen modes, fixed RZF directions, strict post-mode power, and bounded sparse actions. The persistent Site-02 failure is primarily a same-sector stream-balance defect that common sector scaling cannot fix; the Site-07 terminal failure is repaired by sparse local backoff. A fairness-policy revision is not warranted.

## Remaining risk

The next smoke must verify the original Rorqual H100 deployment environment and exact replay from the immutable channel. Action-scope locality is established, but the sufficiency and overhead of the exchanged floor/interference information, controller latency, RF/PA/EVM effects, and multi-seed generalization remain open paper gates.
