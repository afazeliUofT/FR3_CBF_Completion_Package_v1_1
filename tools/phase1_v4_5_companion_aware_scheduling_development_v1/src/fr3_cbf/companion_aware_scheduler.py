"""Companion-aware protected-subband scheduling for candidate v4.5.

This module is invoked only when the frozen candidate-v4.3 fixed-q,
fixed-RZF power action has no deployable witness.  It introduces one new
physical degree of freedom: network-synchronised protected-subband slot
scheduling over a one-second NR frame.

For every mode:
* q commands and RZF directions remain frozen;
* each stream coefficient is in [0, 1];
* every sector remains within its full post-mode conducted-power envelope;
* noncritical sectors remain at the reviewed v4.3 fallback, except for a
  bounded total number of external guard sectors that may only be muted.

The master problem enforces every active eligible user's unchanged total-band
floor and every long/short EESS row on the time average.  The same 0.5-ms
schedule is repeated in each physical second of the 5-second control interval.
"""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from typing import Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

from fr3_cbf import floor_feasibility_repair as repair

SLOT_DURATION_S = 0.0005
SLOTS_PER_SECOND = 2000
# These are solver-side tightenings, not acceptance-tolerance changes.
SCHEDULE_CONSTRAINT_RESERVE = 1e-6
SCHEDULE_RATE_RESERVE_BPS_HZ = 5e-4
MAX_MODE_COUNT = 4096
MAX_DEPLOYABLE_GUARD_SECTORS = 4
DIAGNOSTIC_GUARD_SECTORS = 8


@dataclass(frozen=True)
class ScheduleMode:
    label: str
    stream_scale: np.ndarray
    changed_sectors: tuple[int, ...]
    guard_sectors: tuple[int, ...]
    target_users: tuple[int, ...]
    cost: float


@dataclass
class ScheduleOutcome:
    status: str
    feasible: bool
    guard_sector_limit: int
    diagnostic_only: bool
    mode_count: int
    nonzero_mode_count: int
    slot_count_per_second: int
    fractions: np.ndarray | None
    slot_counts: np.ndarray | None
    average_total_rate: np.ndarray | None
    average_protected_rate: np.ndarray | None
    average_stream_scale: np.ndarray | None
    long_ratio: np.ndarray | None
    short_ratio: np.ndarray | None
    floor_violation_count: int | None
    long_violation_seconds: int | None
    short_violation_seconds: int | None
    maximum_normalized_floor_shortfall: float | None
    minimum_active_eligible_floor_ratio: float | None
    maximum_post_mode_power_ratio: float | None
    critical_sectors: tuple[int, ...]
    mutable_sectors: tuple[int, ...]
    guard_sector_union: tuple[int, ...]
    maximum_guard_sector_count: int
    schedule_records: list[dict[str, object]]
    continuous_message: str
    integer_message: str


def _active_stream_users(
    active_user: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
) -> dict[int, dict[int, int]]:
    active = np.asarray(active_user, dtype=bool)
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    result: dict[int, dict[int, int]] = {}
    for user in np.flatnonzero(active):
        result.setdefault(int(serving[user]), {})[int(stream[user])] = int(user)
    return result


def _target_stream_users(
    violating_users: Sequence[int],
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
) -> dict[int, dict[int, int]]:
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    result: dict[int, dict[int, int]] = {}
    for user_value in violating_users:
        user = int(user_value)
        result.setdefault(int(serving[user]), {})[int(stream[user])] = user
    return result


def _sector_options(
    baseline_row: np.ndarray,
    active_stream_to_user: dict[int, int],
    target_stream_to_user: dict[int, int],
) -> list[tuple[str, np.ndarray, tuple[int, ...]]]:
    """Compact options for one critical sector.

    Singleton modes are generated for every active stream in each critical
    sector.  This completes the local time-sharing basis for companion users
    whose floors can become binding after a vulnerable user is protected.
    """
    baseline = np.asarray(baseline_row, dtype=np.float64)
    stream_count = len(baseline)
    options: list[tuple[str, np.ndarray, tuple[int, ...]]] = [
        ("baseline", baseline.copy(), ()),
    ]
    for local_stream, user in sorted(active_stream_to_user.items()):
        row = np.zeros(stream_count, dtype=np.float64)
        row[int(local_stream)] = 1.0
        options.append((f"singleton_s{local_stream}", row, (int(user),)))
    if active_stream_to_user:
        row = np.zeros(stream_count, dtype=np.float64)
        for local_stream in active_stream_to_user:
            row[int(local_stream)] = 1.0
        options.append(
            (
                "full_active",
                row,
                tuple(sorted(int(v) for v in target_stream_to_user.values())),
            )
        )
    options.append(("mute", np.zeros(stream_count, dtype=np.float64), ()))

    unique: list[tuple[str, np.ndarray, tuple[int, ...]]] = []
    seen: set[bytes] = set()
    for label, row, users in options:
        key = np.round(row, 15).tobytes()
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, row, users))
    return unique


