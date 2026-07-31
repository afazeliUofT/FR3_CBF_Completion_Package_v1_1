"""Online moving-average proportional fairness with load transitions.

This module operates on the validated full-topology export. It recomputes
local RZF precoders whenever the active-user set changes, rebuilds protected
mode decompositions, and supports distributed scalar-price safety control.

Claim boundary: one validated channel/topology seed and one protected pass.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

from fr3_cbf.constrained_pf_safety import PriceAllocator
from fr3_cbf.robust_delayed_safety import (
    full_horizon_reachability_envelope,
)


@dataclass(frozen=True)
class LoadState:
    """Channel/precoder/rate state for one deterministic activity mask."""

    active_user: np.ndarray
    nominal_precoder_by_frequency: np.ndarray
    nominal_total_rate: np.ndarray
    nominal_protected_rate: np.ndarray
    other_weighted_rate: np.ndarray
    amp_perpendicular: np.ndarray
    amp_pol1: np.ndarray
    amp_pol2: np.ndarray
    mode_leakage_w: np.ndarray


@dataclass(frozen=True)
class OnlineControllerRun:
    """Sequential command, action, throughput, and fairness record."""

    command_db: np.ndarray
    applied_db: np.ndarray
    command_feasible: np.ndarray
    fail_safe_used: np.ndarray
    upper_interval_ratio: np.ndarray
    nominal_interval_ratio: np.ndarray
    delivered_total_rate: np.ndarray
    delivered_protected_rate: np.ndarray
    moving_average_rate: np.ndarray
    local_table_build_seconds: np.ndarray
    active_user_schedule: np.ndarray


def exponential_average_alpha(
    update_interval_s: float,
    averaging_time_constant_s: float,
) -> float:
    """Return an exact continuous-time-equivalent exponential update factor."""
    if update_interval_s <= 0 or averaging_time_constant_s <= 0:
        raise ValueError("update interval and time constant must be positive")
    return float(
        1.0
        - math.exp(
            -float(update_interval_s)
            / float(averaging_time_constant_s)
        )
    )


def build_rotating_load_schedule(
    serving_bs_index: np.ndarray,
    serving_stream_index: np.ndarray,
    interval_count: int,
    phase_lengths: Sequence[int],
    load_stream_counts: Sequence[int],
) -> tuple[np.ndarray, list[dict[str, object]]]:
    """Build a deterministic sector-rotated user arrival/departure schedule.

    Each phase activates the declared number of local streams per sector.
    The selected streams rotate with sector and phase index, preventing one
    fixed stream from receiving systematically better treatment.
    """
    serving = np.asarray(serving_bs_index, dtype=np.int64)
    stream = np.asarray(serving_stream_index, dtype=np.int64)
    if serving.shape != (228,) or stream.shape != (228,):
        raise ValueError("serving arrays must have shape [228]")
    if interval_count <= 0:
        raise ValueError("interval_count must be positive")
    if len(phase_lengths) != len(load_stream_counts):
        raise ValueError("phase lengths and stream counts must align")
    if any(length <= 0 for length in phase_lengths):
        raise ValueError("phase lengths must be positive")
    if any(count < 1 or count > 4 for count in load_stream_counts):
        raise ValueError("active stream counts must lie in [1,4]")

    schedule = np.zeros((interval_count, 228), dtype=bool)
    phase_records: list[dict[str, object]] = []
    start = 0
    for phase_index, (requested_length, active_count) in enumerate(
        zip(phase_lengths, load_stream_counts)
    ):
        if start >= interval_count:
            break
        stop = min(start + int(requested_length), interval_count)
        for bs in range(57):
            rotation = (bs + phase_index) % 4
            selected = {
                (rotation + offset) % 4
                for offset in range(int(active_count))
            }
            user_mask = serving == bs
            schedule[start:stop, user_mask] = np.isin(
                stream[user_mask],
                sorted(selected),
            )[None, :]
        phase_records.append(
            {
                "phase_index": phase_index,
                "start_interval": start,
                "stop_interval_exclusive": stop,
                "interval_count": stop - start,
                "active_streams_per_sector": int(active_count),
                "active_user_count": int(
                    schedule[start].sum()
                ),
            }
        )
        start = stop

    # Extend the final declared phase if the requested lengths do not cover
    # the complete finite pass.
    if start < interval_count:
        phase_index = len(phase_records)
        active_count = int(load_stream_counts[-1])
        for bs in range(57):
            rotation = (bs + phase_index) % 4
            selected = {
                (rotation + offset) % 4
                for offset in range(active_count)
            }
            user_mask = serving == bs
            schedule[start:, user_mask] = np.isin(
                stream[user_mask],
                sorted(selected),
            )[None, :]
        phase_records.append(
            {
                "phase_index": phase_index,
                "start_interval": start,
                "stop_interval_exclusive": interval_count,
                "interval_count": interval_count - start,
                "active_streams_per_sector": active_count,
                "active_user_count": int(schedule[start].sum()),
                "extended_final_phase": True,
            }
        )

    if np.any(schedule.sum(axis=1) < 57):
        raise RuntimeError("every sector must retain at least one active user")
    for interval in range(interval_count):
        counts = np.bincount(
            serving[schedule[interval]],
            minlength=57,
        )
        if np.any(counts < 1) or np.any(counts > 4):
            raise RuntimeError("invalid per-sector active-user count")
    return schedule, phase_records


def _local_rzf(
    channel_rows: np.ndarray,
    power_w: float,
    noise_w: float,
) -> np.ndarray:
    """Compute a locally normalized RZF precoder for one active user set."""
    h = np.asarray(channel_rows, dtype=np.complex128)
    if h.ndim != 2 or h.shape[0] < 1:
        raise ValueError("channel_rows must have shape [K,M], K>=1")
    columns = h.conj().T
    users = h.shape[0]
    alpha = max(float(users * noise_w / power_w), 1e-20)
    gram = columns.conj().T @ columns
    eye = np.eye(users, dtype=np.complex128)
    w = columns @ np.linalg.solve(
        gram + alpha * eye,
        eye,
    )
    norm = float(np.sum(np.abs(w) ** 2).real)
    if not np.isfinite(norm) or norm <= 0:
        raise RuntimeError("invalid local RZF norm")
    return (
        w * math.sqrt(float(power_w) / norm)
    ).astype(np.complex64)


def recompute_load_state(
    frequency_response: np.ndarray,
    active_user: np.ndarray,
    serving_bs_index: np.ndarray,
    serving_stream_index: np.ndarray,
    transmit_power_by_frequency_w: np.ndarray,
    noise_power_by_frequency_w: np.ndarray,
    frequency_weights: np.ndarray,
    protected_frequency_index: int,
    steering_pol1: np.ndarray,
    steering_pol2: np.ndarray,
) -> LoadState:
    """Recompute local RZF, full inter-cell rates, and protected modes."""
    h = np.asarray(frequency_response)
    active = np.asarray(active_user, dtype=bool)
    serving = np.asarray(serving_bs_index, dtype=np.int64)
    stream = np.asarray(serving_stream_index, dtype=np.int64)
    power_f = np.asarray(
        transmit_power_by_frequency_w,
        dtype=float,
    )
    noise_f = np.asarray(noise_power_by_frequency_w, dtype=float)
    weights = np.asarray(frequency_weights, dtype=float)
    s1 = np.asarray(steering_pol1)
    s2 = np.asarray(steering_pol2)
    if h.shape != (9, 228, 57, 128):
        raise ValueError("frequency_response has the wrong shape")
    if active.shape != (228,):
        raise ValueError("active_user must have shape [228]")
    if power_f.shape != (9,) or noise_f.shape != (9,):
        raise ValueError("power/noise arrays must have shape [9]")
    if weights.shape != (9,) or not np.isclose(
        weights.sum(),
        1.0,
        rtol=0.0,
        atol=1e-14,
    ):
        raise ValueError("invalid frequency weights")
    if s1.shape != (57, 128) or s2.shape != (57, 128):
        raise ValueError("steering arrays have the wrong shape")
    if protected_frequency_index < 0 or protected_frequency_index >= 9:
        raise ValueError("invalid protected frequency index")

    precoder = np.zeros(
        (9, 57, 128, 4),
        dtype=np.complex64,
    )
    for bs in range(57):
        users = np.flatnonzero((serving == bs) & active)
        if len(users) < 1:
            raise RuntimeError(
                f"sector {bs} has no active users"
            )
        local_streams = stream[users]
        if len(np.unique(local_streams)) != len(local_streams):
            raise RuntimeError("duplicate local stream index")
        for frequency in range(9):
            compact = _local_rzf(
                h[frequency, users, bs, :],
                float(power_f[frequency]),
                float(noise_f[frequency]),
            )
            precoder[frequency, bs][:, local_streams] = compact

    amplitude = np.einsum(
        "fubm,fbmk->fubk",
        h,
        precoder,
        optimize=True,
    ).astype(np.complex64)
    amp_power = np.abs(amplitude) ** 2
    total_power = amp_power.sum(axis=(2, 3))
    desired = amp_power[
        :,
        np.arange(228),
        serving,
        stream,
    ]
    interference = total_power - desired
    sinr = desired / (
        interference + noise_f[:, None]
    )
    rate = np.log2(1.0 + sinr)
    rate[:, ~active] = 0.0
    total_rate = (
        weights[:, None] * rate
    ).sum(axis=0)
    protected_rate = rate[protected_frequency_index].copy()
    other_rate = (
        total_rate
        - float(weights[protected_frequency_index])
        * protected_rate
    )

    protected_w = precoder[protected_frequency_index]
    a0 = np.empty((228, 57, 4), dtype=np.complex64)
    a1 = np.empty_like(a0)
    a2 = np.empty_like(a0)
    leakage = np.empty((57, 2), dtype=np.float64)
    h_protected = h[protected_frequency_index]
    for bs in range(57):
        v1 = s1[bs].astype(np.complex128)
        v2 = s2[bs].astype(np.complex128)
        u1 = v1 / np.linalg.norm(v1)
        u2 = v2 / np.linalg.norm(v2)
        w = protected_w[bs].astype(np.complex128)
        p1 = u1[:, None] * (
            u1.conj() @ w
        )[None, :]
        p2 = u2[:, None] * (
            u2.conj() @ w
        )[None, :]
        perpendicular = w - p1 - p2
        channel = h_protected[:, bs, :].astype(
            np.complex128
        )
        a0[:, bs, :] = (
            channel @ perpendicular
        ).astype(np.complex64)
        a1[:, bs, :] = (
            channel @ p1
        ).astype(np.complex64)
        a2[:, bs, :] = (
            channel @ p2
        ).astype(np.complex64)
        coefficient1 = v1.conj() @ w
        coefficient2 = v2.conj() @ w
        leakage[bs, 0] = float(
            np.sum(np.abs(coefficient1) ** 2).real
        )
        leakage[bs, 1] = float(
            np.sum(np.abs(coefficient2) ** 2).real
        )

    reconstructed = a0 + a1 + a2
    maximum_error = float(
        np.max(
            np.abs(
                reconstructed
                - amplitude[protected_frequency_index]
            )
        )
    )
    # This is a float32 multi-stage identity; use an explicit diagnostic
    # ceiling consistent with the validated V4 export contract.
    if maximum_error > 5e-5:
        raise RuntimeError(
            "protected amplitude decomposition failed: "
            f"{maximum_error}"
        )

    return LoadState(
        active_user=active.copy(),
        nominal_precoder_by_frequency=precoder,
        nominal_total_rate=total_rate.astype(np.float64),
        nominal_protected_rate=protected_rate.astype(np.float64),
        other_weighted_rate=other_rate.astype(np.float64),
        amp_perpendicular=a0,
        amp_pol1=a1,
        amp_pol2=a2,
        mode_leakage_w=leakage,
    )


def exact_user_rates_for_action(
    q_db: np.ndarray,
    state: LoadState,
    serving_bs_index: np.ndarray,
    serving_stream_index: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate current-load total and protected rates for one action."""
    q = np.asarray(q_db, dtype=float)
    if q.shape != (57, 2):
        raise ValueError("q_db must have shape [57,2]")
    scale = np.power(10.0, -q / 20.0)
    amplitude = (
        state.amp_perpendicular
        + scale[None, :, 0, None] * state.amp_pol1
        + scale[None, :, 1, None] * state.amp_pol2
    )
    power = np.abs(amplitude) ** 2
    serving = np.asarray(serving_bs_index, dtype=np.int64)
    stream = np.asarray(serving_stream_index, dtype=np.int64)
    desired = power[
        np.arange(228),
        serving,
        stream,
    ]
    total = power.sum(axis=(1, 2))
    protected_rate = np.log2(
        1.0
        + desired
        / (
            total
            - desired
            + float(protected_noise_w)
        )
    )
    total_rate = (
        state.other_weighted_rate
        + float(protected_weight) * protected_rate
    )
    total_rate = np.asarray(total_rate, dtype=float)
    protected_rate = np.asarray(protected_rate, dtype=float)
    total_rate[~state.active_user] = 0.0
    protected_rate[~state.active_user] = 0.0
    return total_rate, protected_rate


