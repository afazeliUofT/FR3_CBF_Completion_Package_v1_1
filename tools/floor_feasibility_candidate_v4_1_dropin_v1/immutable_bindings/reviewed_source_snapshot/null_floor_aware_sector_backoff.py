"""Null-floor-aware sector-selective protected-tone backoff.

This module implements a deterministic one-seed engineering fallback. It does
not turn assumed null-depth or coupling-uplift scenarios into calibration data.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from time import perf_counter
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class BackoffRun:
    """Per-interval fallback actions and exact rate/safety traces."""

    sector_backoff_db: np.ndarray
    sector_power_scale: np.ndarray
    second_ratio: np.ndarray
    delivered_total_rate: np.ndarray
    delivered_protected_rate: np.ndarray
    moving_average_rate: np.ndarray
    interval_floor_violation_count: np.ndarray
    interval_normalized_shortfall: np.ndarray
    local_table_build_seconds: np.ndarray
    envelope_ratio: np.ndarray


def power_scale_from_backoff(backoff_db: np.ndarray) -> np.ndarray:
    """Convert power backoff in dB to a linear power scale.

    ``+inf`` is the explicit protected-tone sector-mute endpoint.
    """
    value = np.asarray(backoff_db, dtype=float)
    result = np.zeros_like(value, dtype=float)
    finite = np.isfinite(value)
    result[finite] = np.power(10.0, -value[finite] / 10.0)
    return result


def interval_sector_envelope(
    kappa_second_sector: np.ndarray,
    leakage_interval_sector_mode: np.ndarray,
    allowance_second: np.ndarray,
    update_interval_s: int,
    coupling_uplift_db: float,
) -> np.ndarray:
    """Return conservative normalized contribution envelopes per sector.

    The returned array has shape ``[interval, 57]``. Each entry is the maximum,
    over all seconds in that update interval, of the sector contribution after
    applying the declared residual-coupling uplift.
    """
    kappa = np.asarray(kappa_second_sector, dtype=float)
    leakage = np.asarray(leakage_interval_sector_mode, dtype=float)
    allowance = np.asarray(allowance_second, dtype=float)
    if kappa.ndim != 2 or kappa.shape[1] != 57:
        raise ValueError("kappa must have shape [seconds,57]")
    if leakage.ndim != 3 or leakage.shape[1:] != (57, 2):
        raise ValueError("leakage must have shape [intervals,57,2]")
    if allowance.shape != (len(kappa),) or np.any(allowance <= 0.0):
        raise ValueError("allowance must be positive with one value per second")
    if update_interval_s <= 0:
        raise ValueError("update_interval_s must be positive")

    uplift = 10.0 ** (float(coupling_uplift_db) / 10.0)
    rows: list[np.ndarray] = []
    for interval in range(len(leakage)):
        start = interval * int(update_interval_s)
        stop = min(start + int(update_interval_s), len(kappa))
        if start >= stop:
            raise ValueError("leakage contains more intervals than the pass")
        normalized = (
            kappa[start:stop, :, None]
            * leakage[interval][None, :, :]
        ).sum(axis=2) / allowance[start:stop, None]
        rows.append(uplift * np.max(normalized, axis=0))
    return np.asarray(rows, dtype=float)


def exact_second_ratio(
    kappa_second_sector: np.ndarray,
    leakage_interval_sector_mode: np.ndarray,
    sector_power_scale: np.ndarray,
    allowance_second: np.ndarray,
    update_interval_s: int,
    coupling_uplift_db: float,
) -> np.ndarray:
    """Evaluate the exact normalized incumbent interference every second."""
    kappa = np.asarray(kappa_second_sector, dtype=float)
    leakage = np.asarray(leakage_interval_sector_mode, dtype=float)
    scale = np.asarray(sector_power_scale, dtype=float)
    allowance = np.asarray(allowance_second, dtype=float)
    if leakage.shape != (len(scale), 57, 2):
        raise ValueError("leakage and sector power scales do not align")
    if scale.shape[1:] != (57,):
        raise ValueError("sector_power_scale must have shape [intervals,57]")
    if allowance.shape != (len(kappa),):
        raise ValueError("allowance length mismatch")

    uplift = 10.0 ** (float(coupling_uplift_db) / 10.0)
    result = np.empty(len(kappa), dtype=float)
    for second in range(len(kappa)):
        interval = min(
            second // int(update_interval_s),
            len(leakage) - 1,
        )
        result[second] = float(
            uplift
            * np.sum(
                kappa[second, :, None]
                * leakage[interval]
                * scale[interval, :, None]
            )
            / allowance[second]
        )
    return result


def exact_rates(
    state: object,
    q_db: np.ndarray,
    sector_power_scale: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate exact full-network rates under mode and sector power actions."""
    q = np.asarray(q_db, dtype=float)
    sector_scale = np.asarray(sector_power_scale, dtype=float)
    if q.shape != (57, 2) or sector_scale.shape != (57,):
        raise ValueError("invalid action shape")
    if np.any(sector_scale < 0.0) or np.any(sector_scale > 1.0):
        raise ValueError("sector power scale must lie in [0,1]")

    mode_scale = np.power(10.0, -q / 20.0)
    sector_amplitude = (
        np.asarray(state.amp_perpendicular)
        + mode_scale[None, :, 0, None] * np.asarray(state.amp_pol1)
        + mode_scale[None, :, 1, None] * np.asarray(state.amp_pol2)
    )
    amplitude = sector_amplitude * np.sqrt(sector_scale)[None, :, None]
    power = np.abs(amplitude) ** 2
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    desired = power[np.arange(len(serving)), serving, stream]
    total = power.sum(axis=(1, 2))
    protected = np.log2(
        1.0
        + desired
        / (total - desired + float(protected_noise_w))
    )
    total_rate = (
        np.asarray(state.other_weighted_rate, dtype=float)
        + float(protected_weight) * protected
    )
    total_rate = np.asarray(total_rate, dtype=float)
    protected = np.asarray(protected, dtype=float)
    total_rate[~np.asarray(state.active_user, dtype=bool)] = 0.0
    protected[~np.asarray(state.active_user, dtype=bool)] = 0.0
    return total_rate, protected


