"""Candidate v4.4: floor-first protected-subband scheduling/reassignment.

Candidate v4.4 preserves the predictive q-mode trajectory, fixed RZF columns,
unchanged fairness floor, EESS constraints, and the candidate-v4.3 sparse
power-repair hierarchy.  Only when v4.3 returns no feasible deployable action,
a one-second protected-subband slot schedule is synthesized over the critical
serving sectors and one fixed total set of at most four dominant external guard
sectors for the control interval.
"""
from __future__ import annotations

from collections import Counter
import math
import time
from types import SimpleNamespace
from typing import Any, Sequence

import numpy as np

from fr3_cbf.phase1_job_runtime import EvaluatedRun
from fr3_cbf.null_floor_aware_sector_backoff import (
    SectorBackoffPriceAllocator,
    build_local_cost_table,
)
from fr3_cbf import floor_feasibility_repair as repair
from fr3_cbf import protected_subband_scheduler as scheduler

CANDIDATE_METHOD_ID = (
    "candidate_v4_4_floor_first_protected_subband_scheduling"
)
GRID_DB = tuple(float(v) for v in range(13)) + (math.inf,)


def _floor_metrics(
    delivered: np.ndarray,
    active: np.ndarray,
    eligible: np.ndarray,
    floors: np.ndarray,
) -> tuple[int, float, float]:
    delivered = np.asarray(delivered, dtype=np.float64)
    active = np.asarray(active, dtype=bool)
    eligible = np.asarray(eligible, dtype=bool)
    floors = np.asarray(floors, dtype=np.float64)
    valid = active & eligible & (floors > 0.0)
    violating = valid & (
        delivered < floors - repair.FLOOR_COMPARISON_TOLERANCE
    )
    normalized = np.zeros_like(delivered)
    normalized[valid] = np.maximum(
        0.0,
        (floors[valid] - delivered[valid]) / floors[valid],
    )
    return (
        int(np.sum(violating)),
        float(np.sum(normalized)),
        float(np.max(normalized, initial=0.0)),
    )


def _v43_scope_check(
    *,
    choice: Any,
    pre_stream: np.ndarray,
    selected_stream: np.ndarray,
    violating_users: np.ndarray,
    serving_bs: np.ndarray,
) -> tuple[bool, dict[str, Any]]:
    mutable = tuple(int(v) for v in choice.mutable_sectors)
    critical = tuple(int(v) for v in choice.critical_serving_sectors)
    external = tuple(int(v) for v in choice.top_external_sectors)
    eess = tuple(int(v) for v in choice.top_eess_sectors)
    expected = {
        int(serving_bs[int(user)])
        for user in np.asarray(violating_users, dtype=np.int64)
    }
    immutable = sorted(set(range(pre_stream.shape[0])) - set(mutable))
    unchanged = bool(
        not immutable
        or np.allclose(
            selected_stream[immutable],
            pre_stream[immutable],
            rtol=0.0,
            atol=1e-12,
        )
    )
    scalar_sectors = sorted((set(external) | set(eess)) - set(critical))
    scalar_ok = True
    nonincrease_ok = True
    for sector in scalar_sectors:
        row = selected_stream[sector]
        scalar_ok = scalar_ok and bool(
            np.allclose(row, row[0], rtol=0.0, atol=1e-12)
        )
        nonincrease_ok = nonincrease_ok and bool(
            row[0] <= pre_stream[sector, 0] + 1e-12
        )
    ok = bool(
        len(external) <= 2 * len(violating_users)
        and len(eess) <= 2
        and set(mutable) == (set(critical) | set(external) | set(eess))
        and set(critical) == expected
        and unchanged
        and scalar_ok
        and nonincrease_ok
    )
    return ok, {
        "mutable_sectors": list(mutable),
        "critical_serving_sectors": list(critical),
        "external_interferer_sectors": list(external),
        "eess_backoff_sectors": list(eess),
        "immutable_sectors_unchanged": unchanged,
        "external_eess_actions_scalar": scalar_ok,
        "external_eess_actions_nonincreasing": nonincrease_ok,
        "action_type": "V4_3_POWER_REPAIR",
    }


