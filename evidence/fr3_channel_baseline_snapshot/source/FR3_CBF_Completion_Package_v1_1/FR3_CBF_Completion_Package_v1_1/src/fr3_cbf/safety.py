from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def bounded_move(target: float, previous: float, max_change: float, lower: float = 0.0, upper: float = 1.0) -> float:
    if max_change < 0:
        raise ValueError("max_change must be nonnegative")
    return float(np.clip(target, max(lower, previous - max_change), min(upper, previous + max_change)))


@dataclass
class ExceedanceBudget:
    allowed_fraction: float
    balance: float = 0.0
    maximum_balance: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.allowed_fraction <= 1.0:
            raise ValueError("allowed_fraction must be in [0, 1]")
        if self.maximum_balance <= 0:
            raise ValueError("maximum_balance must be positive")

    def can_exceed(self) -> bool:
        return self.balance + self.allowed_fraction >= 1.0 - 1e-12

    def update(self, exceeded: bool) -> float:
        e = 1.0 if exceeded else 0.0
        if e > self.balance + self.allowed_fraction + 1e-12:
            raise ValueError("Exceedance would violate the prefix budget")
        self.balance = min(self.maximum_balance, self.balance + self.allowed_fraction - e)
        return self.balance


@dataclass
class EMAMarginGovernor:
    threshold: float
    alpha: float
    gamma: float
    reserve: float = 0.0
    state: float = 0.0

    def __post_init__(self) -> None:
        if self.threshold <= 0:
            raise ValueError("threshold must be positive")
        if not 0.0 < self.alpha <= 1.0:
            raise ValueError("alpha must be in (0,1]")
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must be in [0,1]")
        if self.reserve < 0:
            raise ValueError("reserve must be nonnegative")

    @property
    def margin(self) -> float:
        return self.threshold - self.state

    def allowance(self) -> float:
        target_margin = max((1.0 - self.gamma) * self.margin, self.reserve)
        return (
            self.threshold - target_margin - (1.0 - self.alpha) * self.state
        ) / self.alpha

    def update(self, interference: float) -> float:
        self.state = (1.0 - self.alpha) * self.state + self.alpha * interference
        return self.state


def unprotected_scale(nominal: float, previous: float, max_change: float) -> float:
    return bounded_move(nominal, previous, max_change)


def hard_backoff_scale(nominal: float, previous: float, max_change: float, fixed_scale: float = 0.35) -> float:
    return bounded_move(min(nominal, fixed_scale), previous, max_change)


def static_cap_scale(nominal: float, previous: float, coupling: float, threshold: float, max_change: float) -> float:
    target = nominal if coupling <= 0 else min(nominal, threshold / coupling)
    return bounded_move(target, previous, max_change)


def myopic_scale(nominal: float, previous: float, coupling_now: float, threshold: float, max_change: float) -> float:
    return static_cap_scale(nominal, previous, coupling_now, threshold, max_change)


def cbf_scale(
    nominal: float,
    previous: float,
    coupling_upper_next: float,
    threshold: float,
    max_change: float,
    reserve_fraction: float,
) -> float:
    safe_threshold = max(0.0, (1.0 - reserve_fraction) * threshold)
    target = nominal if coupling_upper_next <= 0 else min(nominal, safe_threshold / coupling_upper_next)
    return bounded_move(target, previous, max_change)


def virtual_queue_scale(
    nominal: float,
    previous: float,
    coupling_now: float,
    threshold: float,
    queue: float,
    max_change: float,
    gain: float = 0.25,
) -> tuple[float, float]:
    target = nominal / (1.0 + gain * max(queue, 0.0))
    applied = bounded_move(target, previous, max_change)
    interference = coupling_now * applied
    new_queue = max(0.0, queue + interference - threshold)
    return applied, new_queue
