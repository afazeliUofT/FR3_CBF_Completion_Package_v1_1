"""Campaign integration of frozen candidate v4.3.

This module preserves the v4.3 action hierarchy and scientific tolerances while
making the excluded-seed implementation reusable for arbitrary campaign
channels.  It returns an ``EvaluatedRun`` compatible with the frozen phase-1
runtime plus explicit action/power/locality diagnostics.

The selected action is always sparse and local.  Global feasibility problems
inside ``repair_interval`` are diagnostic/classification oracles and are not a
basis for a distributed-information claim; the campaign records that boundary.
"""
from __future__ import annotations

from collections import Counter
import math
import time
from typing import Any, Sequence

import numpy as np

from fr3_cbf.phase1_job_runtime import EvaluatedRun
from fr3_cbf.null_floor_aware_sector_backoff import (
    SectorBackoffPriceAllocator,
    build_local_cost_table,
)
from fr3_cbf import floor_feasibility_repair as repair

CANDIDATE_METHOD_ID = "candidate_v4_3_floor_feasibility_repair"
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
    violating = valid & (delivered < floors - repair.FLOOR_COMPARISON_TOLERANCE)
    normalized = np.zeros_like(delivered)
    normalized[valid] = np.maximum(
        0.0,
        (floors[valid] - delivered[valid]) / floors[valid],
    )
    return int(np.sum(violating)), float(np.sum(normalized)), float(np.max(normalized, initial=0.0))


