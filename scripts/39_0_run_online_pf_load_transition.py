#!/usr/bin/env python3
"""Run online moving-average PF with deterministic load transitions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from fr3_cbf.constrained_pf_safety import (
    PriceAllocator,
    action_grid,
)
from fr3_cbf.online_pf_load_transition import (
    LoadState,
    build_online_moving_pf_cost_grid,
    build_rotating_load_schedule,
    evaluate_actions_across_states,
    exact_second_safety_ratio_dynamic,
    exponential_average_alpha,
    finite_pass_dynamic_certificate,
    full_horizon_dynamic_envelope,
    recompute_load_state,
    sequential_average_trace,
    simulate_online_myopic_controller,
    simulate_online_predictive_controller,
)
from fr3_cbf.robust_delayed_safety import (
    simulate_full_horizon_predictive,
)

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    fieldnames = list(rows[0])
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quantiles(values: np.ndarray) -> dict[str, float]:
    value = np.asarray(values, dtype=float)
    return {
        name: float(np.quantile(value, q))
        for name, q in [
            ("minimum", 0.0),
            ("p01", 0.01),
            ("p05", 0.05),
            ("p10", 0.10),
            ("median", 0.50),
            ("p90", 0.90),
            ("p95", 0.95),
            ("p99", 0.99),
            ("maximum", 1.0),
        ]
    }


def interval_bounds(
    second_array: np.ndarray,
    update_interval_s: int,
    reducer: str,
) -> tuple[np.ndarray, np.ndarray]:
    value = np.asarray(second_array)
    rows = []
    lengths = []
    for start in range(0, len(value), update_interval_s):
        stop = min(start + update_interval_s, len(value))
        if reducer == "max":
            rows.append(np.max(value[start:stop], axis=0))
        elif reducer == "min":
            rows.append(np.min(value[start:stop], axis=0))
        else:
            raise ValueError("unknown reducer")
        lengths.append(stop - start)
    return np.asarray(rows), np.asarray(lengths, dtype=np.int64)


def moving_pf_metrics(
    delivered_total: np.ndarray,
    delivered_protected: np.ndarray,
    moving_average: np.ndarray,
    states: list[LoadState],
    floors: np.ndarray,
    eligible: np.ndarray,
    indoor: np.ndarray,
    interval_lengths: np.ndarray,
    epsilon: float,
) -> dict[str, object]:
    total = np.asarray(delivered_total, dtype=float)
    protected = np.asarray(delivered_protected, dtype=float)
    average = np.asarray(moving_average, dtype=float)
    floor = np.asarray(floors, dtype=float)
    lengths = np.asarray(interval_lengths, dtype=np.int64)
    active = np.stack(
        [state.active_user for state in states],
        axis=0,
    )
    active_eligible = active & eligible[None, :]
    floor_violation = (
        active_eligible
        & (total < floor - 1e-12)
    )
    shortfall = np.zeros_like(total)
    valid_floor = active_eligible & (floor > 0)
    shortfall[valid_floor] = np.maximum(
        0.0,
        (
            floor[valid_floor]
            - total[valid_floor]
        )
        / floor[valid_floor],
    )

    moving_pf = np.log(
        average[:, eligible] + float(epsilon)
    ).sum(axis=1)
    moving_geometric = (
        np.exp(
            np.log(
                average[:, eligible] + float(epsilon)
            ).mean(axis=1)
        )
        - float(epsilon)
    )

    active_p05 = []
    active_min = []
    active_pf = []
    active_geometric = []
    for interval in range(len(total)):
        mask = active_eligible[interval]
        rate = total[interval, mask]
        active_p05.append(float(np.quantile(rate, 0.05)))
        active_min.append(float(rate.min()))
        active_pf.append(
            float(np.log(rate + float(epsilon)).sum())
        )
        active_geometric.append(
            float(
                np.exp(
                    np.log(rate + float(epsilon)).mean()
                )
                - float(epsilon)
            )
        )

    group_metrics: dict[str, dict[str, object]] = {}
    for name, group in [
        ("eligible_all", eligible),
        ("eligible_indoor", eligible & indoor),
        ("eligible_outdoor", eligible & (~indoor)),
        ("coverage_limited_all", ~eligible),
        ("coverage_limited_indoor", (~eligible) & indoor),
        ("coverage_limited_outdoor", (~eligible) & (~indoor)),
    ]:
        if not np.any(group):
            group_metrics[name] = {"user_count": 0}
            continue
        group_active = active & group[None, :]
        values = total[group_active]
        protected_values = protected[group_active]
        group_metrics[name] = {
            "user_count": int(group.sum()),
            "active_user_interval_count": int(
                group_active.sum()
            ),
            "mean_active_total_rate_bps_hz": float(
                values.mean()
            ),
            "p05_active_total_rate_bps_hz": float(
                np.quantile(values, 0.05)
            ),
            "minimum_active_total_rate_bps_hz": float(
                values.min()
            ),
            "mean_active_protected_rate_bps_hz": float(
                protected_values.mean()
            ),
            "minimum_active_protected_rate_bps_hz": float(
                protected_values.min()
            ),
            "final_moving_average_geometric_rate_bps_hz": float(
                np.exp(
                    np.log(
                        average[-1, group]
                        + float(epsilon)
                    ).mean()
                )
                - float(epsilon)
            ),
        }

    nominal_total_network = np.asarray(
        [state.nominal_total_rate.sum() for state in states],
        dtype=float,
    )
    nominal_protected_network = np.asarray(
        [
            state.nominal_protected_rate.sum()
            for state in states
        ],
        dtype=float,
    )
    delivered_total_network = total.sum(axis=1)
    delivered_protected_network = protected.sum(axis=1)

    return {
        "eligible_floor_violation_interval_count": int(
            floor_violation.any(axis=1).sum()
        ),
        "eligible_floor_violation_user_interval_count": int(
            floor_violation.sum()
        ),
        "unique_eligible_floor_violation_user_count": int(
            floor_violation.any(axis=0).sum()
        ),
        "total_normalized_floor_shortfall_user_seconds": float(
            (shortfall * lengths[:, None]).sum()
        ),
        "maximum_normalized_floor_shortfall": float(
            shortfall.max()
        ),
        "minimum_floor_ratio": float(
            np.min(
                total[active_eligible]
                / floor[active_eligible]
            )
        ),
        "mean_moving_pf_utility": float(
            np.average(moving_pf, weights=lengths)
        ),
        "minimum_moving_pf_utility": float(
            moving_pf.min()
        ),
        "final_moving_pf_utility": float(
            moving_pf[-1]
        ),
        "mean_moving_geometric_rate_bps_hz": float(
            np.average(moving_geometric, weights=lengths)
        ),
        "final_moving_geometric_rate_bps_hz": float(
            moving_geometric[-1]
        ),
        "mean_active_instantaneous_pf_utility": float(
            np.average(active_pf, weights=lengths)
        ),
        "mean_active_geometric_rate_bps_hz": float(
            np.average(active_geometric, weights=lengths)
        ),
        "mean_active_p05_rate_bps_hz": float(
            np.average(active_p05, weights=lengths)
        ),
        "minimum_active_p05_rate_bps_hz": float(
            np.min(active_p05)
        ),
        "minimum_active_eligible_rate_bps_hz": float(
            np.min(active_min)
        ),
        "mean_total_network_retention_secondary": float(
            np.average(
                delivered_total_network
                / nominal_total_network,
                weights=lengths,
            )
        ),
        "minimum_total_network_retention_secondary": float(
            np.min(
                delivered_total_network
                / nominal_total_network
            )
        ),
        "mean_protected_network_retention_secondary": float(
            np.average(
                delivered_protected_network
                / nominal_protected_network,
                weights=lengths,
            )
        ),
        "minimum_protected_network_retention_secondary": float(
            np.min(
                delivered_protected_network
                / nominal_protected_network
            )
        ),
        "user_final_moving_average_quantiles": quantiles(
            average[-1, eligible]
        ),
        "groups": group_metrics,
    }


def control_metrics(
    command: np.ndarray,
    applied: np.ndarray,
    build_seconds: np.ndarray | None = None,
) -> dict[str, float]:
    difference = (
        np.diff(command, axis=0)
        if len(command) > 1
        else np.zeros((0, 57, 2))
    )
    result = {
        "command_total_variation_db": float(
            np.abs(difference).sum()
        ),
        "maximum_command_slew_db": float(
            np.abs(difference).max()
            if difference.size
            else 0.0
        ),
        "mean_active_mode_count": float(
            np.mean(
                np.sum(applied > 0.0, axis=(1, 2))
            )
        ),
        "maximum_active_mode_count": float(
            np.max(
                np.sum(applied > 0.0, axis=(1, 2))
            )
        ),
        "payload_bytes_per_update": float(57 * 2 * 4),
    }
    if build_seconds is not None:
        result.update(
            {
                "mean_local_table_build_seconds": float(
                    np.mean(build_seconds)
                ),
                "maximum_local_table_build_seconds": float(
                    np.max(build_seconds)
                ),
            }
        )
    return result


def static_action(
    q_grid: np.ndarray,
    state: LoadState,
    average: np.ndarray,
    eligible: np.ndarray,
    floor: np.ndarray,
    serving: np.ndarray,
    stream: np.ndarray,
    noise: float,
    protected_weight: float,
    alpha: float,
    epsilon: float,
    maximum_upper_contribution: np.ndarray,
    allowance: float,
) -> tuple[np.ndarray, dict[str, object]]:
    cost, audit = build_online_moving_pf_cost_grid(
        q_grid,
        state,
        np.zeros((57, 2), dtype=float),
        average,
        eligible,
        floor,
        serving,
        stream,
        noise,
        protected_weight,
        alpha,
        epsilon,
    )
    allocator = PriceAllocator(q_grid, cost, allowance)
    action, ratio, feasible, price = allocator.solve(
        maximum_upper_contribution
    )
    if not feasible or ratio > 1.0 + 1e-10:
        raise RuntimeError("static robust action is infeasible")
    return action, {
        **audit,
        "normalized_interference_ratio": ratio,
        "price": price,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/online_pf_load_transition_v1.json",
    )
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()
    cfg = json.loads(
        (ROOT / args.config).read_text(encoding="utf-8")
    )
    data = (
        Path(args.data_root).expanduser().resolve()
        if args.data_root
        else (ROOT / cfg["data_root"]).resolve()
    )
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    for path in [results, evidence]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    validation = json.loads(
        (
            data / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json"
        ).read_text(encoding="utf-8")
    )
    if validation["status"] != (
        "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
    ):
        raise ValueError("full-topology data are not V4 validated")

    frequency_response = np.load(
        data / "frequency_response.npy",
        mmap_mode="r",
    )
    serving = np.load(data / "serving_bs_index.npy")
    stream = np.load(data / "serving_stream_index.npy")
    power_f = np.load(
        data / "transmit_power_by_frequency_w.npy"
    )
    noise_f = np.load(
        data / "noise_power_by_frequency_w.npy"
    )
    weights = np.load(data / "frequency_weights.npy")
    steering1 = np.load(
        data / "protected_steering_pol1.npy"
    )
    steering2 = np.load(
        data / "protected_steering_pol2.npy"
    )
    kappa = np.load(data / "kappa_time_sector.npy")
    allowance_second = np.load(
        data / "aggregate_allowance_w.npy"
    )
    time_s = np.load(data / "protected_time_s.npy")
    full_load_nominal = np.load(
        data / "nominal_total_weighted_rate_per_user.npy"
    )
    users = pd.read_csv(data / "USER_TOPOLOGY.csv")
    indoor = users["indoor"].astype(bool).to_numpy()

    update_interval = int(cfg["update_interval_s"])
    interval_count = int(
        math.ceil(len(time_s) / update_interval)
    )
    schedule, phase_records = build_rotating_load_schedule(
        serving,
        stream,
        interval_count,
        cfg["load_schedule"]["phase_lengths_intervals"],
        cfg["load_schedule"][
            "active_streams_per_sector"
        ],
    )

    # Cache one recomputed RZF/decomposition state per unique activity mask.
    state_cache: dict[bytes, LoadState] = {}
    states: list[LoadState] = []
    state_build_records = []
    state_started = time.perf_counter()
    for interval in range(interval_count):
        key = schedule[interval].tobytes()
        if key not in state_cache:
            started = time.perf_counter()
            state_cache[key] = recompute_load_state(
                frequency_response,
                schedule[interval],
                serving,
                stream,
                power_f,
                noise_f,
                weights,
                protected_frequency_index=4,
                steering_pol1=steering1,
                steering_pol2=steering2,
            )
            state_build_records.append(
                {
                    "state_index": len(state_build_records),
                    "first_interval": interval,
                    "active_user_count": int(
                        schedule[interval].sum()
                    ),
                    "build_seconds": (
                        time.perf_counter() - started
                    ),
                }
            )
        states.append(state_cache[key])
    state_build_total = time.perf_counter() - state_started

    # Full-load recomputation check against the validated exporter.
    full_state = states[0]
    full_load_rate_error = float(
        np.max(
            np.abs(
                full_state.nominal_total_rate
                - full_load_nominal
            )
        )
    )
    full_load_reference_sum = float(full_load_nominal.sum())
    full_load_recomputed_sum = float(
        full_state.nominal_total_rate.sum()
    )
    full_load_sum_error = float(
        abs(full_load_recomputed_sum - full_load_reference_sum)
    )
    full_load_sum_relative_error = float(
        full_load_sum_error
        / max(abs(full_load_reference_sum), 1e-300)
    )
    full_load_user_error = (
        full_state.nominal_total_rate - full_load_nominal
    )
    full_load_l1_error = float(
        np.sum(np.abs(full_load_user_error))
    )
    full_load_rms_error = float(
        np.sqrt(np.mean(full_load_user_error**2))
    )
    # The per-user check protects the user-level controller state. The aggregate
    # check must scale with the 228-user network magnitude: reusing the same
    # absolute tolerance for one user and for their sum is not numerically
    # coherent across BLAS/LAPACK implementations.
    if full_load_rate_error > 2e-4:
        raise RuntimeError(
            "local RZF full-load per-user reproduction is outside tolerance: "
            f"{full_load_rate_error}"
        )
    if full_load_sum_relative_error > 5e-6:
        raise RuntimeError(
            "local RZF full-load aggregate relative reproduction is outside "
            f"tolerance: {full_load_sum_relative_error}"
        )

    kappa_interval, interval_lengths = interval_bounds(
        kappa,
        update_interval,
        "max",
    )
    allowance_interval, allowance_lengths = interval_bounds(
        allowance_second,
        update_interval,
        "min",
    )
    if not np.array_equal(interval_lengths, allowance_lengths):
        raise RuntimeError("interval lengths do not align")

    nominal_contribution = np.empty(
        (interval_count, 57, 2),
        dtype=float,
    )
    for interval, state in enumerate(states):
        nominal_contribution[interval] = (
            kappa_interval[interval, :, None]
            * state.mode_leakage_w
        )
    margin_1 = float(cfg["primary_uncertainty_margin_db"])
    margin_3 = float(
        cfg["sensitivity_uncertainty_margin_db"]
    )
    upper_1 = nominal_contribution * 10.0 ** (
        margin_1 / 10.0
    )
    upper_3 = nominal_contribution * 10.0 ** (
        margin_3 / 10.0
    )

    delay = int(cfg["message_delay_intervals"])
    slew = float(cfg["slew_db_per_update"])
    maximum_action = float(cfg["maximum_action_db"])
    app_env_1, cmd_env_1, _preload_1 = (
        full_horizon_dynamic_envelope(
            upper_1,
            delay,
            slew,
        )
    )
    app_env_3, cmd_env_3, _preload_3 = (
        full_horizon_dynamic_envelope(
            upper_3,
            delay,
            slew,
        )
    )

    policy = cfg["fairness_policy"]
    eligible = (
        full_load_nominal
        >= float(
            policy["serviceability_threshold_bps_hz"]
        )
    )
    floors = np.zeros((interval_count, 228), dtype=float)
    for interval, state in enumerate(states):
        active_eligible = state.active_user & eligible
        floors[interval, active_eligible] = np.maximum(
            float(policy["absolute_total_band_floor_bps_hz"]),
            float(
                policy[
                    "relative_current_load_floor_fraction"
                ]
            )
            * state.nominal_total_rate[active_eligible],
        )

    alpha = exponential_average_alpha(
        update_interval,
        float(
            cfg["moving_average"]["time_constant_s"]
        ),
    )
    epsilon = float(
        cfg["moving_average"]["epsilon_bps_hz"]
    )
    initial_average = full_load_nominal.copy()
    q_cfg = cfg["action_grid"]
    q_grid = action_grid(
        int(q_cfg["minimum_db"]),
        int(q_cfg["maximum_db"]),
        int(q_cfg["step_db"]),
    )
    protected_noise = float(noise_f[4])
    protected_weight = float(weights[4])

    runs: dict[str, dict[str, object]] = {}

    def add_online_predictive(
        name: str,
        upper: np.ndarray,
        app_env: np.ndarray,
        cmd_env: np.ndarray,
        margin_db: float,
        drops: tuple[int, ...] = (),
    ) -> None:
        started = time.perf_counter()
        run = simulate_online_predictive_controller(
            q_grid,
            states,
            upper,
            allowance_interval,
            app_env,
            cmd_env,
            delay,
            slew,
            maximum_action,
            initial_average,
            alpha,
            eligible,
            floors,
            serving,
            stream,
            protected_noise,
            protected_weight,
            epsilon,
            fail_safe_drop_command_indices=drops,
        )
        runtime = time.perf_counter() - started
        upper_second, nominal_second = (
            exact_second_safety_ratio_dynamic(
                kappa,
                states,
                run.applied_db,
                update_interval,
                allowance_second,
                margin_db,
            )
        )
        metrics = moving_pf_metrics(
            run.delivered_total_rate,
            run.delivered_protected_rate,
            run.moving_average_rate,
            states,
            floors,
            eligible,
            indoor,
            interval_lengths,
            epsilon,
        )
        certificate = finite_pass_dynamic_certificate(
            run.command_db,
            run.applied_db,
            run.command_feasible,
            app_env,
            cmd_env,
            run.upper_interval_ratio,
            allowance_interval,
            slew,
            maximum_action,
        )
        runs[name] = {
            "run": run,
            "runtime_seconds": runtime,
            "upper_second_ratio": upper_second,
            "nominal_second_ratio": nominal_second,
            "metrics": metrics,
            "certificate": certificate,
            "uncertainty_margin_db": margin_db,
            "fail_safe_drop_command_indices": list(drops),
        }

    add_online_predictive(
        "online_predictive_robust_1db",
        upper_1,
        app_env_1,
        cmd_env_1,
        margin_1,
    )
    add_online_predictive(
        "online_predictive_robust_1db_two_drops",
        upper_1,
        app_env_1,
        cmd_env_1,
        margin_1,
        tuple(
            int(v)
            for v in cfg[
                "message_drop_command_indices"
            ]
        ),
    )
    add_online_predictive(
        "online_predictive_robust_3db",
        upper_3,
        app_env_3,
        cmd_env_3,
        margin_3,
    )

    # Online delayed myopic, using the same 1 dB upper contribution but no
    # future envelope.
    started = time.perf_counter()
    myopic = simulate_online_myopic_controller(
        q_grid,
        states,
        upper_1,
        allowance_interval,
        delay,
        slew,
        initial_average,
        alpha,
        eligible,
        floors,
        serving,
        stream,
        protected_noise,
        protected_weight,
        epsilon,
    )
    myopic_runtime = time.perf_counter() - started
    myopic_upper_second, myopic_nominal_second = (
        exact_second_safety_ratio_dynamic(
            kappa,
            states,
            myopic.applied_db,
            update_interval,
            allowance_second,
            margin_1,
        )
    )
    runs["online_myopic_robust_1db"] = {
        "run": myopic,
        "runtime_seconds": myopic_runtime,
        "upper_second_ratio": myopic_upper_second,
        "nominal_second_ratio": myopic_nominal_second,
        "metrics": moving_pf_metrics(
            myopic.delivered_total_rate,
            myopic.delivered_protected_rate,
            myopic.moving_average_rate,
            states,
            floors,
            eligible,
            indoor,
            interval_lengths,
            epsilon,
        ),
        "certificate": None,
        "uncertainty_margin_db": margin_1,
        "fail_safe_drop_command_indices": [],
    }

    # Static robust reference.
    static_q, static_audit = static_action(
        q_grid,
        states[0],
        initial_average,
        eligible,
        floors[0],
        serving,
        stream,
        protected_noise,
        protected_weight,
        alpha,
        epsilon,
        np.max(upper_1, axis=0),
        float(allowance_interval[0]),
    )
    static_actions = np.repeat(
        static_q[None, :, :],
        interval_count,
        axis=0,
    )
    static_total, static_protected, static_average = (
        evaluate_actions_across_states(
            static_actions,
            states,
            serving,
            stream,
            protected_noise,
            protected_weight,
            initial_average,
            alpha,
        )
    )
    static_upper_second, static_nominal_second = (
        exact_second_safety_ratio_dynamic(
            kappa,
            states,
            static_actions,
            update_interval,
            allowance_second,
            margin_1,
        )
    )
    runs["static_robust_1db"] = {
        "run": None,
        "command_db": static_actions,
        "applied_db": static_actions,
        "delivered_total_rate": static_total,
        "delivered_protected_rate": static_protected,
        "moving_average_rate": static_average,
        "runtime_seconds": 0.0,
        "upper_second_ratio": static_upper_second,
        "nominal_second_ratio": static_nominal_second,
        "metrics": moving_pf_metrics(
            static_total,
            static_protected,
            static_average,
            states,
            floors,
            eligible,
            indoor,
            interval_lengths,
            epsilon,
        ),
        "certificate": None,
        "uncertainty_margin_db": margin_1,
        "fail_safe_drop_command_indices": [],
        "static_audit": static_audit,
    }

    # Frozen local table predictive reference. This quantifies the direct
    # benefit of online moving-average/local-load table rebuilding.
    frozen_cost, frozen_cost_audit = (
        build_online_moving_pf_cost_grid(
            q_grid,
            states[0],
            np.zeros((57, 2), dtype=float),
            initial_average,
            eligible,
            floors[0],
            serving,
            stream,
            protected_noise,
            protected_weight,
            alpha,
            epsilon,
        )
    )
    frozen_allocator = PriceAllocator(
        q_grid,
        frozen_cost,
        float(allowance_interval[0]),
    )
    started = time.perf_counter()
    frozen_robust = simulate_full_horizon_predictive(
        frozen_allocator,
        nominal_contribution,
        allowance_interval,
        delay_intervals=delay,
        slew_db_per_update=slew,
        coupling_upper_margin_db=margin_1,
    )
    frozen_runtime = time.perf_counter() - started
    frozen_total, frozen_protected, frozen_average = (
        evaluate_actions_across_states(
            frozen_robust.applied_db,
            states,
            serving,
            stream,
            protected_noise,
            protected_weight,
            initial_average,
            alpha,
        )
    )
    frozen_upper_second, frozen_nominal_second = (
        exact_second_safety_ratio_dynamic(
            kappa,
            states,
            frozen_robust.applied_db,
            update_interval,
            allowance_second,
            margin_1,
        )
    )
    frozen_certificate = finite_pass_dynamic_certificate(
        frozen_robust.command_db,
        frozen_robust.applied_db,
        frozen_robust.command_feasible,
        frozen_robust.application_envelope_w,
        frozen_robust.command_envelope_w,
        frozen_robust.upper_safety_ratio,
        allowance_interval,
        slew,
        maximum_action,
    )
    runs["frozen_table_predictive_robust_1db"] = {
        "run": frozen_robust,
        "runtime_seconds": frozen_runtime,
        "upper_second_ratio": frozen_upper_second,
        "nominal_second_ratio": frozen_nominal_second,
        "metrics": moving_pf_metrics(
            frozen_total,
            frozen_protected,
            frozen_average,
            states,
            floors,
            eligible,
            indoor,
            interval_lengths,
            epsilon,
        ),
        "certificate": frozen_certificate,
        "uncertainty_margin_db": margin_1,
        "fail_safe_drop_command_indices": [],
        "frozen_cost_audit": frozen_cost_audit,
        "delivered_total_rate": frozen_total,
        "delivered_protected_rate": frozen_protected,
        "moving_average_rate": frozen_average,
    }

    summary_rows: list[dict[str, object]] = []
    time_rows: list[dict[str, object]] = []
    action_arrays: dict[str, np.ndarray] = {}
    for name, record in runs.items():
        run = record.get("run")
        if run is not None:
            command = run.command_db
            applied = run.applied_db
            delivered_total = (
                run.delivered_total_rate
                if hasattr(run, "delivered_total_rate")
                else record["delivered_total_rate"]
            )
            delivered_protected = (
                run.delivered_protected_rate
                if hasattr(run, "delivered_protected_rate")
                else record["delivered_protected_rate"]
            )
            average_trace = (
                run.moving_average_rate
                if hasattr(run, "moving_average_rate")
                else record["moving_average_rate"]
            )
            build_seconds = getattr(
                run,
                "local_table_build_seconds",
                None,
            )
            fail_count = int(
                getattr(
                    run,
                    "fail_safe_used",
                    np.zeros(interval_count, dtype=bool),
                ).sum()
            )
            command_feasible = bool(
                np.all(
                    getattr(
                        run,
                        "command_feasible",
                        np.ones(interval_count, dtype=bool),
                    )
                )
            )
        else:
            command = record["command_db"]
            applied = record["applied_db"]
            delivered_total = record[
                "delivered_total_rate"
            ]
            delivered_protected = record[
                "delivered_protected_rate"
            ]
            average_trace = record["moving_average_rate"]
            build_seconds = None
            fail_count = 0
            command_feasible = True

        upper_second = record["upper_second_ratio"]
        nominal_second = record["nominal_second_ratio"]
        metrics = record["metrics"]
        controls = control_metrics(
            command,
            applied,
            build_seconds,
        )
        certificate_status = (
            record["certificate"]["status"]
            if record["certificate"] is not None
            else "NOT_APPLICABLE"
        )
        row = {
            "controller": name,
            "uncertainty_margin_db": record[
                "uncertainty_margin_db"
            ],
            "command_feasible_all_intervals": (
                command_feasible
            ),
            "upper_bound_violation_seconds": int(
                np.sum(upper_second > 1.0 + 1e-10)
            ),
            "nominal_violation_seconds": int(
                np.sum(nominal_second > 1.0 + 1e-10)
            ),
            "maximum_upper_threshold_excess_db": float(
                10.0 * np.log10(np.max(upper_second))
            ),
            "minimum_nominal_safety_margin_db": float(
                -10.0 * np.log10(
                    np.max(nominal_second)
                )
            ),
            "fail_safe_command_count": fail_count,
            "certificate_status": certificate_status,
            "runtime_seconds": record["runtime_seconds"],
            **{
                key: value
                for key, value in metrics.items()
                if key != "groups"
                and not isinstance(value, dict)
            },
            **controls,
        }
        summary_rows.append(row)
        action_arrays[f"{name}_command_db"] = command
        action_arrays[f"{name}_applied_db"] = applied
        action_arrays[
            f"{name}_moving_average_rate"
        ] = average_trace

        for interval in range(interval_count):
            if len(time_rows) <= interval:
                time_rows.append(
                    {
                        "interval_index": interval,
                        "start_time_s": float(
                            time_s[
                                interval * update_interval
                            ]
                        ),
                        "duration_s": int(
                            interval_lengths[interval]
                        ),
                        "active_user_count": int(
                            schedule[interval].sum()
                        ),
                    }
                )
            time_rows[interval][
                f"{name}_upper_interval_ratio"
            ] = float(
                np.max(
                    upper_second[
                        interval * update_interval :
                        interval * update_interval
                        + interval_lengths[interval]
                    ]
                )
            )
            time_rows[interval][
                f"{name}_moving_pf_utility"
            ] = float(
                np.log(
                    average_trace[interval, eligible]
                    + epsilon
                ).sum()
            )
            time_rows[interval][
                f"{name}_active_total_rate_bps_hz"
            ] = float(
                delivered_total[interval].sum()
            )
            time_rows[interval][
                f"{name}_active_protected_rate_bps_hz"
            ] = float(
                delivered_protected[interval].sum()
            )

    write_csv(
        results / "ONLINE_PF_CONTROLLER_SUMMARY.csv",
        summary_rows,
    )
    write_csv(
        results / "ONLINE_PF_TIME_SERIES.csv",
        time_rows,
    )
    write_csv(
        results / "LOAD_PHASES.csv",
        phase_records,
    )
    write_csv(
        results / "LOAD_STATE_BUILD_AUDIT.csv",
        state_build_records,
    )
    np.savez_compressed(
        results / "ONLINE_PF_ACTIONS_AND_AVERAGES.npz",
        **action_arrays,
    )

    certificates = {
        name: record["certificate"]
        for name, record in runs.items()
        if record["certificate"] is not None
    }
    write_json(
        results / "ONLINE_PF_THEOREM_CERTIFICATES.json",
        certificates,
    )

    by_name = {
        row["controller"]: row
        for row in summary_rows
    }
    online = by_name["online_predictive_robust_1db"]
    dropped = by_name[
        "online_predictive_robust_1db_two_drops"
    ]
    robust3 = by_name["online_predictive_robust_3db"]
    myopic_row = by_name["online_myopic_robust_1db"]
    static_row = by_name["static_robust_1db"]
    frozen_row = by_name[
        "frozen_table_predictive_robust_1db"
    ]

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_ONLINE_MOVING_AVERAGE_PF_LOAD_TRANSITION_REVIEW_REQUIRED"
        ),
        "claim_boundary": cfg["claim_boundary"],
        "data_validation_status": validation["status"],
        "full_load_rzf_reproduction": {
            "maximum_per_user_rate_error_bps_hz": (
                full_load_rate_error
            ),
            "root_mean_square_per_user_error_bps_hz": (
                full_load_rms_error
            ),
            "l1_per_user_error_bps_hz": full_load_l1_error,
            "reference_network_sum_bps_hz": (
                full_load_reference_sum
            ),
            "recomputed_network_sum_bps_hz": (
                full_load_recomputed_sum
            ),
            "network_sum_error_bps_hz": full_load_sum_error,
            "network_sum_relative_error": (
                full_load_sum_relative_error
            ),
            "maximum_per_user_tolerance_bps_hz": 2e-4,
            "network_sum_relative_tolerance": 5e-6,
            "interpretation": (
                "Per-user absolute error protects user-level controller "
                "state; aggregate reproduction is judged relatively because "
                "it sums 228 platform-dependent RZF/rate values."
            ),
        },
        "load_schedule": {
            "interval_count": interval_count,
            "unique_recomputed_load_states": len(state_cache),
            "state_build_total_seconds": state_build_total,
            "phases": phase_records,
        },
        "moving_average": {
            **cfg["moving_average"],
            "alpha": alpha,
        },
        "fairness_policy": policy,
        "controller_rows": by_name,
        "theorem_certificates": certificates,
        "decisive_results": {
            "online_myopic_upper_violation_seconds": (
                myopic_row["upper_bound_violation_seconds"]
            ),
            "online_predictive_1db_upper_violation_seconds": (
                online["upper_bound_violation_seconds"]
            ),
            "online_predictive_1db_drop_upper_violation_seconds": (
                dropped["upper_bound_violation_seconds"]
            ),
            "online_predictive_3db_upper_violation_seconds": (
                robust3["upper_bound_violation_seconds"]
            ),
            "online_predictive_floor_violation_user_intervals": (
                online[
                    "eligible_floor_violation_user_interval_count"
                ]
            ),
            "online_minus_frozen_mean_moving_pf_utility": (
                online["mean_moving_pf_utility"]
                - frozen_row["mean_moving_pf_utility"]
            ),
            "online_minus_static_mean_moving_pf_utility": (
                online["mean_moving_pf_utility"]
                - static_row["mean_moving_pf_utility"]
            ),
            "all_online_predictive_certificates_pass": bool(
                all(
                    certificate["status"]
                    == "PASS_CORRECTED_FINITE_PASS_DYNAMIC_CERTIFICATE"
                    for name, certificate in certificates.items()
                    if name.startswith(
                        "online_predictive"
                    )
                )
            ),
        },
        "theorem_statement_repair": {
            "old_issue": (
                "the prior prose used all-Q safety as a saturation "
                "condition without explicitly certifying the actual "
                "slew-feasible clipped candidate"
            ),
            "corrected_condition": (
                "F(q)=min(q+rho,Q) is checked against the next "
                "command envelope at every finite-pass step"
            ),
        },
        "repository_hygiene": {
            "tracked_pycache_cleanup_required": True,
            "reason": (
                "commit 83ce40b accidentally tracked two generated "
                "__pycache__/pyc artifacts; the push wrapper removes them"
            ),
        },
        "limitations": [
            "one channel/topology seed and one protected pass",
            "deterministic rotating load schedule is a stress test rather than a traffic distribution",
            "future load and geometry are known over the finite pass",
            "1 dB and 3 dB coupling margins remain uncalibrated smoke bounds",
            "online local tables hold other-sector actions at the current applied action",
            "one-dB action grid",
            "no multi-seed confidence intervals or practical-array sensitivity"
        ],
        "multi_seed_spec": (
            "config/multi_seed_campaign_spec_v1.json"
        ),
        "next_gate": cfg["next_gate"],
    }
    write_json(
        results / "ONLINE_PF_LOAD_TRANSITION_AUDIT.json",
        audit,
    )

    # Concise evidence.
    for name in [
        "ONLINE_PF_CONTROLLER_SUMMARY.csv",
        "ONLINE_PF_TIME_SERIES.csv",
        "LOAD_PHASES.csv",
        "LOAD_STATE_BUILD_AUDIT.csv",
        "ONLINE_PF_THEOREM_CERTIFICATES.json",
        "ONLINE_PF_LOAD_TRANSITION_AUDIT.json",
    ]:
        shutil.copy2(results / name, evidence / name)
    write_json(
        evidence / "ONLINE_PF_LOAD_TRANSITION_GATE_DECISION.json",
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": (
                "PASS_ONLINE_MOVING_AVERAGE_PF_LOAD_TRANSITION_ONE_SEED"
            ),
            "paper_result": False,
            "full_load_rzf_recomputed": True,
            "deterministic_load_transitions_completed": True,
            "online_predictive_1db_safe": (
                online["upper_bound_violation_seconds"] == 0
            ),
            "online_predictive_3db_safe": (
                robust3["upper_bound_violation_seconds"] == 0
            ),
            "two_drop_fail_safe_safe": (
                dropped["upper_bound_violation_seconds"] == 0
            ),
            "online_predictive_floor_violations": (
                online[
                    "eligible_floor_violation_user_interval_count"
                ]
            ),
            "corrected_saturation_theorem_certificate": (
                audit["decisive_results"][
                    "all_online_predictive_certificates_pass"
                ]
            ),
            "next_gate": cfg["next_gate"],
        },
    )
    (evidence / "README.md").write_text(
        "# Online moving-average PF and load transitions\n\n"
        "This one-seed local milestone recomputes local RZF and protected "
        "mode leakage for deterministic user arrivals/departures, rebuilds "
        "local proportional-fair action tables online from exponential "
        "moving-average throughput, and applies the corrected finite-pass "
        "robust safety certificate.\n\n"
        "It is not a paper result. Future geometry/load are known over the "
        "finite pass and uncertainty margins are not yet calibrated.\n",
        encoding="utf-8",
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  {path.as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("ONLINE MOVING-AVERAGE PF LOAD-TRANSITION MILESTONE: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