def _rank_external_guards(
    *,
    gain_user_sector_stream: np.ndarray,
    baseline_stream_scale: np.ndarray,
    target_users: Sequence[int],
    serving_bs: np.ndarray,
    excluded_sectors: Sequence[int],
    limit: int,
    leakage_sector_stream: np.ndarray | None = None,
    long_kappa_second_sector: np.ndarray | None = None,
    short_kappa_second_sector: np.ndarray | None = None,
    long_allowance_second: np.ndarray | None = None,
    short_allowance_second: np.ndarray | None = None,
    coupling_uplift_db: float = 0.0,
) -> tuple[int, ...]:
    """Rank one total sparse guard set by user harm and EESS burden.

    Target-interference and EESS-contribution scores are separately normalized
    before addition. A sector that is modest for target-user interference but
    dominant for an active EESS row is therefore not silently ignored. The set
    is fixed for the whole control interval, so its union is exactly bounded by
    ``limit``.
    """
    if limit <= 0 or not target_users:
        return ()
    gain = np.asarray(gain_user_sector_stream, dtype=np.float64)
    baseline = np.asarray(baseline_stream_scale, dtype=np.float64)
    serving = np.asarray(serving_bs, dtype=np.int64)
    sector_count = baseline.shape[0]

    target_score = np.zeros(sector_count, dtype=np.float64)
    for user_value in target_users:
        user = int(user_value)
        contribution = np.sum(gain[user] * baseline, axis=1)
        contribution[int(serving[user])] = 0.0
        total = float(np.sum(contribution))
        if total > np.finfo(np.float64).tiny:
            target_score += contribution / total
    target_max = float(np.max(target_score, initial=0.0))
    if target_max > np.finfo(np.float64).tiny:
        target_score /= target_max

    eess_score = np.zeros(sector_count, dtype=np.float64)
    eess_inputs = (
        leakage_sector_stream,
        long_kappa_second_sector,
        short_kappa_second_sector,
        long_allowance_second,
        short_allowance_second,
    )
    if all(value is not None for value in eess_inputs):
        leakage = np.asarray(leakage_sector_stream, dtype=np.float64)
        sector_leakage = np.sum(leakage * baseline, axis=1)
        uplift = 10.0 ** (float(coupling_uplift_db) / 10.0)
        long_kappa = np.asarray(long_kappa_second_sector, dtype=np.float64)
        short_kappa = np.asarray(short_kappa_second_sector, dtype=np.float64)
        long_allow = np.asarray(long_allowance_second, dtype=np.float64)
        short_allow = np.asarray(short_allowance_second, dtype=np.float64)
        long_contribution = (
            uplift * long_kappa * sector_leakage[None, :]
            / long_allow[:, None]
        )
        short_contribution = (
            uplift * short_kappa * sector_leakage[None, :]
            / short_allow[:, None]
        )
        eess_score = np.maximum(
            np.max(long_contribution, axis=0, initial=0.0),
            np.max(short_contribution, axis=0, initial=0.0),
        )
        eess_max = float(np.max(eess_score, initial=0.0))
        if eess_max > np.finfo(np.float64).tiny:
            eess_score /= eess_max

    score = target_score + eess_score
    excluded = np.asarray(tuple(excluded_sectors), dtype=np.int64)
    if len(excluded):
        score[excluded] = -np.inf
    order = np.argsort(-score, kind="stable")
    selected = [
        int(sector)
        for sector in order
        if np.isfinite(score[sector]) and score[sector] > 0.0
    ]
    return tuple(selected[: int(limit)])