def _strict_scope_check(
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
    allowed_external = 2 * len(violating_users)
    expected_critical = {
        int(serving_bs[int(user)]) for user in np.asarray(violating_users, dtype=np.int64)
    }
    scope_ok = (
        len(external) <= allowed_external
        and len(eess) <= 2
        and set(mutable) == (set(critical) | set(external) | set(eess))
        and set(critical) == expected_critical
    )
    immutable = sorted(set(range(pre_stream.shape[0])) - set(mutable))
    unchanged = True
    if immutable:
        unchanged = bool(
            np.allclose(
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
    result = bool(scope_ok and unchanged and scalar_ok and nonincrease_ok)
    return result, {
        "mutable_sectors": list(mutable),
        "critical_serving_sectors": list(critical),
        "external_interferer_sectors": list(external),
        "eess_backoff_sectors": list(eess),
        "immutable_sectors_unchanged": unchanged,
        "external_eess_actions_scalar": scalar_ok,
        "external_eess_actions_nonincreasing": nonincrease_ok,
    }


def run_candidate_v4_3(
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
    """Evaluate frozen candidate v4.3 for one protected pass.

    The mode trajectory is inherited from the reviewed predictive controller.
    The sector fallback is recomputed sequentially using the candidate's own
    moving-PF state, then repaired only when a hard floor/EESS constraint is
    violated.
    """
    started = time.perf_counter()
    states = list(states)
    matrices = list(matrices)
    K = len(states)
    if K == 0:
        raise ValueError("at least one interval is required")
    if len(matrix_indices) != K or len(interval_lengths) != K:
        raise ValueError("interval dimensions do not align")
    serving = np.asarray(serving, dtype=np.int64)
    stream = np.asarray(stream, dtype=np.int64)
    eligible = np.asarray(eligible, dtype=bool)
    floors = np.asarray(floors, dtype=np.float64)
    sector_count = int(np.asarray(states[0].mode_leakage_w).shape[0])
    stream_count = int(np.asarray(matrices[0].perpendicular).shape[-1])
    user_count = len(serving)

    total = np.empty((K, user_count), dtype=np.float64)
    protected = np.empty_like(total)
    average_trace = np.empty_like(total)
    floor_count = np.empty(K, dtype=np.int64)
    normalized_shortfall = np.empty(K, dtype=np.float64)
    maximum_shortfall = np.empty(K, dtype=np.float64)
    stream_scale = np.empty((K, sector_count, stream_count), dtype=np.float64)
    sector_equivalent = np.empty((K, sector_count), dtype=np.float64)
    pre_repair_sector = np.empty((K, sector_count), dtype=np.float64)
    action_class = np.empty(K, dtype="U96")
    long_ratio = np.empty(len(long_kappa), dtype=np.float64)
    short_ratio = np.empty(len(short_kappa), dtype=np.float64)
    local_build = np.empty(K, dtype=np.float64)
    repair_seconds = np.zeros(K, dtype=np.float64)
    changed_stream_coefficient_count = np.zeros(K, dtype=np.int64)
    changed_sector_count = np.zeros(K, dtype=np.int64)
    incremental_float32_payload_lower_bound_bytes = np.zeros(K, dtype=np.int64)
    current_average = np.asarray(initial_average, dtype=np.float64).copy()
    allocator = SectorBackoffPriceAllocator(np.asarray(GRID_DB, dtype=np.float64))

    action_counts: Counter[str] = Counter()
    maximum_mutable = 0
    maximum_external_per_user = 0
    maximum_eess = 0
    strict_scope_failures = 0
    strict_power_failures = 0
    q0_headroom_actions = 0
    maximum_strict_post_mode_ratio = 0.0
    maximum_q0_envelope_ratio = 0.0
    unresolved = 0
    network_shutdown = 0
    interval_records: list[dict[str, Any]] = []

    for interval, state in enumerate(states):
        start = interval * int(update_interval_s)
        stop = min(start + int(update_interval_s), len(long_kappa))
        if stop <= start:
            raise ValueError("empty physical-second interval")
        q = np.asarray(predictive_run.q_db[interval], dtype=np.float64)
        matrix = matrices[int(matrix_indices[interval])]
        amplitude = repair.mode_adjusted_amplitude(state, q)
        gain = np.abs(amplitude) ** 2
        leakage, actual_stream_power, nominal_q0_stream_power = (
            repair.stream_leakage_and_power_envelopes(
                matrix,
                q,
                steering1,
                steering2,
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
                / np.asarray(long_allowance[start:stop], dtype=np.float64)[:, None],
                axis=0,
            )
        )
        _, pre_sector, _, _, pre_feasible = allocator.solve(local_cost, envelope)
        if not pre_feasible:
            raise RuntimeError(
                f"interval {interval}: sequential sector fallback infeasible despite mute"
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

        choice = None
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
            scope_ok, scope_record = _strict_scope_check(
                choice=choice,
                pre_stream=pre_stream,
                selected_stream=selected_stream,
                violating_users=violating_users,
                serving_bs=serving,
            )
            if not scope_ok:
                strict_scope_failures += 1
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

            strict_power_ok = True
            interval_q0_only = False
            interval_strict_ratio = 0.0
            interval_q0_ratio = 0.0
            if selected_class == "SPARSE_LOCAL_STREAM_POWER_REPAIR":
                for sector in choice.critical_serving_sectors:
                    sector = int(sector)
                    strict_budget = float(
                        pre_sector[sector] * np.sum(actual_stream_power[sector])
                    )
                    q0_budget = float(
                        pre_sector[sector] * np.sum(nominal_q0_stream_power[sector])
                    )
                    selected_power = float(
                        np.sum(actual_stream_power[sector] * selected_stream[sector])
                    )
                    strict_ratio = (
                        selected_power / strict_budget
                        if strict_budget > 0.0
                        else (0.0 if selected_power <= 1e-18 else math.inf)
                    )
                    q0_ratio = (
                        selected_power / q0_budget
                        if q0_budget > 0.0
                        else (0.0 if selected_power <= 1e-18 else math.inf)
                    )
                    interval_strict_ratio = max(interval_strict_ratio, strict_ratio)
                    interval_q0_ratio = max(interval_q0_ratio, q0_ratio)
                    maximum_strict_post_mode_ratio = max(
                        maximum_strict_post_mode_ratio, strict_ratio
                    )
                    maximum_q0_envelope_ratio = max(
                        maximum_q0_envelope_ratio, q0_ratio
                    )
                    if strict_ratio > 1.0 + 1e-10:
                        strict_power_ok = False
                        if q0_ratio <= 1.0 + 1e-10:
                            interval_q0_only = True
                # q=0 is diagnostic only.  A q0-only witness is never deployed.
                if not strict_power_ok:
                    strict_power_failures += 1
                if interval_q0_only:
                    q0_headroom_actions += 1
            if selected_class == "NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND":
                unresolved += 1
            interval_records.append(
                {
                    "interval_index": int(interval),
                    "interval_seconds": int(interval_lengths[interval]),
                    "pre_repair_violating_users": violating_users.tolist(),
                    "chosen_action_class": selected_class,
                    "scope": scope_record,
                    "strict_local_scope_gate": "PASS" if scope_ok else "FAIL",
                    "strict_post_mode_selected_power_gate": (
                        "PASS" if strict_power_ok else "FAIL"
                    ),
                    "candidate_floor_violation_count": int(
                        selected_audit.floor_violation_count
                    ),
                    "candidate_long_violation_seconds": int(
                        selected_audit.long_violation_seconds
                    ),
                    "candidate_short_violation_seconds": int(
                        selected_audit.short_violation_seconds
                    ),
                    "maximum_strict_post_mode_power_ratio": float(
                        interval_strict_ratio
                    ),
                    "maximum_q0_power_envelope_ratio": float(interval_q0_ratio),
                    "global_oracles_used_for_classification": True,
                    "information_exchange_locality_certified": False,
                }
            )
        else:
            selected_stream = pre_stream
            selected_sector = pre_sector
            selected_audit = pre_audit
            selected_class = "BASELINE_NOOP"

        changed_mask = np.abs(selected_stream - pre_stream) > 1e-12
        changed_stream_coefficient_count[interval] = int(np.sum(changed_mask))
        changed_sector_count[interval] = int(np.sum(np.any(changed_mask, axis=1)))
        # This is a protocol-independent lower bound: four bytes per changed
        # float32 coefficient, excluding sector IDs, headers, reliability, and
        # transport overhead. It is not a deployed signalling-byte claim.
        incremental_float32_payload_lower_bound_bytes[interval] = int(
            4 * changed_stream_coefficient_count[interval]
        )
        action_counts[selected_class] += 1
        stream_scale[interval] = selected_stream
        sector_equivalent[interval] = selected_sector
        action_class[interval] = selected_class
        total[interval] = selected_audit.delivered_total_rate
        protected[interval] = selected_audit.delivered_protected_rate
        long_ratio[start:stop] = selected_audit.long_ratio
        short_ratio[start:stop] = selected_audit.short_ratio
        count, shortfall, max_shortfall = _floor_metrics(
            total[interval],
            state.active_user,
            eligible,
            floors[interval],
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

    mute = np.all(stream_scale <= 1e-12, axis=2)
    sector_backoff = np.full_like(sector_equivalent, math.inf, dtype=np.float64)
    positive = ~mute
    sector_backoff[positive] = -10.0 * np.log10(
        np.maximum(sector_equivalent[positive], 1e-300)
    )
    strict_scope_gate = strict_scope_failures == 0
    strict_power_gate = strict_power_failures == 0
    diagnostics: dict[str, Any] = {
        "action_class_counts": dict(action_counts),
        "maximum_mutable_sector_count": int(maximum_mutable),
        "maximum_external_interferers_per_violating_user": int(
            maximum_external_per_user
        ),
        "maximum_eess_backoff_sectors": int(maximum_eess),
        "strict_local_scope_gate": "PASS" if strict_scope_gate else "FAIL",
        "strict_local_scope_violation_intervals": int(strict_scope_failures),
        "strict_post_mode_selected_power_gate": (
            "PASS" if strict_power_gate else "FAIL"
        ),
        "strict_post_mode_power_violation_intervals": int(strict_power_failures),
        "q0_envelope_deployable_actions": int(q0_headroom_actions),
        "maximum_strict_post_mode_selected_power_ratio": float(
            maximum_strict_post_mode_ratio
        ),
        "maximum_q0_nominal_power_envelope_ratio": float(
            maximum_q0_envelope_ratio
        ),
        "unresolved_deployable_intervals": int(unresolved),
        "network_wide_shutdown_intervals": int(network_shutdown),
        "maximum_normalized_floor_shortfall": float(
            np.max(maximum_shortfall, initial=0.0)
        ),
        "solver_constraint_reserve": float(repair.SOLVER_CONSTRAINT_RESERVE),
        "solver_primal_feasibility_tolerance": float(
            repair.SOLVER_PRIMAL_FEASIBILITY_TOLERANCE
        ),
        "solver_dual_feasibility_tolerance": float(
            repair.SOLVER_DUAL_FEASIBILITY_TOLERANCE
        ),
        "local_table_build_seconds_sum": float(np.sum(local_build)),
        "repair_solver_seconds_sum": float(np.sum(repair_seconds)),
        "local_table_build_seconds_max": float(np.max(local_build, initial=0.0)),
        "repair_solver_seconds_max": float(np.max(repair_seconds, initial=0.0)),
        "repair_solver_seconds_p95_nonzero": float(
            np.quantile(repair_seconds[repair_seconds > 0.0], 0.95)
            if np.any(repair_seconds > 0.0)
            else 0.0
        ),
        "candidate_end_to_end_seconds": float(time.perf_counter() - started),
        "changed_stream_coefficient_count_sum": int(
            np.sum(changed_stream_coefficient_count)
        ),
        "changed_sector_interval_count_sum": int(np.sum(changed_sector_count)),
        "maximum_changed_stream_coefficients_per_interval": int(
            np.max(changed_stream_coefficient_count, initial=0)
        ),
        "maximum_changed_sectors_per_interval": int(
            np.max(changed_sector_count, initial=0)
        ),
        "incremental_float32_payload_lower_bound_bytes_sum": int(
            np.sum(incremental_float32_payload_lower_bound_bytes)
        ),
        "payload_claim_boundary": (
            "FLOAT32_COEFFICIENT_VALUE_LOWER_BOUND_ONLY_EXCLUDES_IDS_HEADERS_"
            "RELIABILITY_AND_TRANSPORT_OVERHEAD"
        ),
        "information_exchange_locality_certified": False,
        "action_scope_locality_verified": bool(strict_scope_gate),
        "global_oracles_classification_only": True,
        "interval_records": interval_records,
        "candidate_stream_scale": stream_scale,
        "candidate_action_class": action_class,
        "candidate_pre_repair_sector_scale": pre_repair_sector,
        "candidate_maximum_shortfall_trace": maximum_shortfall,
        "candidate_changed_stream_coefficient_count_trace": (
            changed_stream_coefficient_count
        ),
        "candidate_changed_sector_count_trace": changed_sector_count,
        "candidate_incremental_float32_payload_lower_bound_bytes_trace": (
            incremental_float32_payload_lower_bound_bytes
        ),
    }
    extra = {
        key: value
        for key, value in diagnostics.items()
        if key
        not in {
            "interval_records",
            "candidate_stream_scale",
            "candidate_action_class",
            "candidate_pre_repair_sector_scale",
            "candidate_maximum_shortfall_trace",
            "candidate_changed_stream_coefficient_count_trace",
            "candidate_changed_sector_count_trace",
            "candidate_incremental_float32_payload_lower_bound_bytes_trace",
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