def build_local_cost_table(
    state: object,
    q_db: np.ndarray,
    current_average: np.ndarray,
    eligible: np.ndarray,
    floors: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    averaging_alpha: float,
    epsilon_bps_hz: float,
    backoff_grid_db: np.ndarray,
) -> tuple[np.ndarray, dict[str, object]]:
    """Build one constrained-PF protected-tone backoff curve per sector.

    Each sector evaluates only its four served users while all other sectors
    remain at their current capped-mode actions. Final selected actions receive
    an exact full-network rate and floor audit.
    """
    q = np.asarray(q_db, dtype=float)
    grid = np.asarray(backoff_grid_db, dtype=float)
    power_scale = power_scale_from_backoff(grid)
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    eligible = np.asarray(eligible, dtype=bool)
    floor = np.asarray(floors, dtype=float)
    average = np.asarray(current_average, dtype=float)
    if q.shape != (57, 2):
        raise ValueError("q_db must have shape [57,2]")
    if grid.ndim != 1 or len(grid) < 2:
        raise ValueError("backoff grid must be one-dimensional")
    if eligible.shape != (228,) or floor.shape != (228,):
        raise ValueError("eligible and floors must have shape [228]")

    mode_scale = np.power(10.0, -q / 20.0)
    sector_amplitude = (
        np.asarray(state.amp_perpendicular)
        + mode_scale[None, :, 0, None] * np.asarray(state.amp_pol1)
        + mode_scale[None, :, 1, None] * np.asarray(state.amp_pol2)
    )

    shape = (57, len(grid))
    violation = np.zeros(shape, dtype=np.int16)
    shortfall = np.zeros(shape, dtype=np.float64)
    pf_loss = np.zeros(shape, dtype=np.float64)
    active_eligible_by_sector: list[int] = []

    for bs in range(57):
        users = np.flatnonzero(serving == bs)
        if len(users) != 4:
            raise ValueError(f"sector {bs} does not serve exactly four users")
        local = sector_amplitude[users]
        own = local[:, bs, :]
        other_power = (
            np.abs(local) ** 2
        ).sum(axis=(1, 2)) - (
            np.abs(own) ** 2
        ).sum(axis=1)
        active_eligible = (
            np.asarray(state.active_user, dtype=bool)[users]
            & eligible[users]
        )
        active_eligible_by_sector.append(int(active_eligible.sum()))

        # Vectorize the full backoff grid. Shapes are [G,4,4] and [G,4],
        # where G is the number of finite choices plus the mute endpoint.
        own_power = (
            np.abs(own)[None, :, :] ** 2
            * power_scale[:, None, None]
        )
        desired = own_power[:, np.arange(4), stream[users]]
        total = other_power[None, :] + own_power.sum(axis=2)
        protected_rate = np.log2(
            1.0
            + desired
            / (total - desired + float(protected_noise_w))
        )
        rate = (
            np.asarray(state.other_weighted_rate, dtype=float)[users][
                None, :
            ]
            + float(protected_weight) * protected_rate
        )
        rate[:, ~np.asarray(state.active_user, dtype=bool)[users]] = 0.0

        if np.any(active_eligible):
            local_floor = floor[users][active_eligible]
            delivered = rate[:, active_eligible]
            violation[bs] = (
                delivered < local_floor[None, :] - 1e-12
            ).sum(axis=1)
            shortfall[bs] = np.maximum(
                0.0,
                (local_floor[None, :] - delivered)
                / local_floor[None, :],
            ).sum(axis=1)
            next_average = (
                (1.0 - float(averaging_alpha))
                * average[users][active_eligible][None, :]
                + float(averaging_alpha) * delivered
            )
            pf_loss[bs] = -np.log(
                next_average + float(epsilon_bps_hz)
            ).sum(axis=1)

    shifted_pf = pf_loss - pf_loss.min(axis=1, keepdims=True)
    total_pf_range = float(
        np.sum(pf_loss.max(axis=1) - pf_loss.min(axis=1))
    )
    shortfall_weight = total_pf_range + 1.0
    violation_weight = (
        int(eligible.sum()) * shortfall_weight
        + total_pf_range
        + 1.0
    )
    # Prefer less backoff only after floor and PF priorities are tied. Treat the
    # explicit mute as one step beyond the largest finite grid point.
    proxy = np.where(
        np.isfinite(grid),
        grid,
        float(np.max(grid[np.isfinite(grid)])) + 1.0,
    )
    tie_break = 1e-10 * proxy[None, :] / max(float(proxy.max()), 1.0)
    cost = (
        violation_weight * violation
        + shortfall_weight * shortfall
        + shifted_pf
        + tie_break
    )
    audit = {
        "active_eligible_user_count": int(
            (
                np.asarray(state.active_user, dtype=bool)
                & eligible
            ).sum()
        ),
        "active_eligible_user_count_by_sector": active_eligible_by_sector,
        "violation_weight": violation_weight,
        "shortfall_weight": shortfall_weight,
        "total_pf_range": total_pf_range,
        "maximum_local_candidate_violation_count": int(violation.max()),
        "maximum_local_candidate_normalized_shortfall": float(
            shortfall.max()
        ),
    }
    return cost, audit