def generate_schedule_modes(
    *,
    gain_user_sector_stream: np.ndarray,
    baseline_stream_scale: np.ndarray,
    active_user: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    violating_users: Sequence[int],
    guard_sector_limit: int,
    explicit_guard_sectors: Sequence[int] | None = None,
    leakage_sector_stream: np.ndarray | None = None,
    long_kappa_second_sector: np.ndarray | None = None,
    short_kappa_second_sector: np.ndarray | None = None,
    long_allowance_second: np.ndarray | None = None,
    short_allowance_second: np.ndarray | None = None,
    coupling_uplift_db: float = 0.0,
) -> tuple[list[ScheduleMode], tuple[int, ...]]:
    baseline = np.asarray(baseline_stream_scale, dtype=np.float64)
    active_map = _active_stream_users(active_user, serving_bs, serving_stream)
    target_map = _target_stream_users(
        violating_users, serving_bs, serving_stream
    )
    critical = tuple(sorted(target_map))
    if not critical:
        return [
            ScheduleMode("baseline", baseline.copy(), (), (), (), 0.0)
        ], critical

    options_by_sector = [
        _sector_options(
            baseline[sector],
            active_map.get(sector, {}),
            target_map.get(sector, {}),
        )
        for sector in critical
    ]
    possible = math.prod(len(value) for value in options_by_sector)
    if possible > MAX_MODE_COUNT:
        raise RuntimeError(
            f"protected scheduling mode count {possible} exceeds {MAX_MODE_COUNT}"
        )

    # One total guard set is selected for the whole one-second schedule.
    # This keeps the distributed action scope explicit: all nonbaseline modes
    # use the same at-most-G external sectors, so their union cannot silently
    # exceed the advertised guard limit.
    if explicit_guard_sectors is None:
        global_guards = _rank_external_guards(
            gain_user_sector_stream=gain_user_sector_stream,
            baseline_stream_scale=baseline,
            target_users=tuple(int(v) for v in violating_users),
            serving_bs=serving_bs,
            excluded_sectors=critical,
            limit=int(guard_sector_limit),
            leakage_sector_stream=leakage_sector_stream,
            long_kappa_second_sector=long_kappa_second_sector,
            short_kappa_second_sector=short_kappa_second_sector,
            long_allowance_second=long_allowance_second,
            short_allowance_second=short_allowance_second,
            coupling_uplift_db=float(coupling_uplift_db),
        )
    else:
        explicit = tuple(dict.fromkeys(int(v) for v in explicit_guard_sectors))
        if len(explicit) > int(guard_sector_limit):
            raise ValueError("explicit guard set exceeds declared guard limit")
        if any(v in critical for v in explicit):
            raise ValueError("critical serving sector cannot be an external guard")
        if any(v < 0 or v >= baseline.shape[0] for v in explicit):
            raise ValueError("explicit guard sector out of range")
        global_guards = explicit

    modes: list[ScheduleMode] = []
    seen: set[bytes] = set()
    for combination in itertools.product(*options_by_sector):
        scale = baseline.copy()
        labels: list[str] = []
        targets: set[int] = set()
        for sector, (label, row, users) in zip(
            critical, combination, strict=True
        ):
            scale[int(sector)] = row
            labels.append(f"b{sector}:{label}")
            targets.update(int(user) for user in users)

        changed_critical = bool(
            np.any(np.abs(scale[list(critical)] - baseline[list(critical)]) > 1e-12)
        )
        guards = global_guards if changed_critical else ()
        for sector in guards:
            scale[int(sector)] = 0.0

        key = np.round(scale, 15).tobytes()
        if key in seen:
            continue
        seen.add(key)
        changed = tuple(
            int(sector)
            for sector in np.flatnonzero(
                np.any(np.abs(scale - baseline) > 1e-12, axis=1)
            )
        )
        baseline_mode = not changed
        cost = 0.0 if baseline_mode else (
            1.0
            + 0.02 * len(changed)
            + 0.05 * len(guards)
            + 0.005 * len(targets)
        )
        modes.append(
            ScheduleMode(
                label="baseline" if baseline_mode else ";".join(labels),
                stream_scale=scale,
                changed_sectors=changed,
                guard_sectors=guards,
                target_users=tuple(sorted(targets)),
                cost=float(cost),
            )
        )
    modes.sort(key=lambda mode: (mode.cost, mode.label, mode.guard_sectors))
    return modes, critical


