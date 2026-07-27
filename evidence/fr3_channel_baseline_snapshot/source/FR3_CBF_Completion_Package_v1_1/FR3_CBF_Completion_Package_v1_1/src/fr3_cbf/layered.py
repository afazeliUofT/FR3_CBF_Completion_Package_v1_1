from __future__ import annotations

import numpy as np


def proportional_sector_budgets(nominal_contributions: np.ndarray, total_allowances: np.ndarray) -> np.ndarray:
    """Allocate each incumbent allowance across sectors without exceeding the total.

    nominal_contributions has shape [L,B] and must be nonnegative. The returned budget
    has the same shape and each row sums to the corresponding total allowance.
    """
    contrib = np.asarray(nominal_contributions, dtype=float)
    allowance = np.asarray(total_allowances, dtype=float)
    if contrib.ndim != 2 or allowance.shape != (contrib.shape[0],):
        raise ValueError("Expected contributions [L,B] and allowances [L]")
    if np.any(contrib < 0) or np.any(allowance < 0):
        raise ValueError("Contributions and allowances must be nonnegative")
    out = np.zeros_like(contrib)
    for l in range(contrib.shape[0]):
        total = contrib[l].sum()
        if total > 0:
            out[l] = allowance[l] * contrib[l] / total
        else:
            out[l] = allowance[l] / contrib.shape[1]
    return out


def verify_sector_budgets(budgets: np.ndarray, total_allowances: np.ndarray, tolerance: float = 1e-10) -> None:
    budgets = np.asarray(budgets, dtype=float)
    allowances = np.asarray(total_allowances, dtype=float)
    if np.any(budgets < -tolerance):
        raise ValueError("Negative sector budget")
    if np.any(budgets.sum(axis=1) > allowances + tolerance):
        raise ValueError("Sector budgets exceed aggregate allowance")