def _schedule_scope_check(
    *,
    outcome: scheduler.ScheduleOutcome,
    violating_users: np.ndarray,
    serving_bs: np.ndarray,
) -> tuple[bool, dict[str, Any]]:
    expected = tuple(
        sorted(
            {
                int(serving_bs[int(user)])
                for user in np.asarray(violating_users, dtype=np.int64)
            }
        )
    )
    mutable = set(int(v) for v in outcome.mutable_sectors)
    critical = set(int(v) for v in outcome.critical_sectors)
    guards = set(int(v) for v in outcome.guard_sector_union)
    allowed = critical | guards
    ok = bool(
        not outcome.diagnostic_only
        and tuple(outcome.critical_sectors) == expected
        and mutable.issubset(allowed)
        and len(guards) <= scheduler.MAX_DEPLOYABLE_GUARD_SECTORS
        and outcome.maximum_guard_sector_count
        <= scheduler.MAX_DEPLOYABLE_GUARD_SECTORS
        and outcome.guard_sector_limit
        <= scheduler.MAX_DEPLOYABLE_GUARD_SECTORS
    )
    return ok, {
        "mutable_sectors": sorted(mutable),
        "critical_serving_sectors": list(outcome.critical_sectors),
        "guard_sector_union": sorted(guards),
        "maximum_guard_sector_count_in_nonzero_mode": int(
            outcome.maximum_guard_sector_count
        ),
        "guard_sector_limit": int(outcome.guard_sector_limit),
        "slot_count_per_second": int(outcome.slot_count_per_second),
        "immutable_sectors_unchanged_by_construction": True,
        "guard_actions_mute_only": True,
        "action_type": "PROTECTED_SUBBAND_SCHEDULING",
    }


def _schedule_audit_namespace(
    outcome: scheduler.ScheduleOutcome,
) -> SimpleNamespace:
    assert outcome.average_total_rate is not None
    assert outcome.average_protected_rate is not None
    assert outcome.long_ratio is not None
    assert outcome.short_ratio is not None
    return SimpleNamespace(
        delivered_total_rate=np.asarray(
            outcome.average_total_rate, dtype=np.float64
        ),
        delivered_protected_rate=np.asarray(
            outcome.average_protected_rate, dtype=np.float64
        ),
        long_ratio=np.asarray(outcome.long_ratio, dtype=np.float64),
        short_ratio=np.asarray(outcome.short_ratio, dtype=np.float64),
        floor_violation_count=int(outcome.floor_violation_count or 0),
        long_violation_seconds=int(outcome.long_violation_seconds or 0),
        short_violation_seconds=int(outcome.short_violation_seconds or 0),
        maximum_normalized_floor_shortfall=float(
            outcome.maximum_normalized_floor_shortfall or 0.0
        ),
        minimum_active_eligible_floor_ratio=(
            outcome.minimum_active_eligible_floor_ratio
        ),
        maximum_long_ratio=float(
            np.max(outcome.long_ratio, initial=0.0)
        ),
        maximum_short_ratio=float(
            np.max(outcome.short_ratio, initial=0.0)
        ),
    )