class SectorBackoffPriceAllocator:
    """Scalar-price decomposition over one local backoff curve per sector."""

    def __init__(self, backoff_grid_db: np.ndarray) -> None:
        self.grid = np.asarray(backoff_grid_db, dtype=float)
        self.power_scale = power_scale_from_backoff(self.grid)
        if self.grid.ndim != 1:
            raise ValueError("backoff grid must be one-dimensional")
        if not np.any(self.power_scale == 0.0):
            raise ValueError("an exact sector-mute endpoint is required")

    def solve(
        self,
        cost: np.ndarray,
        sector_envelope: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, float, float, bool]:
        cost = np.asarray(cost, dtype=float)
        contribution = np.asarray(sector_envelope, dtype=float)
        if cost.shape != (57, len(self.grid)):
            raise ValueError("cost table has the wrong shape")
        if contribution.shape != (57,) or np.any(contribution < 0.0):
            raise ValueError("sector envelope has the wrong shape")
        normalized = contribution[:, None] * self.power_scale[None, :]

        def choose(price: float) -> tuple[float, np.ndarray]:
            index = np.argmin(
                cost + float(price) * normalized,
                axis=1,
            )
            ratio = float(
                normalized[np.arange(57), index].sum()
            )
            return ratio, index

        ratio, index = choose(0.0)
        if ratio <= 1.0 + 1e-12:
            return (
                self.grid[index],
                self.power_scale[index],
                ratio,
                0.0,
                True,
            )

        high = 1.0
        while high < 1e30:
            ratio, index = choose(high)
            if ratio <= 1.0:
                break
            high *= 10.0
        if ratio > 1.0:
            # With a zero-power endpoint this should be unreachable.
            return (
                self.grid[index],
                self.power_scale[index],
                ratio,
                math.inf,
                False,
            )

        low = 0.0
        for _ in range(60):
            middle = 0.5 * (low + high)
            middle_ratio, _ = choose(middle)
            if middle_ratio <= 1.0:
                high = middle
            else:
                low = middle
        ratio, index = choose(high)
        return (
            self.grid[index],
            self.power_scale[index],
            ratio,
            high,
            True,
        )