def evaluate_modes(
    *,
    modes: Sequence[ScheduleMode],
    gain_user_sector_stream: np.ndarray,
    other_weighted_rate: np.ndarray,
    active_user: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    long_kappa_second_sector: np.ndarray,
    short_kappa_second_sector: np.ndarray,
    leakage_sector_stream: np.ndarray,
    long_allowance_second: np.ndarray,
    short_allowance_second: np.ndarray,
    coupling_uplift_db: float,
    actual_stream_power: np.ndarray,
) -> dict[str, np.ndarray]:
    gain = np.asarray(gain_user_sector_stream, dtype=np.float64)
    other = np.asarray(other_weighted_rate, dtype=np.float64)
    active = np.asarray(active_user, dtype=bool)
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    scales = np.asarray([mode.stream_scale for mode in modes], dtype=np.float64)
    if (
        float(np.min(scales, initial=0.0)) < -1e-12
        or float(np.max(scales, initial=0.0)) > 1.0 + 1e-12
    ):
        raise RuntimeError(
            "protected-subband mode coefficients must remain in [0, 1]"
        )
    mode_count, sector_count, stream_count = scales.shape
    user_count = gain.shape[0]
    if gain.shape != (user_count, sector_count, stream_count):
        raise ValueError("mode/gain dimensions do not align")

    flat_scale = scales.reshape(mode_count, -1)
    flat_gain = gain.reshape(user_count, -1)
    received = flat_scale @ flat_gain.T
    desired_index = serving * stream_count + stream
    desired_gain = flat_gain[np.arange(user_count), desired_index]
    desired = flat_scale[:, desired_index] * desired_gain[None, :]
    interference = np.maximum(received - desired, 0.0)
    protected = np.log2(
        1.0 + desired / (interference + float(protected_noise_w))
    )
    total = other[None, :] + float(protected_weight) * protected
    total[:, ~active] = 0.0
    protected[:, ~active] = 0.0

    leakage = np.asarray(leakage_sector_stream, dtype=np.float64)
    sector_leakage = np.sum(scales * leakage[None, :, :], axis=2)
    uplift = 10.0 ** (float(coupling_uplift_db) / 10.0)
    long_kappa = np.asarray(long_kappa_second_sector, dtype=np.float64)
    short_kappa = np.asarray(short_kappa_second_sector, dtype=np.float64)
    long_allow = np.asarray(long_allowance_second, dtype=np.float64)
    short_allow = np.asarray(short_allowance_second, dtype=np.float64)
    long_ratio = uplift * (sector_leakage @ long_kappa.T) / long_allow[None, :]
    short_ratio = uplift * (sector_leakage @ short_kappa.T) / short_allow[None, :]

    power = np.asarray(actual_stream_power, dtype=np.float64)
    used_power = np.sum(scales * power[None, :, :], axis=2)
    envelope = np.sum(power, axis=1)
    power_ratio = np.divide(
        used_power,
        envelope[None, :],
        out=np.zeros_like(used_power),
        where=envelope[None, :] > np.finfo(np.float64).tiny,
    )
    zero_envelope_bad = (
        envelope[None, :] <= np.finfo(np.float64).tiny
    ) & (used_power > np.finfo(np.float64).tiny)
    power_ratio[zero_envelope_bad] = np.inf
    if float(np.max(power_ratio, initial=0.0)) > 1.0 + 1e-10:
        raise RuntimeError("generated schedule mode exceeds post-mode power")
    return {
        "scales": scales,
        "protected_rate": protected,
        "total_rate": total,
        "long_ratio": long_ratio,
        "short_ratio": short_ratio,
        "power_ratio": power_ratio,
    }


def _audit_average(
    *,
    fractions: np.ndarray,
    evaluated: dict[str, np.ndarray],
    active_user: np.ndarray,
    eligible_user: np.ndarray,
    floors: np.ndarray,
) -> dict[str, object]:
    fraction = np.asarray(fractions, dtype=np.float64)
    total = fraction @ evaluated["total_rate"]
    protected = fraction @ evaluated["protected_rate"]
    long_ratio = fraction @ evaluated["long_ratio"]
    short_ratio = fraction @ evaluated["short_ratio"]
    active = np.asarray(active_user, dtype=bool)
    eligible = np.asarray(eligible_user, dtype=bool)
    floor = np.asarray(floors, dtype=np.float64)
    valid = active & eligible & (floor > 0.0)
    violating = valid & (
        total < floor - repair.FLOOR_COMPARISON_TOLERANCE
    )
    normalized = np.zeros_like(total)
    normalized[valid] = np.maximum(
        0.0, (floor[valid] - total[valid]) / floor[valid]
    )
    minimum_ratio = (
        float(np.min(total[valid] / floor[valid])) if np.any(valid) else None
    )
    return {
        "total_rate": total,
        "protected_rate": protected,
        "long_ratio": long_ratio,
        "short_ratio": short_ratio,
        "floor_violation_count": int(np.sum(violating)),
        "long_violation_seconds": int(np.sum(long_ratio > 1.0 + 1e-10)),
        "short_violation_seconds": int(np.sum(short_ratio > 1.0 + 1e-10)),
        "maximum_normalized_floor_shortfall": float(
            np.max(normalized, initial=0.0)
        ),
        "minimum_active_eligible_floor_ratio": minimum_ratio,
    }


