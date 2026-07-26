import numpy as np

from fr3_cbf.calibration import evaluate_split_conformal, split_conformal_quantile, wilson_interval


def test_split_conformal_quantile_is_finite_and_conservative_rank():
    scores = np.arange(1, 101, dtype=float)
    q = split_conformal_quantile(scores, alpha=0.05)
    assert q == 96.0


def test_evaluate_split_conformal():
    cal = np.arange(1, 101, dtype=float)
    test = np.array([1.0, 95.0, 97.0])
    result = evaluate_split_conformal(cal, test, alpha=0.05)
    assert result.quantile == 96.0
    assert result.covered_count == 2
    assert result.empirical_coverage == 2 / 3


def test_wilson_interval_contains_observed_fraction():
    lo, hi = wilson_interval(95, 100)
    assert lo < 0.95 < hi
