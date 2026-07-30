# Next Immediate Step

## Gate

`FORMALIZE_DELAYED_SAFETY_GUARANTEE_ADD_VIRTUAL_QUEUE_AND_UNCERTAINTY`

## Required sequence

1. State and prove the finite-horizon delayed/reachability safety condition matching the implemented predictive filter, including initialization, forecast error, delay, and slew limits.
2. Add a virtual-queue/Lyapunov baseline under the same information, delay, slew, service-floor, and uncertainty conditions.
3. Add coupling-error and message-age uncertainty with an explicit local fail-safe and no hidden slack.
4. Replace frozen nominal local action-cost tables with online local moving-average PF cost updates, or quantify their approximation gap.
5. Expand the delay/slew/update grid and produce the primary safety-fairness ablation figures.
6. Only after these gates pass, launch multi-seed and multi-pass experiments.
