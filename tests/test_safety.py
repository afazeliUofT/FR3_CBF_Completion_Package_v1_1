from fr3_cbf.safety import EMAMarginGovernor, ExceedanceBudget, cbf_scale


def test_exceedance_budget_prefix_bound():
    budget = ExceedanceBudget(allowed_fraction=0.2, maximum_balance=1.0)
    exceedances = 0
    for _ in range(20):
        take = budget.can_exceed()
        budget.update(take)
        exceedances += int(take)
        assert exceedances <= 0.2 * (_ + 1) + 1e-12


def test_ema_allowance_keeps_margin():
    g = EMAMarginGovernor(threshold=1.0, alpha=0.1, gamma=0.2, reserve=0.05, state=0.7)
    allowance = g.allowance()
    assert allowance >= 0
    g.update(allowance)
    assert g.state <= 1.0 + 1e-12


def test_cbf_scale_bounded():
    q = cbf_scale(1.0, 1.0, 1.25, 1.0, 0.1, 0.0)
    assert 0.9 <= q <= 1.0
