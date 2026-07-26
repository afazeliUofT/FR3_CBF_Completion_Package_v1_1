import numpy as np

from fr3_cbf.layered import proportional_sector_budgets, verify_sector_budgets


def test_proportional_sector_budgets_sum_to_allowance():
    contrib = np.array([[1.0, 3.0], [0.0, 0.0]])
    allowance = np.array([8.0, 6.0])
    budgets = proportional_sector_budgets(contrib, allowance)
    assert np.allclose(budgets.sum(axis=1), allowance)
    assert np.allclose(budgets[0], [2.0, 6.0])
    assert np.allclose(budgets[1], [3.0, 3.0])
    verify_sector_budgets(budgets, allowance)
