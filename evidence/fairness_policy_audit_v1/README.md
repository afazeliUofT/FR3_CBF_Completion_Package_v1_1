# Fairness policy audit

The primary controller objective is constrained proportional fairness, not network sum rate. Users below the declared nominal serviceability threshold are reported as coverage-limited; they are not hidden inside the controller objective. For eligible users, the controller must first avoid service-floor violations and shortfall, then maximize PF utility. Indoor and outdoor users are reported separately, but no indoor-specific weight is assigned from this one seed.