def _continuous_master(
    *,
    modes: Sequence[ScheduleMode],
    evaluated: dict[str, np.ndarray],
    active_user: np.ndarray,
    eligible_user: np.ndarray,
    floors: np.ndarray,
):
    active = np.asarray(active_user, dtype=bool)
    eligible = np.asarray(eligible_user, dtype=bool)
    floor = np.asarray(floors, dtype=np.float64)
    valid = active & eligible & (floor > 0.0)
    rows: list[np.ndarray] = []
    rhs: list[float] = []
    for user in np.flatnonzero(valid):
        rows.append(-evaluated["total_rate"][:, int(user)])
        rhs.append(-(float(floor[user]) + SCHEDULE_RATE_RESERVE_BPS_HZ))
    for second in range(evaluated["long_ratio"].shape[1]):
        rows.append(evaluated["long_ratio"][:, second])
        rhs.append(1.0 - SCHEDULE_CONSTRAINT_RESERVE)
    for second in range(evaluated["short_ratio"].shape[1]):
        rows.append(evaluated["short_ratio"][:, second])
        rhs.append(1.0 - SCHEDULE_CONSTRAINT_RESERVE)
    cost = np.asarray([mode.cost for mode in modes], dtype=np.float64)
    cost += 1e-12 * np.arange(len(modes), dtype=np.float64)
    return linprog(
        cost,
        A_ub=np.asarray(rows, dtype=np.float64),
        b_ub=np.asarray(rhs, dtype=np.float64),
        A_eq=np.ones((1, len(modes)), dtype=np.float64),
        b_eq=np.ones(1, dtype=np.float64),
        bounds=[(0.0, 1.0)] * len(modes),
        method="highs-ds",
        options={
            "presolve": True,
            "primal_feasibility_tolerance": 1e-9,
            "dual_feasibility_tolerance": 1e-9,
        },
    )


def _integer_master(
    *,
    modes: Sequence[ScheduleMode],
    evaluated: dict[str, np.ndarray],
    active_user: np.ndarray,
    eligible_user: np.ndarray,
    floors: np.ndarray,
    slot_count: int,
) -> tuple[np.ndarray | None, str]:
    active = np.asarray(active_user, dtype=bool)
    eligible = np.asarray(eligible_user, dtype=bool)
    floor = np.asarray(floors, dtype=np.float64)
    valid = active & eligible & (floor > 0.0)
    rows: list[np.ndarray] = []
    lower: list[float] = []
    upper: list[float] = []
    for user in np.flatnonzero(valid):
        rows.append(evaluated["total_rate"][:, int(user)])
        lower.append(
            float(slot_count)
            * (float(floor[user]) + SCHEDULE_RATE_RESERVE_BPS_HZ)
        )
        upper.append(np.inf)
    for second in range(evaluated["long_ratio"].shape[1]):
        rows.append(evaluated["long_ratio"][:, second])
        lower.append(-np.inf)
        upper.append(
            float(slot_count) * (1.0 - SCHEDULE_CONSTRAINT_RESERVE)
        )
    for second in range(evaluated["short_ratio"].shape[1]):
        rows.append(evaluated["short_ratio"][:, second])
        lower.append(-np.inf)
        upper.append(
            float(slot_count) * (1.0 - SCHEDULE_CONSTRAINT_RESERVE)
        )
    rows.append(np.ones(len(modes), dtype=np.float64))
    lower.append(float(slot_count))
    upper.append(float(slot_count))
    result = milp(
        c=np.asarray([mode.cost for mode in modes], dtype=np.float64),
        integrality=np.ones(len(modes), dtype=np.int8),
        bounds=Bounds(
            np.zeros(len(modes), dtype=np.float64),
            np.full(len(modes), float(slot_count), dtype=np.float64),
        ),
        constraints=LinearConstraint(
            np.asarray(rows, dtype=np.float64),
            np.asarray(lower, dtype=np.float64),
            np.asarray(upper, dtype=np.float64),
        ),
        options={"time_limit": 1.0, "mip_rel_gap": 0.0, "presolve": True},
    )
    if result.x is None:
        return None, str(result.message)
    counts = np.rint(np.asarray(result.x, dtype=np.float64)).astype(np.int64)
    if int(np.sum(counts)) != int(slot_count):
        return None, "integer solver returned a nonconforming slot total"
    return counts, str(result.message)