def build_online_moving_pf_cost_grid(
    q_grid_db: np.ndarray,
    state: LoadState,
    reference_q_db: np.ndarray,
    moving_average_rate: np.ndarray,
    eligible_user: np.ndarray,
    required_floor_rate: np.ndarray,
    serving_bs_index: np.ndarray,
    serving_stream_index: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    averaging_alpha: float,
    epsilon_bps_hz: float,
) -> tuple[np.ndarray, dict[str, object]]:
    """Build local online PF tables around the current applied network action.

    Each BS evaluates its active served users while all other sectors remain
    at the current applied action. The utility is the exact next-step
    logarithmic moving-average throughput, not a frozen instantaneous PF loss.
    """
    q_grid = np.asarray(q_grid_db, dtype=float)
    reference_q = np.asarray(reference_q_db, dtype=float)
    average = np.asarray(moving_average_rate, dtype=float)
    eligible = np.asarray(eligible_user, dtype=bool)
    floor = np.asarray(required_floor_rate, dtype=float)
    serving = np.asarray(serving_bs_index, dtype=np.int64)
    stream = np.asarray(serving_stream_index, dtype=np.int64)
    if q_grid.ndim != 1 or np.any(np.diff(q_grid) <= 0):
        raise ValueError("q_grid must be strictly increasing")
    if reference_q.shape != (57, 2):
        raise ValueError("reference_q_db must have shape [57,2]")
    if average.shape != (228,) or np.any(average < 0):
        raise ValueError("invalid moving average")
    if eligible.shape != (228,) or floor.shape != (228,):
        raise ValueError("eligible/floor vectors must have shape [228]")
    if not (0.0 < averaging_alpha <= 1.0):
        raise ValueError("averaging alpha must lie in (0,1]")
    if epsilon_bps_hz <= 0:
        raise ValueError("epsilon must be positive")

    grid_scale = np.power(10.0, -q_grid / 20.0)
    reference_scale = np.power(
        10.0,
        -reference_q / 20.0,
    )
    reference_amplitude = (
        state.amp_perpendicular
        + reference_scale[None, :, 0, None]
        * state.amp_pol1
        + reference_scale[None, :, 1, None]
        * state.amp_pol2
    )
    shape = (57, len(q_grid), len(q_grid))
    violation = np.zeros(shape, dtype=np.int8)
    shortfall = np.zeros(shape, dtype=np.float64)
    negative_log_next_average = np.zeros(
        shape,
        dtype=np.float64,
    )
    active_eligible_by_sector: list[int] = []

    for bs in range(57):
        users = np.flatnonzero(
            (serving == bs) & state.active_user
        )
        active_eligible = eligible[users]
        active_eligible_by_sector.append(
            int(active_eligible.sum())
        )
        if len(users) == 0:
            continue

        base = reference_amplitude[users]
        own_reference = base[:, bs, :]
        other_power = (
            np.abs(base) ** 2
        ).sum(axis=(1, 2)) - (
            np.abs(own_reference) ** 2
        ).sum(axis=1)
        own = (
            state.amp_perpendicular[
                users, bs, :
            ][None, None, :, :]
            + grid_scale[:, None, None, None]
            * state.amp_pol1[
                users, bs, :
            ][None, None, :, :]
            + grid_scale[None, :, None, None]
            * state.amp_pol2[
                users, bs, :
            ][None, None, :, :]
        )
        own_power = np.abs(own) ** 2
        total_power = (
            other_power[None, None, :]
            + own_power.sum(axis=3)
        )
        desired = own_power[
            :,
            :,
            np.arange(len(users)),
            stream[users],
        ]
        protected_rate = np.log2(
            1.0
            + desired
            / (
                total_power
                - desired
                + float(protected_noise_w)
            )
        )
        total_rate = (
            state.other_weighted_rate[
                users
            ][None, None, :]
            + float(protected_weight) * protected_rate
        )

        if active_eligible.any():
            eligible_rate = total_rate[
                :, :, active_eligible
            ]
            local_floor = floor[users][active_eligible]
            violation[bs] = (
                eligible_rate
                < local_floor[None, None, :] - 1e-12
            ).sum(axis=2)
            shortfall[bs] = np.maximum(
                0.0,
                (
                    local_floor[None, None, :]
                    - eligible_rate
                )
                / local_floor[None, None, :],
            ).sum(axis=2)
            next_average = (
                (1.0 - float(averaging_alpha))
                * average[users][active_eligible][
                    None, None, :
                ]
                + float(averaging_alpha)
                * eligible_rate
            )
            negative_log_next_average[bs] = -np.log(
                next_average + float(epsilon_bps_hz)
            ).sum(axis=2)

    utility_shifted = np.empty_like(
        negative_log_next_average
    )
    utility_range_by_sector = np.empty(57, dtype=float)
    for bs in range(57):
        minimum = float(
            negative_log_next_average[bs].min()
        )
        utility_shifted[bs] = (
            negative_log_next_average[bs] - minimum
        )
        utility_range_by_sector[bs] = float(
            negative_log_next_average[bs].max()
            - minimum
        )
    total_utility_range = float(
        utility_range_by_sector.sum()
    )
    active_eligible_count = int(
        np.sum(
            eligible & state.active_user
        )
    )
    shortfall_weight = total_utility_range + 1.0
    violation_weight = (
        max(active_eligible_count, 1)
        * shortfall_weight
        + total_utility_range
        + 1.0
    )
    tie_break = (
        1e-10
        * (
            q_grid[None, :, None]
            + q_grid[None, None, :]
        )
        / max(float(q_grid[-1]), 1.0)
    )
    cost = (
        violation_weight * violation
        + shortfall_weight * shortfall
        + utility_shifted
        + tie_break
    )
    return cost, {
        "active_user_count": int(
            state.active_user.sum()
        ),
        "active_eligible_user_count": active_eligible_count,
        "active_eligible_user_count_by_sector": (
            active_eligible_by_sector
        ),
        "violation_weight": violation_weight,
        "shortfall_weight": shortfall_weight,
        "total_next_average_utility_range": (
            total_utility_range
        ),
        "maximum_candidate_floor_violation_count": int(
            violation.max()
        ),
        "maximum_candidate_normalized_shortfall": float(
            shortfall.max()
        ),
    }


