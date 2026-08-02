"""Robust delayed reachability safety and virtual-queue baselines."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from fr3_cbf.constrained_pf_safety import PriceAllocator


@dataclass(frozen=True)
class RobustRun:
    command_db: np.ndarray
    applied_db: np.ndarray
    command_feasible: np.ndarray
    envelope_ratio: np.ndarray
    upper_safety_ratio: np.ndarray
    nominal_safety_ratio: np.ndarray
    fail_safe_used: np.ndarray
    application_envelope_w: np.ndarray
    command_envelope_w: np.ndarray
    preloaded_action_db: np.ndarray


@dataclass(frozen=True)
class VirtualQueueRun:
    command_db: np.ndarray
    applied_db: np.ndarray
    safety_ratio: np.ndarray
    queue: np.ndarray


def interval_mode_contributions(
    kappa_time_sector: np.ndarray,
    nominal_mode_leakage_w: np.ndarray,
    allowance_w: np.ndarray,
    update_interval_s: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return interval-max mode contributions, allowances, and lengths."""
    kappa = np.asarray(kappa_time_sector, dtype=float)
    leakage = np.asarray(nominal_mode_leakage_w, dtype=float)
    allowance = np.asarray(allowance_w, dtype=float)
    if kappa.shape[1] != 57 or leakage.shape != (57, 2):
        raise ValueError("unexpected kappa or leakage shape")
    if allowance.shape != (len(kappa),) or np.any(allowance <= 0):
        raise ValueError("invalid allowance")
    if update_interval_s <= 0:
        raise ValueError("update interval must be positive")

    second = kappa[:, :, None] * leakage[None, :, :]
    rows = []
    interval_allowance = []
    lengths = []
    for start in range(0, len(second), update_interval_s):
        stop = min(start + update_interval_s, len(second))
        rows.append(np.max(second[start:stop], axis=0))
        interval_allowance.append(float(np.min(allowance[start:stop])))
        lengths.append(stop - start)
    return (
        np.asarray(rows, dtype=float),
        np.asarray(interval_allowance, dtype=float),
        np.asarray(lengths, dtype=np.int64),
    )