def _empty_outcome(
    *,
    status: str,
    guard_sector_limit: int,
    diagnostic_only: bool,
    mode_count: int,
    critical_sectors: Sequence[int],
    continuous_message: str,
    integer_message: str,
) -> ScheduleOutcome:
    return ScheduleOutcome(
        status=status,
        feasible=False,
        guard_sector_limit=int(guard_sector_limit),
        diagnostic_only=bool(diagnostic_only),
        mode_count=int(mode_count),
        nonzero_mode_count=0,
        slot_count_per_second=SLOTS_PER_SECOND,
        fractions=None,
        slot_counts=None,
        average_total_rate=None,
        average_protected_rate=None,
        average_stream_scale=None,
        long_ratio=None,
        short_ratio=None,
        floor_violation_count=None,
        long_violation_seconds=None,
        short_violation_seconds=None,
        maximum_normalized_floor_shortfall=None,
        minimum_active_eligible_floor_ratio=None,
        maximum_post_mode_power_ratio=None,
        critical_sectors=tuple(int(v) for v in critical_sectors),
        mutable_sectors=(),
        guard_sector_union=(),
        maximum_guard_sector_count=0,
        schedule_records=[],
        continuous_message=continuous_message,
        integer_message=integer_message,
    )


def solve_schedule(
    *,
    modes: Sequence[ScheduleMode],
    evaluated: dict[str, np.ndarray],
    active_user: np.ndarray,
    eligible_user: np.ndarray,
    floors: np.ndarray,
    guard_sector_limit: int,
    diagnostic_only: bool,
    critical_sectors: Sequence[int],
) -> ScheduleOutcome:
    continuous = _continuous_master(
        modes=modes,
        evaluated=evaluated,
        active_user=active_user,
        eligible_user=eligible_user,
        floors=floors,
    )
    continuous_message = str(continuous.message)
    if continuous.x is None or not continuous.success:
        return _empty_outcome(
            status="CONTINUOUS_SCHEDULING_INFEASIBLE",
            guard_sector_limit=guard_sector_limit,
            diagnostic_only=diagnostic_only,
            mode_count=len(modes),
            critical_sectors=critical_sectors,
            continuous_message=continuous_message,
            integer_message="not run",
        )

    raw = np.asarray(continuous.x, dtype=np.float64) * SLOTS_PER_SECOND
    counts = np.floor(raw + 1e-12).astype(np.int64)
    remaining = int(SLOTS_PER_SECOND - np.sum(counts))
    if remaining > 0:
        remainders = raw - counts
        order = np.lexsort((np.arange(len(modes)), -remainders))
        counts[order[:remaining]] += 1
    fractions = counts.astype(np.float64) / float(SLOTS_PER_SECOND)
    audit = _audit_average(
        fractions=fractions,
        evaluated=evaluated,
        active_user=active_user,
        eligible_user=eligible_user,
        floors=floors,
    )
    exact_ok = bool(
        audit["floor_violation_count"] == 0
        and audit["long_violation_seconds"] == 0
        and audit["short_violation_seconds"] == 0
    )
    integer_message = "largest-remainder quantization"
    if not exact_ok:
        integer_counts, integer_message = _integer_master(
            modes=modes,
            evaluated=evaluated,
            active_user=active_user,
            eligible_user=eligible_user,
            floors=floors,
            slot_count=SLOTS_PER_SECOND,
        )
        if integer_counts is None:
            return _empty_outcome(
                status="CONTINUOUS_FEASIBLE_BUT_SLOT_QUANTIZATION_UNCERTIFIED",
                guard_sector_limit=guard_sector_limit,
                diagnostic_only=diagnostic_only,
                mode_count=len(modes),
                critical_sectors=critical_sectors,
                continuous_message=continuous_message,
                integer_message=integer_message,
            )
        counts = integer_counts
        fractions = counts.astype(np.float64) / float(SLOTS_PER_SECOND)
        audit = _audit_average(
            fractions=fractions,
            evaluated=evaluated,
            active_user=active_user,
            eligible_user=eligible_user,
            floors=floors,
        )
        exact_ok = bool(
            audit["floor_violation_count"] == 0
            and audit["long_violation_seconds"] == 0
            and audit["short_violation_seconds"] == 0
        )
    if not exact_ok:
        return _empty_outcome(
            status="QUANTIZED_SCHEDULE_EXACT_AUDIT_FAILED",
            guard_sector_limit=guard_sector_limit,
            diagnostic_only=diagnostic_only,
            mode_count=len(modes),
            critical_sectors=critical_sectors,
            continuous_message=continuous_message,
            integer_message=integer_message,
        )

    nonzero = np.flatnonzero(counts > 0)
    mutable: set[int] = set()
    guard_union: set[int] = set()
    records: list[dict[str, object]] = []
    maximum_guard = 0
    for index in nonzero:
        mode = modes[int(index)]
        mutable.update(mode.changed_sectors)
        guard_union.update(mode.guard_sectors)
        maximum_guard = max(maximum_guard, len(mode.guard_sectors))
        records.append(
            {
                "mode_index": int(index),
                "label": mode.label,
                "slot_count_per_second": int(counts[index]),
                "fraction": float(fractions[index]),
                "changed_sectors": list(mode.changed_sectors),
                "guard_sectors": list(mode.guard_sectors),
                "target_users": list(mode.target_users),
            }
        )
    average_stream_scale = (
        fractions @ evaluated["scales"].reshape(len(modes), -1)
    ).reshape(evaluated["scales"].shape[1:])
    return ScheduleOutcome(
        status=(
            "DIAGNOSTIC_SCHEDULING_FEASIBLE"
            if diagnostic_only
            else "DEPLOYABLE_SCHEDULING_FEASIBLE"
        ),
        feasible=not diagnostic_only,
        guard_sector_limit=int(guard_sector_limit),
        diagnostic_only=bool(diagnostic_only),
        mode_count=len(modes),
        nonzero_mode_count=len(nonzero),
        slot_count_per_second=SLOTS_PER_SECOND,
        fractions=fractions,
        slot_counts=counts,
        average_total_rate=np.asarray(audit["total_rate"], dtype=np.float64),
        average_protected_rate=np.asarray(
            audit["protected_rate"], dtype=np.float64
        ),
        average_stream_scale=average_stream_scale,
        long_ratio=np.asarray(audit["long_ratio"], dtype=np.float64),
        short_ratio=np.asarray(audit["short_ratio"], dtype=np.float64),
        floor_violation_count=int(audit["floor_violation_count"]),
        long_violation_seconds=int(audit["long_violation_seconds"]),
        short_violation_seconds=int(audit["short_violation_seconds"]),
        maximum_normalized_floor_shortfall=float(
            audit["maximum_normalized_floor_shortfall"]
        ),
        minimum_active_eligible_floor_ratio=audit[
            "minimum_active_eligible_floor_ratio"
        ],
        maximum_post_mode_power_ratio=float(
            np.max(evaluated["power_ratio"][nonzero], initial=0.0)
        ),
        critical_sectors=tuple(int(v) for v in critical_sectors),
        mutable_sectors=tuple(sorted(mutable)),
        guard_sector_union=tuple(sorted(guard_union)),
        maximum_guard_sector_count=int(maximum_guard),
        schedule_records=records,
        continuous_message=continuous_message,
        integer_message=integer_message,
    )


