"""Constrained proportional-fair distributed safety-controller prototypes.

This module supports a one-seed milestone. The predictive method is a
finite-horizon reachability filter. It is not yet a formally proved CBF.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class ControllerRun:
    command_db: np.ndarray
    applied_db: np.ndarray
    feasible_command: np.ndarray
    interval_mode_contribution_w: np.ndarray


def action_grid(minimum_db: int, maximum_db: int, step_db: int) -> np.ndarray:
    if step_db <= 0 or maximum_db < minimum_db:
        raise ValueError("invalid action grid")
    values = np.arange(
        minimum_db,
        maximum_db + step_db,
        step_db,
        dtype=float,
    )
    if values[-1] != maximum_db:
        raise ValueError("action grid does not end at maximum_db")
    return values


def exact_user_rates(
    q_db: np.ndarray,
    amp_perpendicular: np.ndarray,
    amp_pol1: np.ndarray,
    amp_pol2: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    other_weighted_rate: np.ndarray,
    protected_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    q = np.asarray(q_db, dtype=float)
    if q.shape != (57, 2):
        raise ValueError("q_db must have shape [57,2]")
    scale = np.power(10.0, -q / 20.0)
    amplitude = (
        np.asarray(amp_perpendicular)
        + scale[None, :, 0, None] * np.asarray(amp_pol1)
        + scale[None, :, 1, None] * np.asarray(amp_pol2)
    )
    power = np.abs(amplitude) ** 2
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    desired = power[np.arange(len(serving)), serving, stream]
    total = power.sum(axis=(1, 2))
    protected_rate = np.log2(
        1.0
        + desired
        / (total - desired + float(protected_noise_w))
    )
    total_rate = (
        np.asarray(other_weighted_rate, dtype=float)
        + float(protected_weight) * protected_rate
    )
    return total_rate, protected_rate


def build_local_constrained_pf_cost_grid(
    q_grid_db: np.ndarray,
    nominal_total_rate: np.ndarray,
    eligible_user: np.ndarray,
    required_floor_rate: np.ndarray,
    amp_perpendicular: np.ndarray,
    amp_pol1: np.ndarray,
    amp_pol2: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    other_weighted_rate: np.ndarray,
    protected_weight: float,
    epsilon_bps_hz: float,
) -> tuple[np.ndarray, dict[str, object]]:
    """Build one local two-mode lexicographic cost table per sector.

    Each sector evaluates its four served users while all other sector actions
    remain nominal. The table records eligible-user floor violations,
    normalized floor shortfall, and proportional-fair loss. A globally bounded
    scalarization preserves this priority among candidate action assignments:

      violation count -> normalized shortfall -> PF loss.

    Incumbent safety remains a separate hard aggregate constraint handled by
    the scalar interference price. Exact full-network floor metrics are
    re-evaluated after every controller action.
    """
    q_grid = np.asarray(q_grid_db, dtype=float)
    nominal = np.asarray(nominal_total_rate, dtype=float)
    eligible = np.asarray(eligible_user, dtype=bool)
    floor = np.asarray(required_floor_rate, dtype=float)
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    a0 = np.asarray(amp_perpendicular)
    a1 = np.asarray(amp_pol1)
    a2 = np.asarray(amp_pol2)
    if q_grid.ndim != 1 or np.any(np.diff(q_grid) <= 0):
        raise ValueError("q_grid_db must be strictly increasing")
    if nominal.shape != (228,) or eligible.shape != (228,) or floor.shape != (228,):
        raise ValueError("user vectors must have shape [228]")
    if epsilon_bps_hz <= 0:
        raise ValueError("epsilon must be positive")

    scale = np.power(10.0, -q_grid / 20.0)
    nominal_amplitude = a0 + a1 + a2
    shape = (57, len(q_grid), len(q_grid))
    violation = np.empty(shape, dtype=np.int8)
    shortfall = np.empty(shape, dtype=np.float64)
    pf_loss = np.empty(shape, dtype=np.float64)
    eligible_per_sector: list[int] = []

    for bs in range(57):
        users = np.flatnonzero(serving == bs)
        if len(users) != 4:
            raise ValueError(f"BS {bs} does not serve exactly four users")
        eligible_local = eligible[users]
        eligible_per_sector.append(int(eligible_local.sum()))

        local_base = nominal_amplitude[users]
        own_nominal = local_base[:, bs, :]
        other_sector_power = (
            np.abs(local_base) ** 2
        ).sum(axis=(1, 2)) - (
            np.abs(own_nominal) ** 2
        ).sum(axis=1)

        own = (
            a0[users, bs, :][None, None, :, :]
            + scale[:, None, None, None]
            * a1[users, bs, :][None, None, :, :]
            + scale[None, :, None, None]
            * a2[users, bs, :][None, None, :, :]
        )
        own_power = np.abs(own) ** 2
        total_power = (
            other_sector_power[None, None, :]
            + own_power.sum(axis=3)
        )
        desired = own_power[:, :, np.arange(4), stream[users]]
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
            np.asarray(other_weighted_rate, dtype=float)[users][None, None, :]
            + float(protected_weight) * protected_rate
        )

        if eligible_local.any():
            local_floor = floor[users][eligible_local]
            eligible_rate = total_rate[:, :, eligible_local]
            violation[bs] = (
                eligible_rate < local_floor[None, None, :] - 1e-12
            ).sum(axis=2)
            shortfall[bs] = np.maximum(
                0.0,
                (
                    local_floor[None, None, :]
                    - eligible_rate
                )
                / local_floor[None, None, :],
            ).sum(axis=2)
            baseline_pf = float(
                np.log(
                    nominal[users][eligible_local]
                    + float(epsilon_bps_hz)
                ).sum()
            )
            pf_loss[bs] = (
                baseline_pf
                - np.log(
                    eligible_rate + float(epsilon_bps_hz)
                ).sum(axis=2)
            )
        else:
            violation[bs] = 0
            shortfall[bs] = 0.0
            pf_loss[bs] = 0.0

    # Global scalarization weights are derived from exact finite table ranges.
    # Hence one additional violation dominates every possible global shortfall
    # and PF improvement, and one additional unit of normalized shortfall
    # dominates every possible global PF improvement.
    pf_shifted = np.empty_like(pf_loss)
    pf_range_by_sector = np.empty(57, dtype=float)
    for bs in range(57):
        local_min = float(pf_loss[bs].min())
        pf_shifted[bs] = pf_loss[bs] - local_min
        pf_range_by_sector[bs] = (
            float(pf_loss[bs].max()) - local_min
        )
    total_pf_range = float(pf_range_by_sector.sum())
    eligible_count = int(eligible.sum())
    shortfall_weight = total_pf_range + 1.0
    violation_weight = (
        eligible_count * shortfall_weight
        + total_pf_range
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
        + pf_shifted
        + tie_break
    )

    audit = {
        "eligible_user_count": eligible_count,
        "coverage_limited_user_count": int((~eligible).sum()),
        "eligible_user_count_by_sector": eligible_per_sector,
        "violation_weight": violation_weight,
        "shortfall_weight": shortfall_weight,
        "total_pf_range": total_pf_range,
        "maximum_candidate_violation_count": int(violation.max()),
        "maximum_candidate_normalized_shortfall": float(shortfall.max()),
        "minimum_candidate_pf_loss": float(pf_loss.min()),
        "maximum_candidate_pf_loss": float(pf_loss.max()),
        "maximum_scalarized_cost": float(cost.max()),
        "sectors_with_any_local_floor_violating_candidate": int(
            np.sum(violation.reshape(57, -1).max(axis=1) > 0)
        ),
        "interpretation": (
            "Local tables are frozen around nominal other-sector actions; "
            "all final controller actions receive an exact full-network "
            "floor/outage audit."
        ),
    }
    return cost, audit


def interval_mode_contributions(
    kappa_time_sector: np.ndarray,
    nominal_mode_leakage_w: np.ndarray,
    update_interval_s: int,
) -> tuple[np.ndarray, np.ndarray]:
    kappa = np.asarray(kappa_time_sector, dtype=float)
    leakage = np.asarray(nominal_mode_leakage_w, dtype=float)
    if kappa.shape[1] != 57 or leakage.shape != (57, 2):
        raise ValueError("unexpected kappa or leakage shape")
    if update_interval_s <= 0:
        raise ValueError("update interval must be positive")

    second = kappa[:, :, None] * leakage[None, :, :]
    rows = []
    lengths = []
    for start in range(0, len(second), update_interval_s):
        stop = min(start + update_interval_s, len(second))
        rows.append(np.max(second[start:stop], axis=0))
        lengths.append(stop - start)
    return np.asarray(rows), np.asarray(lengths, dtype=np.int64)


class PriceAllocator:
    """Scalar-price decomposition over local two-mode action tables."""

    def __init__(
        self,
        q_grid_db: np.ndarray,
        local_cost: np.ndarray,
        allowance_w: float,
    ) -> None:
        self.q_grid = np.asarray(q_grid_db, dtype=float)
        self.power_scale = np.power(10.0, -self.q_grid / 10.0)
        self.cost = np.asarray(local_cost, dtype=float)
        self.allowance = float(allowance_w)
        if self.cost.shape != (
            57,
            len(self.q_grid),
            len(self.q_grid),
        ):
            raise ValueError("local_cost has the wrong shape")
        if self.allowance <= 0:
            raise ValueError("allowance must be positive")

    def solve(
        self,
        mode_contribution_w: np.ndarray,
        previous_q_db: np.ndarray | None = None,
        slew_db: float | None = None,
    ) -> tuple[np.ndarray, float, bool, float]:
        contribution = np.asarray(mode_contribution_w, dtype=float)
        if contribution.shape != (57, 2):
            raise ValueError("mode contribution must have shape [57,2]")
        normalized = (
            contribution[:, 0, None, None]
            * self.power_scale[None, :, None]
            + contribution[:, 1, None, None]
            * self.power_scale[None, None, :]
        ) / self.allowance

        if previous_q_db is None:
            mask = np.ones_like(normalized, dtype=bool)
        else:
            if slew_db is None or slew_db <= 0:
                raise ValueError("a positive slew is required")
            previous = np.asarray(previous_q_db, dtype=float)
            if previous.shape != (57, 2):
                raise ValueError("previous_q_db has the wrong shape")
            valid_1 = (
                np.abs(
                    self.q_grid[None, :]
                    - previous[:, 0, None]
                )
                <= float(slew_db) + 1e-12
            )
            valid_2 = (
                np.abs(
                    self.q_grid[None, :]
                    - previous[:, 1, None]
                )
                <= float(slew_db) + 1e-12
            )
            mask = valid_1[:, :, None] & valid_2[:, None, :]
            if np.any(mask.sum(axis=(1, 2)) == 0):
                raise RuntimeError("a sector has no slew-feasible action")

        count = len(self.q_grid)

        def choose(price: float) -> tuple[float, np.ndarray, np.ndarray]:
            objective = np.where(
                mask,
                self.cost + float(price) * normalized,
                np.inf,
            )
            flat = objective.reshape(57, -1).argmin(axis=1)
            first = flat // count
            second = flat % count
            ratio = float(
                normalized[
                    np.arange(57),
                    first,
                    second,
                ].sum()
            )
            return ratio, first, second

        ratio, first, second = choose(0.0)
        if ratio <= 1.0 + 1e-12:
            action = np.column_stack(
                [self.q_grid[first], self.q_grid[second]]
            )
            return action, ratio, True, 0.0

        high = 1.0
        while high < 1e30:
            ratio, first, second = choose(high)
            if ratio <= 1.0:
                break
            high *= 10.0

        if ratio > 1.0:
            safest = np.where(mask, normalized, np.inf)
            flat = safest.reshape(57, -1).argmin(axis=1)
            first = flat // count
            second = flat % count
            action = np.column_stack(
                [self.q_grid[first], self.q_grid[second]]
            )
            ratio = float(
                normalized[
                    np.arange(57),
                    first,
                    second,
                ].sum()
            )
            return action, ratio, False, math.inf

        low = 0.0
        for _ in range(40):
            middle = 0.5 * (low + high)
            middle_ratio, _, _ = choose(middle)
            if middle_ratio <= 1.0:
                high = middle
            else:
                low = middle
        ratio, first, second = choose(high)
        action = np.column_stack(
            [self.q_grid[first], self.q_grid[second]]
        )
        return action, ratio, True, high


def predictive_effective_contribution(
    interval_contribution_w: np.ndarray,
    command_index: int,
    delay_intervals: int,
    slew_db_per_update: float,
    horizon_intervals: int,
) -> np.ndarray:
    contribution = np.asarray(interval_contribution_w, dtype=float)
    effective = np.zeros((57, 2), dtype=float)
    for horizon in range(horizon_intervals + 1):
        future = min(
            command_index + delay_intervals + horizon,
            len(contribution) - 1,
        )
        reachability_scale = 10.0 ** (
            -float(slew_db_per_update) * horizon / 10.0
        )
        effective = np.maximum(
            effective,
            contribution[future] * reachability_scale,
        )
    return effective


def _initial_safe_action(
    allocator: PriceAllocator,
    contribution_w: np.ndarray,
) -> np.ndarray:
    action, _ratio, feasible, _price = allocator.solve(
        contribution_w
    )
    if not feasible:
        raise RuntimeError("initial action is infeasible")
    return action


def simulate_myopic(
    allocator: PriceAllocator,
    interval_contribution_w: np.ndarray,
    delay_intervals: int,
    slew_db_per_update: float,
) -> ControllerRun:
    contribution = np.asarray(interval_contribution_w, dtype=float)
    initial = _initial_safe_action(allocator, contribution[0])
    command = np.empty((len(contribution), 57, 2), dtype=float)
    feasible = np.ones(len(contribution), dtype=bool)
    previous = initial.copy()
    for index in range(len(contribution)):
        action, _ratio, ok, _price = allocator.solve(
            contribution[index],
            previous_q_db=previous,
            slew_db=slew_db_per_update,
        )
        command[index] = action
        feasible[index] = ok
        previous = action
    applied = np.empty_like(command)
    for index in range(len(command)):
        source = index - delay_intervals
        applied[index] = command[source] if source >= 0 else initial
    return ControllerRun(command, applied, feasible, contribution)


def simulate_predictive_reachability(
    allocator: PriceAllocator,
    interval_contribution_w: np.ndarray,
    delay_intervals: int,
    slew_db_per_update: float,
    horizon_intervals: int,
) -> ControllerRun:
    contribution = np.asarray(interval_contribution_w, dtype=float)
    initial_effective = np.maximum(
        contribution[0],
        predictive_effective_contribution(
            contribution,
            command_index=0,
            delay_intervals=delay_intervals,
            slew_db_per_update=slew_db_per_update,
            horizon_intervals=horizon_intervals,
        ),
    )
    initial = _initial_safe_action(allocator, initial_effective)
    command = np.empty((len(contribution), 57, 2), dtype=float)
    feasible = np.ones(len(contribution), dtype=bool)
    previous = initial.copy()
    for index in range(len(contribution)):
        effective = predictive_effective_contribution(
            contribution,
            command_index=index,
            delay_intervals=delay_intervals,
            slew_db_per_update=slew_db_per_update,
            horizon_intervals=horizon_intervals,
        )
        action, _ratio, ok, _price = allocator.solve(
            effective,
            previous_q_db=previous,
            slew_db=slew_db_per_update,
        )
        command[index] = action
        feasible[index] = ok
        previous = action
    applied = np.empty_like(command)
    for index in range(len(command)):
        source = index - delay_intervals
        applied[index] = command[source] if source >= 0 else initial
    return ControllerRun(command, applied, feasible, contribution)


def second_safety_ratio(
    kappa_time_sector: np.ndarray,
    nominal_mode_leakage_w: np.ndarray,
    applied_interval_q_db: np.ndarray,
    update_interval_s: int,
    allowance_w: np.ndarray,
) -> np.ndarray:
    kappa = np.asarray(kappa_time_sector, dtype=float)
    leakage = np.asarray(nominal_mode_leakage_w, dtype=float)
    action = np.asarray(applied_interval_q_db, dtype=float)
    allowance = np.asarray(allowance_w, dtype=float)
    result = np.empty(len(kappa), dtype=float)
    for second in range(len(kappa)):
        interval = min(second // update_interval_s, len(action) - 1)
        result[second] = float(
            (
                kappa[second, :, None]
                * leakage
                * np.power(10.0, -action[interval] / 10.0)
            ).sum()
            / allowance[second]
        )
    return result


def evaluate_interval_actions(
    applied_q_db: np.ndarray,
    interval_lengths: np.ndarray,
    nominal_total_rate: np.ndarray,
    nominal_protected_rate: np.ndarray,
    eligible_user: np.ndarray,
    required_floor_rate: np.ndarray,
    indoor_user: np.ndarray,
    amp_perpendicular: np.ndarray,
    amp_pol1: np.ndarray,
    amp_pol2: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    other_weighted_rate: np.ndarray,
    protected_weight: float,
    epsilon_bps_hz: float,
) -> dict[str, object]:
    action = np.asarray(applied_q_db, dtype=float)
    lengths = np.asarray(interval_lengths, dtype=np.int64)
    nominal_total = np.asarray(nominal_total_rate, dtype=float)
    nominal_protected = np.asarray(
        nominal_protected_rate,
        dtype=float,
    )
    eligible = np.asarray(eligible_user, dtype=bool)
    floor = np.asarray(required_floor_rate, dtype=float)
    indoor = np.asarray(indoor_user, dtype=bool)

    total_rate = np.empty((len(action), 228), dtype=float)
    protected_rate = np.empty_like(total_rate)
    for index, value in enumerate(action):
        total_rate[index], protected_rate[index] = exact_user_rates(
            value,
            amp_perpendicular,
            amp_pol1,
            amp_pol2,
            serving_bs,
            serving_stream,
            protected_noise_w,
            other_weighted_rate,
            protected_weight,
        )

    eligible_rate = total_rate[:, eligible]
    eligible_floor = floor[eligible]
    floor_violation = (
        eligible_rate < eligible_floor[None, :] - 1e-12
    )
    normalized_shortfall = np.maximum(
        0.0,
        (
            eligible_floor[None, :]
            - eligible_rate
        )
        / eligible_floor[None, :],
    )
    pf_by_interval = np.log(
        eligible_rate + float(epsilon_bps_hz)
    ).sum(axis=1)
    geometric_by_interval = (
        np.exp(
            np.log(
                eligible_rate + float(epsilon_bps_hz)
            ).mean(axis=1)
        )
        - float(epsilon_bps_hz)
    )
    p05_by_interval = np.quantile(
        eligible_rate,
        0.05,
        axis=1,
    )
    jain_by_interval = (
        eligible_rate.sum(axis=1) ** 2
        / (
            eligible_rate.shape[1]
            * np.sum(eligible_rate**2, axis=1)
        )
    )

    groups: dict[str, dict[str, float | int]] = {}
    for name, mask in [
        ("eligible_all", eligible),
        ("eligible_indoor", eligible & indoor),
        ("eligible_outdoor", eligible & (~indoor)),
        ("coverage_limited_all", ~eligible),
        ("coverage_limited_indoor", (~eligible) & indoor),
        ("coverage_limited_outdoor", (~eligible) & (~indoor)),
    ]:
        rate = total_rate[:, mask]
        protected = protected_rate[:, mask]
        if rate.shape[1] == 0:
            groups[name] = {"user_count": 0}
            continue
        groups[name] = {
            "user_count": int(mask.sum()),
            "mean_total_rate_bps_hz": float(
                np.average(rate.mean(axis=1), weights=lengths)
            ),
            "minimum_total_rate_bps_hz": float(rate.min()),
            "mean_protected_rate_bps_hz": float(
                np.average(protected.mean(axis=1), weights=lengths)
            ),
            "minimum_protected_rate_bps_hz": float(
                protected.min()
            ),
            "mean_total_geometric_rate_bps_hz": float(
                np.average(
                    np.exp(
                        np.log(
                            rate + float(epsilon_bps_hz)
                        ).mean(axis=1)
                    )
                    - float(epsilon_bps_hz),
                    weights=lengths,
                )
            ),
        }

    return {
        "total_rate": total_rate,
        "protected_rate": protected_rate,
        "mean_total_network_retention": float(
            np.average(total_rate.sum(axis=1), weights=lengths)
            / nominal_total.sum()
        ),
        "minimum_total_network_retention": float(
            total_rate.sum(axis=1).min() / nominal_total.sum()
        ),
        "mean_protected_network_retention": float(
            np.average(
                protected_rate.sum(axis=1),
                weights=lengths,
            )
            / nominal_protected.sum()
        ),
        "minimum_protected_network_retention": float(
            protected_rate.sum(axis=1).min()
            / nominal_protected.sum()
        ),
        "floor_violation_interval_count": int(
            floor_violation.any(axis=1).sum()
        ),
        "floor_violation_user_interval_count": int(
            floor_violation.sum()
        ),
        "unique_floor_violation_user_count": int(
            floor_violation.any(axis=0).sum()
        ),
        "total_normalized_floor_shortfall_user_seconds": float(
            (
                normalized_shortfall
                * lengths[:, None]
            ).sum()
        ),
        "maximum_normalized_floor_shortfall": float(
            normalized_shortfall.max()
        ),
        "minimum_floor_ratio": float(
            np.min(
                eligible_rate
                / eligible_floor[None, :]
            )
        ),
        "mean_pf_utility": float(
            np.average(pf_by_interval, weights=lengths)
        ),
        "minimum_pf_utility": float(pf_by_interval.min()),
        "mean_geometric_rate_bps_hz": float(
            np.average(geometric_by_interval, weights=lengths)
        ),
        "minimum_geometric_rate_bps_hz": float(
            geometric_by_interval.min()
        ),
        "mean_p05_eligible_rate_bps_hz": float(
            np.average(p05_by_interval, weights=lengths)
        ),
        "minimum_p05_eligible_rate_bps_hz": float(
            p05_by_interval.min()
        ),
        "minimum_eligible_rate_bps_hz": float(
            eligible_rate.min()
        ),
        "mean_jain_index_eligible": float(
            np.average(jain_by_interval, weights=lengths)
        ),
        "minimum_jain_index_eligible": float(
            jain_by_interval.min()
        ),
        "user_worst_total_retention": (
            total_rate.min(axis=0) / nominal_total
        ),
        "user_worst_protected_retention": (
            protected_rate.min(axis=0) / nominal_protected
        ),
        "groups": groups,
    }


def control_metrics(
    command_q_db: np.ndarray,
    applied_q_db: np.ndarray,
) -> dict[str, float]:
    command = np.asarray(command_q_db, dtype=float)
    applied = np.asarray(applied_q_db, dtype=float)
    difference = (
        np.diff(command, axis=0)
        if len(command) > 1
        else np.zeros((0, 57, 2))
    )
    return {
        "command_total_variation_db": float(
            np.abs(difference).sum()
        ),
        "maximum_command_slew_db": float(
            np.abs(difference).max()
            if difference.size
            else 0.0
        ),
        "mean_active_mode_count": float(
            np.mean(np.sum(applied > 0.0, axis=(1, 2)))
        ),
        "maximum_active_mode_count": float(
            np.max(np.sum(applied > 0.0, axis=(1, 2)))
        ),
        "payload_bytes_per_update": float(57 * 2 * 4),
    }