def full_horizon_dynamic_envelope(
    interval_contribution_w: np.ndarray,
    delay_intervals: int,
    slew_db_per_update: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Alias with explicit dynamic-load semantics."""
    return full_horizon_reachability_envelope(
        np.asarray(interval_contribution_w, dtype=float),
        delay_intervals=int(delay_intervals),
        slew_db_per_update=float(slew_db_per_update),
    )


def evaluate_interval_upper_ratio(
    contribution_w: np.ndarray,
    applied_q_db: np.ndarray,
    allowance_w: np.ndarray,
) -> np.ndarray:
    contribution = np.asarray(contribution_w, dtype=float)
    action = np.asarray(applied_q_db, dtype=float)
    allowance = np.asarray(allowance_w, dtype=float)
    if contribution.shape != action.shape:
        raise ValueError("contribution/action shapes must match")
    if allowance.shape != (len(contribution),):
        raise ValueError("allowance has the wrong shape")
    return (
        contribution
        * np.power(10.0, -action / 10.0)
    ).sum(axis=(1, 2)) / allowance


def simulate_online_predictive_controller(
    q_grid_db: np.ndarray,
    states: Sequence[LoadState],
    contribution_upper_w: np.ndarray,
    allowance_w: np.ndarray,
    application_envelope_w: np.ndarray,
    command_envelope_w: np.ndarray,
    delay_intervals: int,
    slew_db_per_update: float,
    maximum_action_db: float,
    moving_average_initial_rate: np.ndarray,
    averaging_alpha: float,
    eligible_user: np.ndarray,
    required_floor_by_interval: np.ndarray,
    serving_bs_index: np.ndarray,
    serving_stream_index: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    epsilon_bps_hz: float,
    fail_safe_drop_command_indices: Sequence[int] = (),
) -> OnlineControllerRun:
    """Sequential online moving-average PF predictive safety filter."""
    q_grid = np.asarray(q_grid_db, dtype=float)
    contribution = np.asarray(
        contribution_upper_w,
        dtype=float,
    )
    allowance = np.asarray(allowance_w, dtype=float)
    application_envelope = np.asarray(
        application_envelope_w,
        dtype=float,
    )
    envelope = np.asarray(command_envelope_w, dtype=float)
    average = np.asarray(
        moving_average_initial_rate,
        dtype=float,
    ).copy()
    floors = np.asarray(
        required_floor_by_interval,
        dtype=float,
    )
    if len(states) != len(contribution):
        raise ValueError("states and contributions must align")
    if application_envelope.shape != contribution.shape:
        raise ValueError("application envelope has the wrong shape")
    if envelope.shape != contribution.shape:
        raise ValueError("command envelope has the wrong shape")
    if allowance.shape != (len(states),):
        raise ValueError("allowance has the wrong shape")
    if floors.shape != (len(states), 228):
        raise ValueError("floor schedule has the wrong shape")

    # The current prototype uses a constant normalized allowance. The dataset
    # has a constant allowance over the pass.
    if not np.allclose(
        allowance,
        allowance[0],
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError("varying allowances are not implemented")

    command = np.empty(
        (len(states), 57, 2),
        dtype=float,
    )
    applied = np.empty_like(command)
    feasible = np.ones(len(states), dtype=bool)
    fail_safe = np.zeros(len(states), dtype=bool)
    delivered_total = np.empty(
        (len(states), 228),
        dtype=float,
    )
    delivered_protected = np.empty_like(delivered_total)
    average_trace = np.empty_like(delivered_total)
    build_seconds = np.empty(len(states), dtype=float)
    drop_set = {
        int(value)
        for value in fail_safe_drop_command_indices
    }

    # The command selected before the pass is applied during interval zero.
    # It must therefore satisfy the application envelope at interval zero,
    # not the delay-shifted command envelope for command index zero.
    initial_reference = np.zeros(
        (57, 2),
        dtype=float,
    )
    initial_cost, _audit = build_online_moving_pf_cost_grid(
        q_grid,
        states[0],
        initial_reference,
        average,
        eligible_user,
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
    preload, ratio, ok, _price = initial_allocator.solve(
        application_envelope[0]
    )
    if not ok or ratio > 1.0 + 1e-10:
        raise RuntimeError("predictive preload is infeasible")

    previous_command = preload.copy()
    for index, state in enumerate(states):
        source = index - int(delay_intervals)
        applied[index] = (
            command[source]
            if source >= 0
            else preload
        )
        total_rate, protected_rate = (
            exact_user_rates_for_action(
                applied[index],
                state,
                serving_bs_index,
                serving_stream_index,
                protected_noise_w,
                protected_weight,
            )
        )
        delivered_total[index] = total_rate
        delivered_protected[index] = protected_rate

        # Exponential moving average is updated for all users; inactive users
        # receive zero instantaneous rate and naturally gain future PF weight.
        average = (
            (1.0 - float(averaging_alpha)) * average
            + float(averaging_alpha) * total_rate
        )
        average_trace[index] = average

        application_index = min(
            index + int(delay_intervals),
            len(states) - 1,
        )
        reference_q = applied[index]
        import time

        started = time.perf_counter()
        cost, _audit = build_online_moving_pf_cost_grid(
            q_grid,
            states[application_index],
            reference_q,
            average,
            eligible_user,
            floors[application_index],
            serving_bs_index,
            serving_stream_index,
            protected_noise_w,
            protected_weight,
            averaging_alpha,
            epsilon_bps_hz,
        )
        build_seconds[index] = (
            time.perf_counter() - started
        )
        allocator = PriceAllocator(
            q_grid,
            cost,
            float(allowance[index]),
        )

        if index in drop_set:
            candidate = np.minimum(
                previous_command
                + float(slew_db_per_update),
                float(maximum_action_db),
            )
            candidate_ratio = float(
                (
                    envelope[index]
                    * np.power(
                        10.0,
                        -candidate / 10.0,
                    )
                ).sum()
                / allowance[index]
            )
            if candidate_ratio > 1.0 + 1e-10:
                raise RuntimeError(
                    "ramp-to-safe fail-safe is infeasible"
                )
            command[index] = candidate
            feasible[index] = True
            fail_safe[index] = True
        else:
            action, _ratio, ok, _price = allocator.solve(
                envelope[index],
                previous_q_db=previous_command,
                slew_db=slew_db_per_update,
            )
            command[index] = action
            feasible[index] = ok
        previous_command = command[index]

    nominal_ratio = evaluate_interval_upper_ratio(
        contribution,
        applied,
        allowance,
    )
    return OnlineControllerRun(
        command_db=command,
        applied_db=applied,
        command_feasible=feasible,
        fail_safe_used=fail_safe,
        upper_interval_ratio=nominal_ratio,
        nominal_interval_ratio=nominal_ratio.copy(),
        delivered_total_rate=delivered_total,
        delivered_protected_rate=delivered_protected,
        moving_average_rate=average_trace,
        local_table_build_seconds=build_seconds,
        active_user_schedule=np.stack(
            [state.active_user for state in states],
            axis=0,
        ),
    )


def simulate_online_myopic_controller(
    q_grid_db: np.ndarray,
    states: Sequence[LoadState],
    contribution_w: np.ndarray,
    allowance_w: np.ndarray,
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
) -> OnlineControllerRun:
    """Sequential online moving-average PF delayed myopic controller."""
    q_grid = np.asarray(q_grid_db, dtype=float)
    contribution = np.asarray(contribution_w, dtype=float)
    allowance = np.asarray(allowance_w, dtype=float)
    average = np.asarray(
        moving_average_initial_rate,
        dtype=float,
    ).copy()
    floors = np.asarray(required_floor_by_interval, dtype=float)
    if not np.allclose(
        allowance,
        allowance[0],
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError("varying allowances are not implemented")

    command = np.empty(
        (len(states), 57, 2),
        dtype=float,
    )
    applied = np.empty_like(command)
    feasible = np.ones(len(states), dtype=bool)
    delivered_total = np.empty(
        (len(states), 228),
        dtype=float,
    )
    delivered_protected = np.empty_like(delivered_total)
    average_trace = np.empty_like(delivered_total)
    build_seconds = np.empty(len(states), dtype=float)

    initial_cost, _audit = build_online_moving_pf_cost_grid(
        q_grid,
        states[0],
        np.zeros((57, 2), dtype=float),
        average,
        eligible_user,
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
    preload, ratio, ok, _price = initial_allocator.solve(
        contribution[0]
    )
    if not ok or ratio > 1.0 + 1e-10:
        raise RuntimeError("myopic preload is infeasible")

    previous_command = preload.copy()
    for index, state in enumerate(states):
        source = index - int(delay_intervals)
        applied[index] = (
            command[source]
            if source >= 0
            else preload
        )
        total_rate, protected_rate = (
            exact_user_rates_for_action(
                applied[index],
                state,
                serving_bs_index,
                serving_stream_index,
                protected_noise_w,
                protected_weight,
            )
        )
        delivered_total[index] = total_rate
        delivered_protected[index] = protected_rate
        average = (
            (1.0 - float(averaging_alpha)) * average
            + float(averaging_alpha) * total_rate
        )
        average_trace[index] = average

        import time

        started = time.perf_counter()
        cost, _audit = build_online_moving_pf_cost_grid(
            q_grid,
            state,
            applied[index],
            average,
            eligible_user,
            floors[index],
            serving_bs_index,
            serving_stream_index,
            protected_noise_w,
            protected_weight,
            averaging_alpha,
            epsilon_bps_hz,
        )
        build_seconds[index] = time.perf_counter() - started
        allocator = PriceAllocator(
            q_grid,
            cost,
            float(allowance[index]),
        )
        action, _ratio, ok, _price = allocator.solve(
            contribution[index],
            previous_q_db=previous_command,
            slew_db=slew_db_per_update,
        )
        command[index] = action
        feasible[index] = ok
        previous_command = action

    ratio = evaluate_interval_upper_ratio(
        contribution,
        applied,
        allowance,
    )
    return OnlineControllerRun(
        command_db=command,
        applied_db=applied,
        command_feasible=feasible,
        fail_safe_used=np.zeros(len(states), dtype=bool),
        upper_interval_ratio=ratio,
        nominal_interval_ratio=ratio.copy(),
        delivered_total_rate=delivered_total,
        delivered_protected_rate=delivered_protected,
        moving_average_rate=average_trace,
        local_table_build_seconds=build_seconds,
        active_user_schedule=np.stack(
            [state.active_user for state in states],
            axis=0,
        ),
    )


def sequential_average_trace(
    delivered_total_rate: np.ndarray,
    initial_average_rate: np.ndarray,
    averaging_alpha: float,
) -> np.ndarray:
    """Compute exponential moving-average throughput for a rate trace."""
    delivered = np.asarray(delivered_total_rate, dtype=float)
    average = np.asarray(initial_average_rate, dtype=float).copy()
    if delivered.ndim != 2 or delivered.shape[1] != 228:
        raise ValueError("delivered rate must have shape [K,228]")
    trace = np.empty_like(delivered)
    for index in range(len(delivered)):
        average = (
            (1.0 - float(averaging_alpha)) * average
            + float(averaging_alpha) * delivered[index]
        )
        trace[index] = average
    return trace


def evaluate_actions_across_states(
    actions_db: np.ndarray,
    states: Sequence[LoadState],
    serving_bs_index: np.ndarray,
    serving_stream_index: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    initial_average_rate: np.ndarray,
    averaging_alpha: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate one interval action per load state and update PF averages."""
    actions = np.asarray(actions_db, dtype=float)
    if actions.shape != (len(states), 57, 2):
        raise ValueError("actions have the wrong shape")
    total = np.empty((len(states), 228), dtype=float)
    protected = np.empty_like(total)
    for index, state in enumerate(states):
        total[index], protected[index] = (
            exact_user_rates_for_action(
                actions[index],
                state,
                serving_bs_index,
                serving_stream_index,
                protected_noise_w,
                protected_weight,
            )
        )
    average = sequential_average_trace(
        total,
        initial_average_rate,
        averaging_alpha,
    )
    return total, protected, average


def finite_pass_dynamic_certificate(
    command_db: np.ndarray,
    applied_db: np.ndarray,
    command_feasible: np.ndarray,
    application_envelope_w: np.ndarray,
    command_envelope_w: np.ndarray,
    upper_interval_ratio: np.ndarray,
    interval_allowance_w: np.ndarray,
    slew_db_per_update: float,
    maximum_action_db: float,
) -> dict[str, object]:
    """Check the corrected finite-pass theorem, including saturation.

    The recursively feasible candidate is exactly

        F(q) = min(q + rho, Q)

    and is checked against the next command envelope. This candidate-specific
    condition replaces the insufficient statement that an unrelated all-Q
    action is merely safe.
    """
    command = np.asarray(command_db, dtype=float)
    applied = np.asarray(applied_db, dtype=float)
    feasible = np.asarray(command_feasible, dtype=bool)
    application = np.asarray(
        application_envelope_w,
        dtype=float,
    )
    envelope = np.asarray(command_envelope_w, dtype=float)
    ratio = np.asarray(upper_interval_ratio, dtype=float)
    allowance = np.asarray(interval_allowance_w, dtype=float)
    if command.shape != envelope.shape:
        raise ValueError("command/envelope shapes must match")
    if applied.shape != command.shape:
        raise ValueError("applied command shape mismatch")
    if application.shape != command.shape:
        raise ValueError("application envelope shape mismatch")
    if allowance.shape != (len(command),):
        raise ValueError("allowance shape mismatch")

    attenuation_step = 10.0 ** (
        -float(slew_db_per_update) / 10.0
    )
    recurrence_excess = np.maximum(
        0.0,
        attenuation_step * application[1:]
        - application[:-1],
    )
    command_ratio = (
        envelope
        * np.power(10.0, -command / 10.0)
    ).sum(axis=(1, 2)) / allowance
    slew = (
        np.abs(np.diff(command, axis=0))
        if len(command) > 1
        else np.zeros((0, 57, 2), dtype=float)
    )
    candidate_ratios = []
    for index in range(len(command) - 1):
        candidate = np.minimum(
            command[index] + float(slew_db_per_update),
            float(maximum_action_db),
        )
        candidate_ratios.append(
            float(
                (
                    envelope[index + 1]
                    * np.power(
                        10.0,
                        -candidate / 10.0,
                    )
                ).sum()
                / allowance[index + 1]
            )
        )
    terminal_ratio = (
        application
        * 10.0 ** (-float(maximum_action_db) / 10.0)
    ).sum(axis=(1, 2)) / allowance

    checks = {
        "full_horizon_recurrence": bool(
            recurrence_excess.size == 0
            or float(recurrence_excess.max()) <= 1e-24
        ),
        "all_commands_envelope_feasible": bool(
            np.all(command_ratio <= 1.0 + 1e-10)
        ),
        "all_upper_intervals_safe": bool(
            np.all(ratio <= 1.0 + 1e-10)
        ),
        "all_solver_commands_feasible": bool(
            np.all(feasible)
        ),
        "slew_constraint": bool(
            slew.size == 0
            or float(slew.max())
            <= float(slew_db_per_update) + 1e-12
        ),
        "candidate_specific_saturation_feasibility": bool(
            not candidate_ratios
            or max(candidate_ratios) <= 1.0 + 1e-10
        ),
        "maximum_action_terminal_safety": bool(
            np.all(terminal_ratio <= 1.0 + 1e-10)
        ),
    }
    return {
        "status": (
            "PASS_CORRECTED_FINITE_PASS_DYNAMIC_CERTIFICATE"
            if all(checks.values())
            else "FAIL_CORRECTED_FINITE_PASS_DYNAMIC_CERTIFICATE"
        ),
        "checks": checks,
        "maximum_recurrence_excess_w": float(
            recurrence_excess.max()
            if recurrence_excess.size
            else 0.0
        ),
        "maximum_command_envelope_ratio": float(
            command_ratio.max()
        ),
        "maximum_upper_interval_ratio": float(ratio.max()),
        "maximum_command_slew_db": float(
            slew.max() if slew.size else 0.0
        ),
        "maximum_candidate_specific_ratio": float(
            max(candidate_ratios)
            if candidate_ratios
            else 0.0
        ),
        "maximum_terminal_ratio": float(
            terminal_ratio.max()
        ),
    }


def exact_second_safety_ratio_dynamic(
    kappa_time_sector: np.ndarray,
    states: Sequence[LoadState],
    applied_interval_q_db: np.ndarray,
    update_interval_s: int,
    allowance_second_w: np.ndarray,
    coupling_upper_margin_db: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate nominal and upper incumbent ratios at every one-second sample."""
    kappa = np.asarray(kappa_time_sector, dtype=float)
    action = np.asarray(applied_interval_q_db, dtype=float)
    allowance = np.asarray(allowance_second_w, dtype=float)
    if kappa.shape != (len(allowance), 57):
        raise ValueError("kappa/allowance shape mismatch")
    if action.shape != (len(states), 57, 2):
        raise ValueError("applied action shape mismatch")
    factor = 10.0 ** (
        float(coupling_upper_margin_db) / 10.0
    )
    nominal = np.empty(len(kappa), dtype=float)
    upper = np.empty(len(kappa), dtype=float)
    for second in range(len(kappa)):
        interval = min(
            second // int(update_interval_s),
            len(states) - 1,
        )
        leakage = states[interval].mode_leakage_w
        power_scale = np.power(
            10.0,
            -action[interval] / 10.0,
        )
        value = float(
            (
                kappa[second, :, None]
                * leakage
                * power_scale
            ).sum()
            / allowance[second]
        )
        nominal[second] = value
        upper[second] = factor * value
    return upper, nominal
