"""Corrected EESS dual-criterion controller helpers.

This module reuses the validated full-topology online-PF implementation. It
adds a dynamically rebuilt virtual-queue baseline, exact hard-null evaluation,
and explicit long-versus-short normalized-dominance checks.

Claim boundary: one seed, one pass, ideal digital spatial-mode model. This is
not regulatory compliance evidence and not a paper result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from fr3_cbf.constrained_pf_safety import PriceAllocator
from fr3_cbf.online_pf_load_transition import (
    LoadState,
    build_online_moving_pf_cost_grid,
    exact_user_rates_for_action,
)
from fr3_cbf.robust_delayed_safety import choose_with_external_price


@dataclass(frozen=True)
class OnlineVirtualQueueRun:
    command_db: np.ndarray
    applied_db: np.ndarray
    delivered_total_rate: np.ndarray
    delivered_protected_rate: np.ndarray
    moving_average_rate: np.ndarray
    queue: np.ndarray
    safety_ratio: np.ndarray
    local_table_build_seconds: np.ndarray
    command_feasible: np.ndarray


def interval_reduce(
    second_array: np.ndarray,
    update_interval_s: int,
    reducer: str,
) -> tuple[np.ndarray, np.ndarray]:
    value = np.asarray(second_array)
    if value.ndim < 1 or update_interval_s <= 0:
        raise ValueError("invalid second array or update interval")
    rows = []
    lengths = []
    for start in range(0, len(value), int(update_interval_s)):
        stop = min(start + int(update_interval_s), len(value))
        block = value[start:stop]
        if reducer == "max":
            rows.append(np.max(block, axis=0))
        elif reducer == "min":
            rows.append(np.min(block, axis=0))
        else:
            raise ValueError("reducer must be max or min")
        lengths.append(stop - start)
    return np.asarray(rows), np.asarray(lengths, dtype=np.int64)


def exact_second_safety_ratio(
    kappa_time_sector: np.ndarray,
    states: Sequence[LoadState],
    applied_interval_q_db: np.ndarray,
    update_interval_s: int,
    allowance_second_w: np.ndarray,
) -> np.ndarray:
    kappa = np.asarray(kappa_time_sector, dtype=float)
    actions = np.asarray(applied_interval_q_db, dtype=float)
    allowance = np.asarray(allowance_second_w, dtype=float)
    if kappa.shape != (587, 57):
        raise ValueError("kappa must have shape [587,57]")
    if allowance.shape != (587,) or np.any(allowance <= 0):
        raise ValueError("allowance must have shape [587] and be positive")
    if actions.shape != (len(states), 57, 2):
        raise ValueError("actions have the wrong shape")
    result = np.empty(587, dtype=float)
    for second in range(587):
        interval = min(second // int(update_interval_s), len(states) - 1)
        result[second] = float(
            (
                kappa[second, :, None]
                * states[interval].mode_leakage_w
                * np.power(10.0, -actions[interval] / 10.0)
            ).sum()
            / allowance[second]
        )
    return result


def simulate_online_virtual_queue(
    q_grid_db: np.ndarray,
    states: Sequence[LoadState],
    interval_contribution_w: np.ndarray,
    interval_allowance_w: np.ndarray,
    delay_intervals: int,
    slew_db_per_update: float,
    moving_average_initial_rate: np.ndarray,
    averaging_alpha: float,
    eligible_user: np.ndarray,
    required_floor_by_interval: np.ndarray,
    serving_bs_index: np.ndarray,
    serving_stream_index: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    epsilon_bps_hz: float,
    price_gain: float,
) -> OnlineVirtualQueueRun:
    """Online moving-PF virtual-queue baseline.

    The queue price reacts to realized normalized interference. It has no hard
    instantaneous safety guarantee. Local PF cost tables are rebuilt online
    around the currently applied action, making the baseline fairer than a
    frozen-table queue while retaining its long-term-only interpretation.
    """
    q_grid = np.asarray(q_grid_db, dtype=float)
    contribution = np.asarray(interval_contribution_w, dtype=float)
    allowance = np.asarray(interval_allowance_w, dtype=float)
    floors = np.asarray(required_floor_by_interval, dtype=float)
    average = np.asarray(moving_average_initial_rate, dtype=float).copy()
    eligible = np.asarray(eligible_user, dtype=bool)
    if price_gain <= 0:
        raise ValueError("price_gain must be positive")
    if contribution.shape != (len(states), 57, 2):
        raise ValueError("contribution has the wrong shape")
    if allowance.shape != (len(states),):
        raise ValueError("allowance has the wrong shape")
    if not np.allclose(allowance, allowance[0], rtol=0.0, atol=0.0):
        raise ValueError("this baseline expects constant allowance")
    if floors.shape != (len(states), 228):
        raise ValueError("floor schedule has the wrong shape")

    initial_cost, _ = build_online_moving_pf_cost_grid(
        q_grid,
        states[0],
        np.zeros((57, 2), dtype=float),
        average,
        eligible,
        floors[0],
        serving_bs_index,
        serving_stream_index,
        protected_noise_w,
        protected_weight,
        averaging_alpha,
        epsilon_bps_hz,
    )
    initial_allocator = PriceAllocator(
        q_grid,
        initial_cost,
        float(allowance[0]),
    )
    preload, ratio, ok, _ = initial_allocator.solve(contribution[0])
    if not ok or ratio > 1.0 + 1e-10:
        raise RuntimeError("virtual-queue preload is infeasible")

    command = np.empty((len(states), 57, 2), dtype=float)
    applied = np.empty_like(command)
    delivered_total = np.empty((len(states), 228), dtype=float)
    delivered_protected = np.empty_like(delivered_total)
    average_trace = np.empty_like(delivered_total)
    queue = np.zeros(len(states) + 1, dtype=float)
    safety_ratio = np.empty(len(states), dtype=float)
    build_seconds = np.empty(len(states), dtype=float)
    feasible = np.ones(len(states), dtype=bool)
    previous = preload.copy()

    import time

    for index, state in enumerate(states):
        source = index - int(delay_intervals)
        applied[index] = command[source] if source >= 0 else preload
        total_rate, protected_rate = exact_user_rates_for_action(
            applied[index],
            state,
            serving_bs_index,
            serving_stream_index,
            protected_noise_w,
            protected_weight,
        )
        delivered_total[index] = total_rate
        delivered_protected[index] = protected_rate
        average = (
            (1.0 - float(averaging_alpha)) * average
            + float(averaging_alpha) * total_rate
        )
        average_trace[index] = average

        started = time.perf_counter()
        cost, _ = build_online_moving_pf_cost_grid(
            q_grid,
            state,
            applied[index],
            average,
            eligible,
            floors[index],
            serving_bs_index,
            serving_stream_index,
            protected_noise_w,
            protected_weight,
            averaging_alpha,
            epsilon_bps_hz,
        )
        build_seconds[index] = time.perf_counter() - started
        allocator = PriceAllocator(q_grid, cost, float(allowance[index]))
        command[index] = choose_with_external_price(
            allocator,
            contribution[index],
            price=float(price_gain) * queue[index],
            previous_q_db=previous,
            slew_db_per_update=slew_db_per_update,
        )
        previous = command[index]

        safety_ratio[index] = float(
            (
                contribution[index]
                * np.power(10.0, -applied[index] / 10.0)
            ).sum()
            / allowance[index]
        )
        queue[index + 1] = max(
            0.0,
            queue[index] + safety_ratio[index] - 1.0,
        )

    return OnlineVirtualQueueRun(
        command_db=command,
        applied_db=applied,
        delivered_total_rate=delivered_total,
        delivered_protected_rate=delivered_protected,
        moving_average_rate=average_trace,
        queue=queue,
        safety_ratio=safety_ratio,
        local_table_build_seconds=build_seconds,
        command_feasible=feasible,
    )


def exact_hard_null_rates(
    state: LoadState,
    serving_bs_index: np.ndarray,
    serving_stream_index: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate an exact zero scale on both incumbent-parallel modes."""
    serving = np.asarray(serving_bs_index, dtype=np.int64)
    stream = np.asarray(serving_stream_index, dtype=np.int64)
    amplitude = np.asarray(state.amp_perpendicular)
    power = np.abs(amplitude) ** 2
    desired = power[np.arange(228), serving, stream]
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
    total_rate[~state.active_user] = 0.0
    protected[~state.active_user] = 0.0
    return total_rate, protected


def common_scale_action(
    interval_contribution_w: np.ndarray,
    interval_allowance_w: np.ndarray,
) -> np.ndarray:
    contribution = np.asarray(interval_contribution_w, dtype=float)
    allowance = np.asarray(interval_allowance_w, dtype=float)
    required = np.maximum(
        0.0,
        10.0
        * np.log10(
            np.maximum(contribution.sum(axis=(1, 2)), 1e-300)
            / allowance
        ),
    )
    return np.broadcast_to(
        required[:, None, None],
        contribution.shape,
    ).copy()


def normalized_short_to_long_ratio(
    kappa_short: np.ndarray,
    allowance_short: np.ndarray,
    kappa_long: np.ndarray,
    allowance_long: np.ndarray,
) -> np.ndarray:
    short = np.asarray(kappa_short, dtype=float) / np.asarray(
        allowance_short, dtype=float
    )[:, None]
    long = np.asarray(kappa_long, dtype=float) / np.asarray(
        allowance_long, dtype=float
    )[:, None]
    return short / long