def _candidate_guard_subsets(pool: Sequence[int], maximum_size: int = 4):
    """Enumerate deterministic bounded guard unions by increasing cardinality."""
    unique = tuple(dict.fromkeys(int(v) for v in pool))
    for size in range(1, min(int(maximum_size), len(unique)) + 1):
        yield from itertools.combinations(unique, size)


def _build_and_solve(
    *,
    gain_user_sector_stream: np.ndarray,
    baseline_stream_scale: np.ndarray,
    other_weighted_rate: np.ndarray,
    active_user: np.ndarray,
    eligible_user: np.ndarray,
    floors: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    long_kappa_second_sector: np.ndarray,
    short_kappa_second_sector: np.ndarray,
    leakage_sector_stream: np.ndarray,
    long_allowance_second: np.ndarray,
    short_allowance_second: np.ndarray,
    coupling_uplift_db: float,
    actual_stream_power: np.ndarray,
    violating_users: Sequence[int],
    guard_sector_limit: int,
    diagnostic_only: bool,
    explicit_guard_sectors: Sequence[int] | None = None,
) -> ScheduleOutcome:
    modes, critical = generate_schedule_modes(
        gain_user_sector_stream=gain_user_sector_stream,
        baseline_stream_scale=baseline_stream_scale,
        active_user=active_user,
        serving_bs=serving_bs,
        serving_stream=serving_stream,
        violating_users=violating_users,
        guard_sector_limit=guard_sector_limit,
        explicit_guard_sectors=explicit_guard_sectors,
        leakage_sector_stream=leakage_sector_stream,
        long_kappa_second_sector=long_kappa_second_sector,
        short_kappa_second_sector=short_kappa_second_sector,
        long_allowance_second=long_allowance_second,
        short_allowance_second=short_allowance_second,
        coupling_uplift_db=float(coupling_uplift_db),
    )
    evaluated = evaluate_modes(
        modes=modes,
        gain_user_sector_stream=gain_user_sector_stream,
        other_weighted_rate=other_weighted_rate,
        active_user=active_user,
        serving_bs=serving_bs,
        serving_stream=serving_stream,
        protected_noise_w=protected_noise_w,
        protected_weight=protected_weight,
        long_kappa_second_sector=long_kappa_second_sector,
        short_kappa_second_sector=short_kappa_second_sector,
        leakage_sector_stream=leakage_sector_stream,
        long_allowance_second=long_allowance_second,
        short_allowance_second=short_allowance_second,
        coupling_uplift_db=coupling_uplift_db,
        actual_stream_power=actual_stream_power,
    )
    return solve_schedule(
        modes=modes,
        evaluated=evaluated,
        active_user=active_user,
        eligible_user=eligible_user,
        floors=floors,
        guard_sector_limit=guard_sector_limit,
        diagnostic_only=diagnostic_only,
        critical_sectors=critical,
    )


