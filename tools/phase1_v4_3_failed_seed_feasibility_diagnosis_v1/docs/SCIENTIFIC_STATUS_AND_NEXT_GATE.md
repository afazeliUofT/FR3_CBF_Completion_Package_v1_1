# Scientific status and next gate

The 30-seed Rorqual campaign is complete and scientifically informative.
Candidate v4.3 has zero long- and short-term EESS violations, passes strict
locality and strict post-mode power gates, and provides a positive final PF
utility effect versus safe static: 0.28850 with a seed-cluster bootstrap 95%
interval [0.24164, 0.33858]. It also reduces floor-violation user-seconds by
77.93% relative to the reviewed predictive method and 81.11% relative to safe
static.

The unchanged hard floor is not yet general across the campaign: 19/30 seeds
pass all hard gates, while eleven seeds contain 1,736 unresolved intervals and
19,994 floor-violation user-seconds. These are scientific action-space failures,
not infrastructure failures.

The next major gate reuses those eleven preserved channels and determines
whether the remaining intervals are feasible with a minimally expanded local
fixed-beam action, feasible only with broader coordination, or infeasible even
under global fixed-beam stream-power control. This directly selects candidate
v4.4; it does not regenerate channels or rerun the 30-seed campaign.

If the diagnosis causes any candidate-v4.4 source change, the current 30 seeds
become development/stress-test data for that revised candidate. A fresh,
preregistered holdout is then required for the final v4.4 generalization claim.
This is a major scientific requirement, not an optional audit.