def run_candidate_v4_4(
    *,
    states: Sequence[object],
    matrices: Sequence[object],
    matrix_indices: Sequence[int],
    predictive_run: EvaluatedRun,
    long_kappa: np.ndarray,
    short_kappa: np.ndarray,
    long_allowance: np.ndarray,
    short_allowance: np.ndarray,
    interval_lengths: np.ndarray,
    serving: np.ndarray,
    stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    initial_average: np.ndarray,
    alpha: float,
    eligible: np.ndarray,
    floors: np.ndarray,
    steering1: np.ndarray,
    steering2: np.ndarray,
    update_interval_s: int = 5,
    coupling_uplift_db: float = 3.0,
    epsilon: float = 0.001,
    grid_time_limit_s: float = 45.0,
) -> tuple[EvaluatedRun, dict[str, Any]]:
    started = time.perf_counter()
    states = list(states)
    matrices = list(matrices)
    interval_count = len(states)
    if interval_count == 0:
        raise ValueError("at least one interval is required")
    if len(matrix_indices) != interval_count or len(interval_lengths) != interval_count:
        raise ValueError("interval dimensions do not align")
    serving = np.asarray(serving, dtype=np.int64)
    stream = np.asarray(stream, dtype=np.int64)
    eligible = np.asarray(eligible, dtype=bool)
    floors = np.asarray(floors, dtype=np.float64)
    interval_lengths = np.asarray(interval_lengths, dtype=np.int64)
    sector_count = int(np.asarray(states[0].mode_leakage_w).shape[0])
    stream_count = int(np.asarray(matrices[0].perpendicular).shape[-1])
    user_count = len(serving)

    total = np.empty((interval_count, user_count), dtype=np.float64)
    protected = np.empty_like(total)
    average_trace = np.empty_like(total)
    floor_count = np.empty(interval_count, dtype=np.int64)
    normalized_shortfall = np.empty(interval_count, dtype=np.float64)
    maximum_shortfall = np.empty(interval_count, dtype=np.float64)
    average_stream_scale = np.empty(
        (interval_count, sector_count, stream_count), dtype=np.float64
    )
    sector_equivalent = np.empty(
        (interval_count, sector_count), dtype=np.float64
    )
    pre_repair_sector = np.empty_like(sector_equivalent)
    action_class = np.empty(interval_count, dtype="U128")
    long_ratio = np.empty(len(long_kappa), dtype=np.float64)
    short_ratio = np.empty(len(short_kappa), dtype=np.float64)
    local_build = np.empty(interval_count, dtype=np.float64)
    repair_seconds = np.zeros(interval_count, dtype=np.float64)
    schedule_seconds = np.zeros(interval_count, dtype=np.float64)
    schedule_mode_count = np.zeros(interval_count, dtype=np.int64)
    schedule_nonzero_mode_count = np.zeros(interval_count, dtype=np.int64)
    schedule_guard_sector_limit = np.full(interval_count, -1, dtype=np.int64)
    schedule_mutable_sector_count = np.zeros(interval_count, dtype=np.int64)
    current_average = np.asarray(initial_average, dtype=np.float64).copy()
    allocator = SectorBackoffPriceAllocator(np.asarray(GRID_DB, dtype=np.float64))

    action_counts: Counter[str] = Counter()
    strict_scope_failures = 0
    strict_power_failures = 0
    q0_headroom_actions = 0
    unresolved = 0
    diagnostic_g8_feasible = 0
    network_shutdown = 0
    maximum_mutable = 0
    maximum_external_per_user = 0
    maximum_eess = 0
    maximum_post_mode_power_ratio = 0.0
    maximum_schedule_guard = 0
    maximum_schedule_modes = 0
    schedule_interval_count = 0
    schedule_attempt_count = 0
    schedule_guard_limit_counts: Counter[str] = Counter()
    total_scheduled_slots_per_second = 0
    maximum_scheduled_slots_per_second = 0
    maximum_schedule_nonzero_modes = 0
    maximum_schedule_critical_sectors = 0
    maximum_q0_power_ratio = 0.0
    interval_records: list[dict[str, Any]] = []
    schedule_records: list[dict[str, Any]] = []

    for interval, state in enumerate(states):
        start = interval * int(update_interval_s)
        stop = min(start + int(update_interval_s), len(long_kappa))
        if stop <= start:
            raise ValueError("empty physical-second interval")
        q = np.asarray(predictive_run.q_db[interval], dtype=np.float64)
        matrix = matrices[int(matrix_indices[interval])]
        amplitude = repair.mode_adjusted_amplitude(state, q)
        gain = np.abs(amplitude) ** 2
        leakage, actual_power, nominal_q0_power = (
            repair.stream_leakage_and_power_envelopes(
                matrix, q, steering1, steering2
            )
        )

        local_started = time.perf_counter()
        local_cost, _ = build_local_cost_table(
            state,
            q,
            current_average,
            eligible,
            floors[interval],
            serving,
            stream,
            float(protected_noise_w),
            float(protected_weight),
            float(alpha),
            float(epsilon),
            np.asarray(GRID_DB, dtype=np.float64),
        )
        local_build[interval] = time.perf_counter() - local_started
        sector_leakage = np.sum(leakage, axis=1)
        envelope = (
            10.0 ** (float(coupling_uplift_db) / 10.0)
            * np.max(
                np.asarray(long_kappa[start:stop], dtype=np.float64)
                * sector_leakage[None, :]
                / np.asarray(
                    long_allowance[start:stop], dtype=np.float64
                )[:, None],
                axis=0,
            )
        )
        _, pre_sector, _, _, pre_feasible = allocator.solve(
            local_cost, envelope
        )
        if not pre_feasible:
            raise RuntimeError(
                f"interval {interval}: sequential fallback infeasible despite mute"
            )
        pre_sector = np.asarray(pre_sector, dtype=np.float64)
        pre_stream = np.repeat(pre_sector, stream_count).reshape(
            sector_count, stream_count
        )
        pre_repair_sector[interval] = pre_sector
        pre_audit = repair.exact_audit(
            gain_user_sector_stream=gain,
            stream_scale=pre_stream,
            other_weighted_rate=state.other_weighted_rate,
            active_user=state.active_user,
            eligible_user=eligible,
            floors=floors[interval],
            serving_bs=serving,
            serving_stream=stream,
            protected_noise_w=float(protected_noise_w),
            protected_weight=float(protected_weight),
            long_kappa_second_sector=long_kappa[start:stop],
            short_kappa_second_sector=short_kappa[start:stop],
            leakage_sector_stream=leakage,
            long_allowance_second=long_allowance[start:stop],
            short_allowance_second=short_allowance[start:stop],
            coupling_uplift_db=float(coupling_uplift_db),
        )
        violating_users = np.flatnonzero(pre_audit.floor_violation_mask)
        hard_failure = bool(
            pre_audit.floor_violation_count
            or pre_audit.long_violation_seconds
            or pre_audit.short_violation_seconds
        )

        selected_stream = pre_stream
        selected_sector = pre_sector
        selected_audit = pre_audit
        selected_class = "BASELINE_NOOP"
        scope_ok = True
        scope_record: dict[str, Any] = {
            "mutable_sectors": [],
            "critical_serving_sectors": [],
            "action_type": "BASELINE_NOOP",
        }
        schedule_outcome: scheduler.ScheduleOutcome | None = None

        if hard_failure:
            repair_started = time.perf_counter()
            choice = repair.repair_interval(
                state=state,
                matrices=matrix,
                q_db=q,
                baseline_sector_scale=pre_sector,
                eligible_user=eligible,
                floors=floors[interval],
                serving_bs=serving,
                serving_stream=stream,
                protected_noise_w=float(protected_noise_w),
                protected_weight=float(protected_weight),
                steering_pol1=steering1,
                steering_pol2=steering2,
                long_kappa_second_sector=long_kappa[start:stop],
                short_kappa_second_sector=short_kappa[start:stop],
                long_allowance_second=long_allowance[start:stop],
                short_allowance_second=short_allowance[start:stop],
                coupling_uplift_db=float(coupling_uplift_db),
                grid_backoff_db=GRID_DB,
                grid_time_limit_s=float(grid_time_limit_s),
            )
            repair_seconds[interval] = time.perf_counter() - repair_started
            selected_stream = np.asarray(choice.stream_scale, dtype=np.float64)
            selected_sector = np.asarray(
                choice.sector_scale_equivalent, dtype=np.float64
            )
            selected_audit = choice.exact_audit
            selected_class = str(choice.chosen_action_class)
            scope_ok, scope_record = _v43_scope_check(
                choice=choice,
                pre_stream=pre_stream,
                selected_stream=selected_stream,
                violating_users=violating_users,
                serving_bs=serving,
            )
            maximum_mutable = max(maximum_mutable, len(choice.mutable_sectors))
            maximum_external_per_user = max(
                maximum_external_per_user,
                int(
                    math.ceil(
                        len(choice.top_external_sectors)
                        / max(len(violating_users), 1)
                    )
                ),
            )
            maximum_eess = max(maximum_eess, len(choice.top_eess_sectors))

            if selected_class == "NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND":
                schedule_attempt_count += 1
                schedule_started = time.perf_counter()
                schedule_outcome = scheduler.schedule_interval(
                    gain_user_sector_stream=gain,
                    baseline_stream_scale=pre_stream,
                    other_weighted_rate=state.other_weighted_rate,
                    active_user=state.active_user,
                    eligible_user=eligible,
                    floors=floors[interval],
                    serving_bs=serving,
                    serving_stream=stream,
                    protected_noise_w=float(protected_noise_w),
                    protected_weight=float(protected_weight),
                    long_kappa_second_sector=long_kappa[start:stop],
                    short_kappa_second_sector=short_kappa[start:stop],
                    leakage_sector_stream=leakage,
                    long_allowance_second=long_allowance[start:stop],
                    short_allowance_second=short_allowance[start:stop],
                    coupling_uplift_db=float(coupling_uplift_db),
                    actual_stream_power=actual_power,
                    violating_users=violating_users,
                )
                schedule_seconds[interval] = (
                    time.perf_counter() - schedule_started
                )
                schedule_mode_count[interval] = schedule_outcome.mode_count
                schedule_nonzero_mode_count[interval] = (
                    schedule_outcome.nonzero_mode_count
                )
                schedule_guard_sector_limit[interval] = (
                    schedule_outcome.guard_sector_limit
                )
                schedule_mutable_sector_count[interval] = len(
                    schedule_outcome.mutable_sectors
                )
                maximum_schedule_modes = max(
                    maximum_schedule_modes, schedule_outcome.mode_count
                )
                maximum_schedule_guard = max(
                    maximum_schedule_guard,
                    schedule_outcome.maximum_guard_sector_count,
                )
                if schedule_outcome.feasible:
                    assert schedule_outcome.average_stream_scale is not None
                    selected_stream = np.asarray(
                        schedule_outcome.average_stream_scale,
                        dtype=np.float64,
                    )
                    power_denominator = np.sum(actual_power, axis=1)
                    selected_power = np.sum(
                        actual_power * selected_stream, axis=1
                    )
                    selected_sector = np.divide(
                        selected_power,
                        power_denominator,
                        out=np.zeros_like(selected_power),
                        where=power_denominator
                        > np.finfo(np.float64).tiny,
                    )
                    selected_audit = _schedule_audit_namespace(
                        schedule_outcome
                    )
                    selected_class = (
                        "FLOOR_FIRST_PROTECTED_SUBBAND_SCHEDULING_"
                        f"G{schedule_outcome.guard_sector_limit}"
                    )
                    scope_ok, scope_record = _schedule_scope_check(
                        outcome=schedule_outcome,
                        violating_users=violating_users,
                        serving_bs=serving,
                    )
                    schedule_interval_count += 1
                    schedule_guard_limit_counts[str(
                        schedule_outcome.guard_sector_limit
                    )] += 1
                    scheduled_slots = int(
                        sum(
                            int(record["slot_count_per_second"])
                            for record in schedule_outcome.schedule_records
                            if record["label"] != "baseline"
                        )
                    )
                    total_scheduled_slots_per_second += scheduled_slots
                    maximum_scheduled_slots_per_second = max(
                        maximum_scheduled_slots_per_second, scheduled_slots
                    )
                    maximum_schedule_nonzero_modes = max(
                        maximum_schedule_nonzero_modes,
                        int(schedule_outcome.nonzero_mode_count),
                    )
                    maximum_schedule_critical_sectors = max(
                        maximum_schedule_critical_sectors,
                        len(schedule_outcome.critical_sectors),
                    )
                    maximum_mutable = max(
                        maximum_mutable,
                        len(schedule_outcome.mutable_sectors),
                    )
                    maximum_post_mode_power_ratio = max(
                        maximum_post_mode_power_ratio,
                        float(
                            schedule_outcome.maximum_post_mode_power_ratio
                            or 0.0
                        ),
                    )
                else:
                    unresolved += 1
                    if (
                        schedule_outcome.diagnostic_only
                        and schedule_outcome.status
                        == "DIAGNOSTIC_SCHEDULING_FEASIBLE"
                    ):
                        diagnostic_g8_feasible += 1
                    selected_class = "NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND"

                schedule_records.append(
                    {
                        "interval_index": int(interval),
                        "status": schedule_outcome.status,
                        "guard_sector_limit": int(
                            schedule_outcome.guard_sector_limit
                        ),
                        "diagnostic_only": bool(
                            schedule_outcome.diagnostic_only
                        ),
                        "mode_count": int(schedule_outcome.mode_count),
                        "nonzero_mode_count": int(
                            schedule_outcome.nonzero_mode_count
                        ),
                        "critical_sectors": list(
                            schedule_outcome.critical_sectors
                        ),
                        "mutable_sectors": list(
                            schedule_outcome.mutable_sectors
                        ),
                        "maximum_guard_sector_count": int(
                            schedule_outcome.maximum_guard_sector_count
                        ),
                        "schedule": schedule_outcome.schedule_records,
                    }
                )

            if selected_class == "SPARSE_LOCAL_STREAM_POWER_REPAIR":
                for sector in choice.critical_serving_sectors:
                    sector = int(sector)
                    budget = float(
                        pre_sector[sector] * np.sum(actual_power[sector])
                    )
                    used = float(
                        np.sum(actual_power[sector] * selected_stream[sector])
                    )
                    ratio = (
                        used / budget
                        if budget > 0.0
                        else (0.0 if used <= 1e-18 else math.inf)
                    )
                    maximum_post_mode_power_ratio = max(
                        maximum_post_mode_power_ratio,
                        float(pre_sector[sector] * ratio),
                    )
                    if ratio > 1.0 + 1e-10:
                        strict_power_failures += 1
                    q0_budget = float(
                        pre_sector[sector]
                        * np.sum(nominal_q0_power[sector])
                    )
                    q0_ratio = (
                        used / q0_budget
                        if q0_budget > 0.0
                        else (0.0 if used <= 1e-18 else math.inf)
                    )
                    if ratio > 1.0 + 1e-10 and q0_ratio <= 1.0 + 1e-10:
                        q0_headroom_actions += 1

        used_power_all = np.sum(actual_power * selected_stream, axis=1)
        post_envelope_all = np.sum(actual_power, axis=1)
        post_ratio_all = np.divide(
            used_power_all,
            post_envelope_all,
            out=np.zeros_like(used_power_all),
            where=post_envelope_all > np.finfo(np.float64).tiny,
        )
        maximum_post_mode_power_ratio = max(
            maximum_post_mode_power_ratio,
            float(np.max(post_ratio_all, initial=0.0)),
        )
        q0_envelope_all = np.sum(nominal_q0_power, axis=1)
        q0_ratio_all = np.divide(
            used_power_all,
            q0_envelope_all,
            out=np.zeros_like(used_power_all),
            where=q0_envelope_all > np.finfo(np.float64).tiny,
        )
        maximum_q0_power_ratio = max(
            maximum_q0_power_ratio,
            float(np.max(q0_ratio_all, initial=0.0)),
        )

        if not scope_ok:
            strict_scope_failures += 1
        action_counts[selected_class] += 1
        average_stream_scale[interval] = selected_stream
        sector_equivalent[interval] = selected_sector
        action_class[interval] = selected_class
        total[interval] = selected_audit.delivered_total_rate
        protected[interval] = selected_audit.delivered_protected_rate
        long_ratio[start:stop] = selected_audit.long_ratio
        short_ratio[start:stop] = selected_audit.short_ratio
        count, shortfall, max_shortfall = _floor_metrics(
            total[interval], state.active_user, eligible, floors[interval]
        )
        floor_count[interval] = count
        normalized_shortfall[interval] = shortfall
        maximum_shortfall[interval] = max_shortfall
        current_average = (
            (1.0 - float(alpha)) * current_average
            + float(alpha) * total[interval]
        )
        average_trace[interval] = current_average
        if np.all(selected_stream <= 1e-12):
            network_shutdown += 1

        interval_records.append(
            {
                "interval_index": int(interval),
                "interval_seconds": int(interval_lengths[interval]),
                "pre_repair_violating_users": violating_users.tolist(),
                "chosen_action_class": selected_class,
                "scope": scope_record,
                "strict_local_scope_gate": "PASS" if scope_ok else "FAIL",
                "strict_post_mode_selected_power_gate": (
                    "PASS"
                    if (
                        schedule_outcome is None
                        or (
                            schedule_outcome.maximum_post_mode_power_ratio
                            is not None
                            and schedule_outcome.maximum_post_mode_power_ratio
                            <= 1.0 + 1e-10
                        )
                    )
                    else "FAIL"
                ),
                "candidate_floor_violation_count": int(count),
                "candidate_long_violation_seconds": int(
                    np.sum(selected_audit.long_ratio > 1.0 + 1e-10)
                ),
                "candidate_short_violation_seconds": int(
                    np.sum(selected_audit.short_ratio > 1.0 + 1e-10)
                ),
                "schedule_status": (
                    None
                    if schedule_outcome is None
                    else schedule_outcome.status
                ),
                "information_exchange_locality_certified": False,
            }
        )

    mute = np.all(average_stream_scale <= 1e-12, axis=2)
    sector_backoff = np.full_like(sector_equivalent, math.inf)
    positive = ~mute
    sector_backoff[positive] = -10.0 * np.log10(
        np.maximum(sector_equivalent[positive], 1e-300)
    )
    strict_scope_gate = strict_scope_failures == 0
    strict_power_gate = strict_power_failures == 0
    baseline_stream_trace = np.repeat(
        pre_repair_sector[:, :, None], stream_count, axis=2
    )
    changed_stream_count_trace = np.sum(
        np.abs(average_stream_scale - baseline_stream_trace) > 1e-8,
        axis=(1, 2),
    ).astype(np.int64)
    changed_sector_count_trace = np.sum(
        np.any(
            np.abs(average_stream_scale - baseline_stream_trace) > 1e-8,
            axis=2,
        ),
        axis=1,
    ).astype(np.int64)
    incremental_payload_trace = (
        4 * changed_stream_count_trace
        + 4 * schedule_nonzero_mode_count
        + 2 * schedule_mutable_sector_count
    ).astype(np.int64)
    nonzero_repair = repair_seconds[repair_seconds > 0.0]
    diagnostics: dict[str, Any] = {
        "action_class_counts": dict(action_counts),
        "strict_local_scope_gate": "PASS" if strict_scope_gate else "FAIL",
        "strict_local_scope_violation_intervals": int(strict_scope_failures),
        "strict_post_mode_selected_power_gate": (
            "PASS" if strict_power_gate else "FAIL"
        ),
        "strict_post_mode_power_violation_intervals": int(
            strict_power_failures
        ),
        "q0_envelope_deployable_actions": int(q0_headroom_actions),
        "unresolved_deployable_intervals": int(unresolved),
        "diagnostic_g8_scheduling_feasible_intervals": int(
            diagnostic_g8_feasible
        ),
        "network_wide_shutdown_intervals": int(network_shutdown),
        "maximum_normalized_floor_shortfall": float(
            np.max(maximum_shortfall, initial=0.0)
        ),
        "maximum_mutable_sector_count": int(maximum_mutable),
        "maximum_external_interferers_per_violating_user": int(
            maximum_external_per_user
        ),
        "maximum_eess_backoff_sectors": int(maximum_eess),
        "maximum_post_mode_selected_power_ratio": float(
            maximum_post_mode_power_ratio
        ),
        "maximum_strict_post_mode_selected_power_ratio": float(
            maximum_post_mode_power_ratio
        ),
        "maximum_q0_nominal_power_envelope_ratio": float(
            maximum_q0_power_ratio
        ),
        "protected_subband_scheduling_intervals": int(
            schedule_interval_count
        ),
        "protected_subband_scheduling_success_intervals": int(
            schedule_interval_count
        ),
        "protected_subband_scheduling_failure_intervals": int(
            schedule_attempt_count - schedule_interval_count
        ),
        "protected_subband_scheduling_guard_limit_counts": dict(
            schedule_guard_limit_counts
        ),
        "maximum_schedule_mode_count": int(maximum_schedule_modes),
        "maximum_schedule_guard_sector_count": int(
            maximum_schedule_guard
        ),
        "schedule_slots_per_second": int(scheduler.SLOTS_PER_SECOND),
        "scheduled_nonbaseline_slots_per_second_sum": int(
            total_scheduled_slots_per_second
        ),
        "maximum_scheduled_nonbaseline_slots_per_second": int(
            maximum_scheduled_slots_per_second
        ),
        "maximum_protected_subband_scheduled_fraction": float(
            maximum_scheduled_slots_per_second / scheduler.SLOTS_PER_SECOND
        ),
        "maximum_schedule_nonzero_mode_count": int(
            maximum_schedule_nonzero_modes
        ),
        "maximum_schedule_critical_sector_count": int(
            maximum_schedule_critical_sectors
        ),
        "maximum_schedule_mutable_sector_count": int(
            np.max(schedule_mutable_sector_count, initial=0)
        ),
        "local_table_build_seconds_sum": float(np.sum(local_build)),
        "local_table_build_seconds_max": float(
            np.max(local_build, initial=0.0)
        ),
        "repair_solver_seconds_sum": float(np.sum(repair_seconds)),
        "repair_solver_seconds_max": float(
            np.max(repair_seconds, initial=0.0)
        ),
        "repair_solver_seconds_p95_nonzero": float(
            np.quantile(nonzero_repair, 0.95)
            if len(nonzero_repair)
            else 0.0
        ),
        "schedule_solver_seconds_sum": float(np.sum(schedule_seconds)),
        "schedule_solver_seconds_max": float(
            np.max(schedule_seconds, initial=0.0)
        ),
        "candidate_end_to_end_seconds": float(
            time.perf_counter() - started
        ),
        "information_exchange_locality_certified": False,
        "action_scope_locality_verified": bool(strict_scope_gate),
        "global_oracles_classification_only": True,
        "changed_stream_coefficient_count_sum": int(
            np.sum(changed_stream_count_trace)
        ),
        "changed_sector_interval_count_sum": int(
            np.sum(changed_sector_count_trace)
        ),
        "maximum_changed_stream_coefficients_per_interval": int(
            np.max(changed_stream_count_trace, initial=0)
        ),
        "maximum_changed_sectors_per_interval": int(
            np.max(changed_sector_count_trace, initial=0)
        ),
        "incremental_float32_payload_lower_bound_bytes_sum": int(
            np.sum(incremental_payload_trace)
        ),
        "payload_claim_boundary": (
            "LOWER_BOUND_FOR_CHANGED_FLOAT32_STREAM_COEFFICIENTS_PLUS_"
            "SCHEDULE_COUNTS_NOT_A_SERIALIZED_PROTOCOL_MEASUREMENT"
        ),
        "candidate_stream_scale": average_stream_scale,
        "candidate_action_class": action_class,
        "candidate_pre_repair_sector_scale": pre_repair_sector,
        "candidate_maximum_shortfall_trace": maximum_shortfall,
        "candidate_changed_stream_coefficient_count_trace": (
            changed_stream_count_trace
        ),
        "candidate_changed_sector_count_trace": (
            changed_sector_count_trace
        ),
        "candidate_incremental_float32_payload_lower_bound_bytes_trace": (
            incremental_payload_trace
        ),
        "candidate_schedule_mode_count_trace": schedule_mode_count,
        "candidate_schedule_nonzero_mode_count_trace": (
            schedule_nonzero_mode_count
        ),
        "candidate_schedule_guard_sector_limit_trace": (
            schedule_guard_sector_limit
        ),
        "candidate_schedule_mutable_sector_count_trace": (
            schedule_mutable_sector_count
        ),
        "interval_records": interval_records,
        "schedule_records": schedule_records,
        "claim_boundary": (
            "DEVELOPMENT_REPLAY_ON_PREVIOUSLY_OBSERVED_SEEDS_NOT_"
            "CONFIRMATORY_NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE"
        ),
    }
    extra = {
        key: value
        for key, value in diagnostics.items()
        if key
        not in {
            "candidate_stream_scale",
            "candidate_action_class",
            "candidate_pre_repair_sector_scale",
            "candidate_maximum_shortfall_trace",
            "candidate_changed_stream_coefficient_count_trace",
            "candidate_changed_sector_count_trace",
            "candidate_incremental_float32_payload_lower_bound_bytes_trace",
            "candidate_schedule_mode_count_trace",
            "candidate_schedule_nonzero_mode_count_trace",
            "candidate_schedule_guard_sector_limit_trace",
            "candidate_schedule_mutable_sector_count_trace",
            "interval_records",
            "schedule_records",
        }
    }
    run = EvaluatedRun(
        method_id=CANDIDATE_METHOD_ID,
        q_db=np.asarray(predictive_run.q_db, dtype=np.float64),
        sector_power_scale=sector_equivalent,
        long_ratio=long_ratio,
        short_ratio=short_ratio,
        delivered_total_rate=total,
        delivered_protected_rate=protected,
        moving_average_rate=average_trace,
        floor_violation_count=floor_count,
        normalized_shortfall=normalized_shortfall,
        sector_backoff_db=sector_backoff,
        local_table_build_seconds=local_build,
        runtime_seconds=float(time.perf_counter() - started),
        extra=extra,
    )
    return run, diagnostics
