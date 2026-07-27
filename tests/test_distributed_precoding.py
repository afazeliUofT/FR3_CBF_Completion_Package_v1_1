from __future__ import annotations

import numpy as np

from fr3_cbf.distributed_precoding import (
    leakage_power_w,
    local_rzf_precoder,
    project_precoder_to_leakage_budget,
    proportional_received_interference_budgets,
    upa_steering_vector,
)


def test_local_rzf_power():
    rng = np.random.default_rng(1)
    h = rng.normal(size=(16, 4)) + 1j * rng.normal(size=(16, 4))
    w = local_rzf_precoder(h, power_limit_w=2.5, regularization=0.1)
    assert abs(np.vdot(w, w).real - 2.5) < 1e-11


def test_closed_form_projection_exact_and_power_nonincrease():
    rng = np.random.default_rng(2)
    w = rng.normal(size=(12, 3)) + 1j * rng.normal(size=(12, 3))
    a = rng.normal(size=12) + 1j * rng.normal(size=12)
    initial = leakage_power_w(w, a)
    target = 0.2 * initial
    result = project_precoder_to_leakage_budget(w, a, target)
    assert result.active
    assert abs(result.safe_leakage_w - target) <= 1e-10 * max(1.0, target)
    assert result.power_after_w <= result.power_before_w + 1e-11
    assert abs(result.projection_scale - np.sqrt(0.2)) < 1e-12


def test_inactive_projection_is_identity():
    rng = np.random.default_rng(3)
    w = rng.normal(size=(8, 2)) + 1j * rng.normal(size=(8, 2))
    a = rng.normal(size=8) + 1j * rng.normal(size=8)
    current = leakage_power_w(w, a)
    result = project_precoder_to_leakage_budget(w, a, 2.0 * current)
    assert not result.active
    assert np.allclose(result.precoder, w)


def test_certified_budget_sum():
    nominal = np.array([1.0, 2.0, 7.0])
    budgets = proportional_received_interference_budgets(
        nominal, aggregate_threshold_w=5.0, reserve_fraction=0.1
    )
    assert np.all(budgets >= 0)
    assert abs(budgets.sum() - 4.5) < 1e-14
    assert np.allclose(budgets / budgets.sum(), nominal / nominal.sum())


def test_upa_array_factor_convention():
    a = upa_steering_vector(4, 8, 0.0, 0.0, normalize=False)
    assert a.shape == (32,)
    assert abs(np.vdot(a, a).real - 32.0) < 1e-12