def _floor_metrics(
    delivered: np.ndarray,
    state: object,
    eligible: np.ndarray,
    floors: np.ndarray,
) -> tuple[int, float]:
    active_eligible = (
        np.asarray(state.active_user, dtype=bool)
        & np.asarray(eligible, dtype=bool)
    )
    valid = active_eligible & (np.asarray(floors, dtype=float) > 0.0)
    violation = active_eligible & (
        delivered < np.asarray(floors, dtype=float) - 1e-12
    )
    shortfall = float(
        np.sum(
            np.maximum(
                0.0,
                (
                    np.asarray(floors, dtype=float)[valid]
                    - delivered[valid]
                )
                / np.asarray(floors, dtype=float)[valid],
            )
        )
    )
    return int(violation.sum()), shortfall


def simulate_sector_selective(
    ideal_actions_db: np.ndarray,
    capped_leakage: np.ndarray,
    states: Sequence[object],
    kappa_second: np.ndarray,
    allowance_second: np.ndarray,
    update_interval_s: int,
    coupling_uplift_db: float,
    null_depth_cap_db: float,
    backoff_grid_db: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    initial_average: np.ndarray,
    averaging_alpha: float,
    eligible: np.ndarray,
    floors: np.ndarray,
    epsilon_bps_hz: float,
) -> BackoffRun:
    """Run the distributed sector-selective fallback over the full pass."""
    ideal = np.asarray(ideal_actions_db, dtype=float)
    leakage = np.asarray(capped_leakage, dtype=float)
    if ideal.shape != (len(states), 57, 2):
        raise ValueError("ideal actions have the wrong shape")
    if leakage.shape != (len(states), 57, 2):
        raise ValueError("capped leakage has the wrong shape")
    q_capped = np.minimum(ideal, float(null_depth_cap_db))
    envelope = interval_sector_envelope(
        kappa_second,
        leakage,
        allowance_second,
        update_interval_s,
        coupling_uplift_db,
    )
    allocator = SectorBackoffPriceAllocator(backoff_grid_db)
    average = np.asarray(initial_average, dtype=float).copy()

    backoff_rows: list[np.ndarray] = []
    scale_rows: list[np.ndarray] = []
    total_rows: list[np.ndarray] = []
    protected_rows: list[np.ndarray] = []
    average_rows: list[np.ndarray] = []
    floor_counts: list[int] = []
    shortfalls: list[float] = []
    build_seconds: list[float] = []
    envelope_ratios: list[float] = []

    for interval, state in enumerate(states):
        started = perf_counter()
        cost, _audit = build_local_cost_table(
            state,
            q_capped[interval],
            average,
            eligible,
            floors[interval],
            serving_bs,
            serving_stream,
            protected_noise_w,
            protected_weight,
            averaging_alpha,
            epsilon_bps_hz,
            backoff_grid_db,
        )
        build_seconds.append(perf_counter() - started)
        backoff, scale, ratio, _price, feasible = allocator.solve(
            cost,
            envelope[interval],
        )
        if not feasible:
            raise RuntimeError(
                f"sector-selective fallback infeasible at interval {interval}"
            )
        delivered, protected = exact_rates(
            state,
            q_capped[interval],
            scale,
            serving_bs,
            serving_stream,
            protected_noise_w,
            protected_weight,
        )
        floor_count, shortfall = _floor_metrics(
            delivered,
            state,
            eligible,
            floors[interval],
        )
        average = (
            (1.0 - float(averaging_alpha)) * average
            + float(averaging_alpha) * delivered
        )

        backoff_rows.append(backoff)
        scale_rows.append(scale)
        total_rows.append(delivered)
        protected_rows.append(protected)
        average_rows.append(average.copy())
        floor_counts.append(floor_count)
        shortfalls.append(shortfall)
        envelope_ratios.append(ratio)

    scales = np.asarray(scale_rows, dtype=float)
    second_ratio = exact_second_ratio(
        kappa_second,
        leakage,
        scales,
        allowance_second,
        update_interval_s,
        coupling_uplift_db,
    )
    return BackoffRun(
        sector_backoff_db=np.asarray(backoff_rows, dtype=float),
        sector_power_scale=scales,
        second_ratio=second_ratio,
        delivered_total_rate=np.asarray(total_rows, dtype=float),
        delivered_protected_rate=np.asarray(protected_rows, dtype=float),
        moving_average_rate=np.asarray(average_rows, dtype=float),
        interval_floor_violation_count=np.asarray(
            floor_counts,
            dtype=np.int64,
        ),
        interval_normalized_shortfall=np.asarray(shortfalls, dtype=float),
        local_table_build_seconds=np.asarray(build_seconds, dtype=float),
        envelope_ratio=np.asarray(envelope_ratios, dtype=float),
    )


