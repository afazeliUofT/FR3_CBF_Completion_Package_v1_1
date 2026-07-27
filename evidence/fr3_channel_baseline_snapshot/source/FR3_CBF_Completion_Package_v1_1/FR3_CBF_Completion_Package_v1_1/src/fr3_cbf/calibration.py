from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CalibrationResult:
    quantile: float
    calibration_size: int
    test_size: int
    empirical_coverage: float
    target_coverage: float
    covered_count: int


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("Invalid binomial counts")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0,1)")
    from scipy.stats import norm

    z = float(norm.ppf(0.5 + confidence / 2.0))
    p = successes / trials
    den = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / den
    half = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / den
    return max(0.0, center - half), min(1.0, center + half)


def split_conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    scores = np.asarray(scores, dtype=float)
    scores = scores[np.isfinite(scores)]
    if scores.size == 0:
        raise ValueError("No finite calibration scores")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0,1)")
    rank = min(scores.size, math.ceil((scores.size + 1) * (1.0 - alpha)))
    return float(np.partition(scores, rank - 1)[rank - 1])


def evaluate_split_conformal(cal_scores: np.ndarray, test_scores: np.ndarray, alpha: float) -> CalibrationResult:
    q = split_conformal_quantile(cal_scores, alpha)
    test = np.asarray(test_scores, dtype=float)
    test = test[np.isfinite(test)]
    if test.size == 0:
        raise ValueError("No finite test scores")
    covered = int(np.sum(test <= q))
    coverage = covered / int(test.size)
    return CalibrationResult(q, int(np.isfinite(cal_scores).sum()), int(test.size), float(coverage), 1.0 - alpha, covered)