def schedule_interval(
    *,
    gain_user_sector_stream: np.ndarray,
    baseline_stream_scale: np.ndarray,
    other_weighted_rate: np.ndarray,
    active_user: np.ndarray,
    eligible_user: np.ndarray,
    floors: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    long_kappa_second_sector: np.ndarray,
    short_kappa_second_sector: np.ndarray,
    leakage_sector_stream: np.ndarray,
    long_allowance_second: np.ndarray,
    short_allowance_second: np.ndarray,
    coupling_uplift_db: float,
    actual_stream_power: np.ndarray,
    violating_users: Sequence[int],
) -> ScheduleOutcome:
    """Complete companion singletons, then exact-search bounded guard unions."""
    violating = tuple(int(value) for value in violating_users)
    if not violating:
        return _empty_outcome(
            status="NO_VIOLATING_USER",
            guard_sector_limit=0,
            diagnostic_only=False,
            mode_count=1,
            critical_sectors=(),
            continuous_message="not run",
            integer_message="not run",
        )

    common = dict(
        gain_user_sector_stream=gain_user_sector_stream,
        baseline_stream_scale=baseline_stream_scale,
        other_weighted_rate=other_weighted_rate,
        active_user=active_user,
        eligible_user=eligible_user,
        floors=floors,
        serving_bs=serving_bs,
        serving_stream=serving_stream,
        protected_noise_w=protected_noise_w,
        protected_weight=protected_weight,
        long_kappa_second_sector=long_kappa_second_sector,
        short_kappa_second_sector=short_kappa_second_sector,
        leakage_sector_stream=leakage_sector_stream,
        long_allowance_second=long_allowance_second,
        short_allowance_second=short_allowance_second,
        coupling_uplift_db=coupling_uplift_db,
        actual_stream_power=actual_stream_power,
        violating_users=violating,
    )

    last: ScheduleOutcome | None = None
    for guard_limit in (0, 2, MAX_DEPLOYABLE_GUARD_SECTORS):
        outcome = _build_and_solve(
            **common,
            guard_sector_limit=guard_limit,
            diagnostic_only=False,
        )
        last = outcome
        if outcome.feasible:
            return outcome

    diagnostic = _build_and_solve(
        **common,
        guard_sector_limit=DIAGNOSTIC_GUARD_SECTORS,
        diagnostic_only=True,
    )
    last = diagnostic
    if diagnostic.status == "DIAGNOSTIC_SCHEDULING_FEASIBLE":
        critical = tuple(sorted(set(int(serving_bs[u]) for u in violating)))
        pool = _rank_external_guards(
            gain_user_sector_stream=gain_user_sector_stream,
            baseline_stream_scale=baseline_stream_scale,
            target_users=violating,
            serving_bs=serving_bs,
            excluded_sectors=critical,
            limit=DIAGNOSTIC_GUARD_SECTORS,
            leakage_sector_stream=leakage_sector_stream,
            long_kappa_second_sector=long_kappa_second_sector,
            short_kappa_second_sector=short_kappa_second_sector,
            long_allowance_second=long_allowance_second,
            short_allowance_second=short_allowance_second,
            coupling_uplift_db=float(coupling_uplift_db),
        )
        for subset in _candidate_guard_subsets(
            pool, MAX_DEPLOYABLE_GUARD_SECTORS
        ):
            outcome = _build_and_solve(
                **common,
                guard_sector_limit=len(subset),
                diagnostic_only=False,
                explicit_guard_sectors=subset,
            )
            if outcome.feasible:
                outcome.status = "DEPLOYABLE_GUARD_SUBSET_SCHEDULING_FEASIBLE"
                return outcome
        return diagnostic
    return last
