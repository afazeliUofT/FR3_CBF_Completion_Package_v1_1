# Constrained proportional-fair controller milestone

Run only:

```bash
bash RUN_CONSTRAINED_PF_CONTROLLER_MILESTONE_DROPIN.sh
```

This local-only milestone uses the validated 228-user full-topology dataset and
the frozen fairness policy from commit `2ca450f`.

The optimization priority is:

1. incumbent safety;
2. eligible-user service-floor violations;
3. normalized service-floor shortfall;
4. eligible-user proportional-fair utility;
5. control variation.

The 21 nominally coverage-limited users are reported separately. All methods
are evaluated with total-band and protected-band rates, PF utility, geometric
mean, fifth percentile, minimum rate, Jain index, indoor/outdoor groups, and
explicit floor violations. Network sum rate is secondary.

The predictive method is a one-seed finite-horizon reachability prototype, not
yet a formally proved CBF or a paper result. No cluster job is submitted.

Do not run the older `FR3_CBF_v1_1_Local_UtilityAware_Controller_Milestone_DropIn_v1.zip`; it does not enforce the frozen eligible-user service-floor policy.