def full_horizon_reachability_envelope(
    upper_contribution_w: np.ndarray,
    delay_intervals: int,
    slew_db_per_update: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build application, command, and preloaded full-horizon envelopes."""
    contribution = np.asarray(upper_contribution_w, dtype=float)
    if contribution.ndim != 3 or contribution.shape[1:] != (57, 2):
        raise ValueError("upper_contribution_w must have shape [K,57,2]")
    if delay_intervals < 0 or slew_db_per_update <= 0:
        raise ValueError("invalid delay or slew")
    attenuation_step = 10.0 ** (-float(slew_db_per_update) / 10.0)
    application = np.empty_like(contribution)
    application[-1] = contribution[-1]
    for index in range(len(contribution) - 2, -1, -1):
        application[index] = np.maximum(
            contribution[index],
            attenuation_step * application[index + 1],
        )
    command = np.empty_like(contribution)
    for index in range(len(contribution)):
        command[index] = application[
            min(index + int(delay_intervals), len(application) - 1)
        ]
    return application, command, application[0].copy()


def simulate_full_horizon_predictive(
    allocator: PriceAllocator,
    nominal_contribution_w: np.ndarray,
    interval_allowance_w: np.ndarray,
    delay_intervals: int,
    slew_db_per_update: float,
    coupling_upper_margin_db: float,
    fail_safe_drop_command_indices: tuple[int, ...] = (),
) -> RobustRun:
    """Run the recursively feasible full-horizon robust safety filter."""
    nominal = np.asarray(nominal_contribution_w, dtype=float)
    allowance = np.asarray(interval_allowance_w, dtype=float)
    if allowance.shape != (len(nominal),):
        raise ValueError("interval allowance has the wrong shape")
    if not np.allclose(allowance, allowance[0], rtol=0.0, atol=0.0):
        raise ValueError(
            "the current allocator uses a constant allowance; "
            "normalize contributions before extending to varying allowances"
        )
    upper = nominal * 10.0 ** (float(coupling_upper_margin_db) / 10.0)
    application_envelope, command_envelope, preload_envelope = (
        full_horizon_reachability_envelope(
            upper,
            delay_intervals=delay_intervals,
            slew_db_per_update=slew_db_per_update,
        )
    )
    preload, preload_ratio, preload_ok, _ = allocator.solve(
        preload_envelope
    )
    if not preload_ok or preload_ratio > 1.0 + 1e-10:
        raise RuntimeError("preloaded robust action is infeasible")

    command = np.empty((len(nominal), 57, 2), dtype=float)
    feasible = np.ones(len(nominal), dtype=bool)
    envelope_ratio = np.empty(len(nominal), dtype=float)
    fail_safe = np.zeros(len(nominal), dtype=bool)
    previous = preload.copy()
    drop_set = {int(value) for value in fail_safe_drop_command_indices}

    for index in range(len(nominal)):
        if index in drop_set:
            action = np.minimum(
                previous + float(slew_db_per_update),
                allocator.q_grid[-1],
            )
            ratio = float(
                (
                    command_envelope[index]
                    * np.power(10.0, -action / 10.0)
                ).sum()
                / allocator.allowance
            )
            ok = ratio <= 1.0 + 1e-10
            fail_safe[index] = True
        else:
            action, ratio, ok, _ = allocator.solve(
                command_envelope[index],
                previous_q_db=previous,
                slew_db=slew_db_per_update,
            )
        command[index] = action
        feasible[index] = ok
        envelope_ratio[index] = ratio
        previous = action

    applied = np.empty_like(command)
    for index in range(len(command)):
        source = index - int(delay_intervals)
        applied[index] = command[source] if source >= 0 else preload

    upper_ratio = (
        upper * np.power(10.0, -applied / 10.0)
    ).sum(axis=(1, 2)) / allowance
    nominal_ratio = (
        nominal * np.power(10.0, -applied / 10.0)
    ).sum(axis=(1, 2)) / allowance
    return RobustRun(
        command_db=command,
        applied_db=applied,
        command_feasible=feasible,
        envelope_ratio=envelope_ratio,
        upper_safety_ratio=upper_ratio,
        nominal_safety_ratio=nominal_ratio,
        fail_safe_used=fail_safe,
        application_envelope_w=application_envelope,
        command_envelope_w=command_envelope,
        preloaded_action_db=preload,
    )


def choose_with_external_price(
    allocator: PriceAllocator,
    contribution_w: np.ndarray,
    price: float,
    previous_q_db: np.ndarray,
    slew_db_per_update: float,
) -> np.ndarray:
    """Choose independent local actions for a supplied virtual-queue price."""
    contribution = np.asarray(contribution_w, dtype=float)
    previous = np.asarray(previous_q_db, dtype=float)
    grid = allocator.q_grid
    scale = allocator.power_scale
    normalized = (
        contribution[:, 0, None, None] * scale[None, :, None]
        + contribution[:, 1, None, None] * scale[None, None, :]
    ) / allocator.allowance
    valid_1 = (
        np.abs(grid[None, :] - previous[:, 0, None])
        <= float(slew_db_per_update) + 1e-12
    )
    valid_2 = (
        np.abs(grid[None, :] - previous[:, 1, None])
        <= float(slew_db_per_update) + 1e-12
    )
    mask = valid_1[:, :, None] & valid_2[:, None, :]
    objective = np.where(
        mask,
        allocator.cost + float(price) * normalized,
        np.inf,
    )
    count = len(grid)
    flat = objective.reshape(57, -1).argmin(axis=1)
    first = flat // count
    second = flat % count
    return np.column_stack([grid[first], grid[second]])


def simulate_virtual_queue(
    allocator: PriceAllocator,
    contribution_w: np.ndarray,
    interval_allowance_w: np.ndarray,
    delay_intervals: int,
    slew_db_per_update: float,
    price_gain: float,
) -> VirtualQueueRun:
    """Long-term virtual-queue baseline with no hard instantaneous guarantee."""
    contribution = np.asarray(contribution_w, dtype=float)
    allowance = np.asarray(interval_allowance_w, dtype=float)
    if price_gain <= 0:
        raise ValueError("price_gain must be positive")
    preload, _ratio, ok, _price = allocator.solve(contribution[0])
    if not ok:
        raise RuntimeError("virtual-queue initial action is infeasible")

    command = np.empty((len(contribution), 57, 2), dtype=float)
    applied = np.empty_like(command)
    ratio = np.empty(len(contribution), dtype=float)
    queue = np.zeros(len(contribution) + 1, dtype=float)
    previous = preload.copy()

    for index in range(len(contribution)):
        command[index] = choose_with_external_price(
            allocator,
            contribution[index],
            price=float(price_gain) * queue[index],
            previous_q_db=previous,
            slew_db_per_update=slew_db_per_update,
        )
        previous = command[index]
        source = index - int(delay_intervals)
        applied[index] = command[source] if source >= 0 else preload
        ratio[index] = float(
            (
                contribution[index]
                * np.power(10.0, -applied[index] / 10.0)
            ).sum()
            / allowance[index]
        )
        queue[index + 1] = max(
            0.0,
            queue[index] + ratio[index] - 1.0,
        )
    return VirtualQueueRun(command, applied, ratio, queue)


def theorem_certificate(
    run: RobustRun,
    interval_allowance_w: np.ndarray,
    slew_db_per_update: float,
    maximum_action_db: float,
) -> dict[str, object]:
    """Machine-check the finite-pass robust reachability theorem conditions."""
    allowance = np.asarray(interval_allowance_w, dtype=float)
    attenuation_step = 10.0 ** (-float(slew_db_per_update) / 10.0)
    recurrence_excess = np.maximum(
        0.0,
        attenuation_step * run.application_envelope_w[1:]
        - run.application_envelope_w[:-1],
    )
    command_slew = (
        np.abs(np.diff(run.command_db, axis=0))
        if len(run.command_db) > 1
        else np.zeros((0, 57, 2))
    )

    candidate_ratios = []
    for index in range(len(run.command_db) - 1):
        candidate = np.minimum(
            run.command_db[index] + float(slew_db_per_update),
            float(maximum_action_db),
        )
        candidate_ratios.append(
            float(
                (
                    run.command_envelope_w[index + 1]
                    * np.power(10.0, -candidate / 10.0)
                ).sum()
                / allowance[index + 1]
            )
        )
    terminal_ratio = (
        run.application_envelope_w
        * 10.0 ** (-float(maximum_action_db) / 10.0)
    ).sum(axis=(1, 2)) / allowance

    checks = {
        "full_horizon_recurrence": bool(
            float(recurrence_excess.max(initial=0.0)) <= 1e-24
        ),
        "all_commands_envelope_feasible": bool(
            np.all(run.envelope_ratio <= 1.0 + 1e-10)
        ),
        "all_upper_bound_intervals_safe": bool(
            np.all(run.upper_safety_ratio <= 1.0 + 1e-10)
        ),
        "all_commands_solver_feasible": bool(
            np.all(run.command_feasible)
        ),
        "slew_constraint": bool(
            command_slew.size == 0
            or float(command_slew.max()) <= (
                float(slew_db_per_update) + 1e-12
            )
        ),
        "terminal_maximum_action_safe": bool(
            np.all(terminal_ratio <= 1.0 + 1e-10)
        ),
        "fail_safe_candidate_recursively_feasible": bool(
            not candidate_ratios
            or max(candidate_ratios) <= 1.0 + 1e-10
        ),
    }
    return {
        "status": (
            "PASS_FINITE_PASS_ROBUST_REACHABILITY_CERTIFICATE"
            if all(checks.values())
            else "FAIL_FINITE_PASS_ROBUST_REACHABILITY_CERTIFICATE"
        ),
        "checks": checks,
        "maximum_recurrence_excess_w": float(
            recurrence_excess.max(initial=0.0)
        ),
        "maximum_envelope_ratio": float(run.envelope_ratio.max()),
        "maximum_upper_safety_ratio": float(
            run.upper_safety_ratio.max()
        ),
        "maximum_command_slew_db": float(
            command_slew.max() if command_slew.size else 0.0
        ),
        "maximum_fail_safe_candidate_ratio": float(
            max(candidate_ratios) if candidate_ratios else 0.0
        ),
        "maximum_terminal_action_ratio": float(terminal_ratio.max()),
        "fail_safe_use_count": int(run.fail_safe_used.sum()),
    }