def simulate_uniform(
    ideal_actions_db: np.ndarray,
    capped_leakage: np.ndarray,
    states: Sequence[object],
    kappa_second: np.ndarray,
    allowance_second: np.ndarray,
    update_interval_s: int,
    coupling_uplift_db: float,
    null_depth_cap_db: float,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    initial_average: np.ndarray,
    averaging_alpha: float,
    eligible: np.ndarray,
    floors: np.ndarray,
    epsilon_bps_hz: float,
) -> BackoffRun:
    """Run the minimum interval-wise uniform protected-tone backoff baseline."""
    ideal = np.asarray(ideal_actions_db, dtype=float)
    leakage = np.asarray(capped_leakage, dtype=float)
    q_capped = np.minimum(ideal, float(null_depth_cap_db))
    envelope = interval_sector_envelope(
        kappa_second,
        leakage,
        allowance_second,
        update_interval_s,
        coupling_uplift_db,
    )
    average = np.asarray(initial_average, dtype=float).copy()

    backoff_rows: list[np.ndarray] = []
    scale_rows: list[np.ndarray] = []
    total_rows: list[np.ndarray] = []
    protected_rows: list[np.ndarray] = []
    average_rows: list[np.ndarray] = []
    floor_counts: list[int] = []
    shortfalls: list[float] = []
    envelope_ratios: list[float] = []

    for interval, state in enumerate(states):
        required_db = max(
            0.0,
            10.0 * math.log10(float(envelope[interval].sum())),
        )
        backoff = np.full(57, required_db, dtype=float)
        scale = np.full(
            57,
            10.0 ** (-required_db / 10.0),
            dtype=float,
        )
        delivered, protected = exact_rates(
            state,
            q_capped[interval],
            scale,
            serving_bs,
            serving_stream,
            protected_noise_w,
            protected_weight,
        )
        floor_count, shortfall = _floor_metrics(
            delivered,
            state,
            eligible,
            floors[interval],
        )
        average = (
            (1.0 - float(averaging_alpha)) * average
            + float(averaging_alpha) * delivered
        )
        backoff_rows.append(backoff)
        scale_rows.append(scale)
        total_rows.append(delivered)
        protected_rows.append(protected)
        average_rows.append(average.copy())
        floor_counts.append(floor_count)
        shortfalls.append(shortfall)
        envelope_ratios.append(
            float(envelope[interval].sum() * scale[0])
        )

    scales = np.asarray(scale_rows, dtype=float)
    second_ratio = exact_second_ratio(
        kappa_second,
        leakage,
        scales,
        allowance_second,
        update_interval_s,
        coupling_uplift_db,
    )
    return BackoffRun(
        sector_backoff_db=np.asarray(backoff_rows, dtype=float),
        sector_power_scale=scales,
        second_ratio=second_ratio,
        delivered_total_rate=np.asarray(total_rows, dtype=float),
        delivered_protected_rate=np.asarray(protected_rows, dtype=float),
        moving_average_rate=np.asarray(average_rows, dtype=float),
        interval_floor_violation_count=np.asarray(
            floor_counts,
            dtype=np.int64,
        ),
        interval_normalized_shortfall=np.asarray(shortfalls, dtype=float),
        local_table_build_seconds=np.zeros(len(states), dtype=float),
        envelope_ratio=np.asarray(envelope_ratios, dtype=float),
    )
