#!/usr/bin/env python3
"""Rerun online constrained-PF controllers under corrected EESS criteria."""
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

from fr3_cbf.constrained_pf_safety import PriceAllocator, action_grid
from fr3_cbf.dual_criterion_controller import (
    common_scale_action,
    exact_hard_null_rates,
    exact_second_safety_ratio,
    interval_reduce,
    normalized_short_to_long_ratio,
    simulate_online_virtual_queue,
)
from fr3_cbf.online_pf_load_transition import (
    LoadState,
    build_online_moving_pf_cost_grid,
    build_rotating_load_schedule,
    evaluate_actions_across_states,
    exponential_average_alpha,
    finite_pass_dynamic_certificate,
    full_horizon_dynamic_envelope,
    recompute_load_state,
    sequential_average_trace,
    simulate_online_myopic_controller,
    simulate_online_predictive_controller,
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
    fields = list(rows[0])
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
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
    x = np.asarray(values, dtype=float)
    return {
        name: float(np.quantile(x, q))
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
    active = np.stack([state.active_user for state in states], axis=0)
    active_eligible = active & eligible[None, :]
    floor_violation = active_eligible & (total < floor - 1e-12)
    shortfall = np.zeros_like(total)
    valid_floor = active_eligible & (floor > 0)
    shortfall[valid_floor] = np.maximum(
        0.0,
        (floor[valid_floor] - total[valid_floor]) / floor[valid_floor],
    )

    moving_pf = np.log(average[:, eligible] + float(epsilon)).sum(axis=1)
    moving_geometric = (
        np.exp(np.log(average[:, eligible] + float(epsilon)).mean(axis=1))
        - float(epsilon)
    )
    active_p05 = []
    active_min = []
    for interval in range(len(total)):
        rate = total[interval, active_eligible[interval]]
        active_p05.append(float(np.quantile(rate, 0.05)))
        active_min.append(float(rate.min()))

    nominal_total_network = np.asarray(
        [state.nominal_total_rate.sum() for state in states], dtype=float
    )
    nominal_protected_network = np.asarray(
        [state.nominal_protected_rate.sum() for state in states], dtype=float
    )
    delivered_total_network = total.sum(axis=1)
    delivered_protected_network = protected.sum(axis=1)

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
            "active_user_interval_count": int(group_active.sum()),
            "mean_active_total_rate_bps_hz": float(values.mean()),
            "p05_active_total_rate_bps_hz": float(np.quantile(values, 0.05)),
            "minimum_active_total_rate_bps_hz": float(values.min()),
            "mean_active_protected_rate_bps_hz": float(
                protected_values.mean()
            ),
            "minimum_active_protected_rate_bps_hz": float(
                protected_values.min()
            ),
        }

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
        "maximum_normalized_floor_shortfall": float(shortfall.max()),
        "minimum_floor_ratio": float(
            np.min(total[active_eligible] / floor[active_eligible])
        ),
        "mean_moving_pf_utility": float(
            np.average(moving_pf, weights=lengths)
        ),
        "minimum_moving_pf_utility": float(moving_pf.min()),
        "final_moving_pf_utility": float(moving_pf[-1]),
        "mean_moving_geometric_rate_bps_hz": float(
            np.average(moving_geometric, weights=lengths)
        ),
        "final_moving_geometric_rate_bps_hz": float(moving_geometric[-1]),
        "mean_active_p05_rate_bps_hz": float(
            np.average(active_p05, weights=lengths)
        ),
        "minimum_active_p05_rate_bps_hz": float(np.min(active_p05)),
        "minimum_active_eligible_rate_bps_hz": float(np.min(active_min)),
        "mean_total_network_retention_secondary": float(
            np.average(
                delivered_total_network / nominal_total_network,
                weights=lengths,
            )
        ),
        "minimum_total_network_retention_secondary": float(
            np.min(delivered_total_network / nominal_total_network)
        ),
        "mean_protected_network_retention_secondary": float(
            np.average(
                delivered_protected_network / nominal_protected_network,
                weights=lengths,
            )
        ),
        "minimum_protected_network_retention_secondary": float(
            np.min(delivered_protected_network / nominal_protected_network)
        ),
        "user_final_moving_average_quantiles": quantiles(
            average[-1, eligible]
        ),
        "groups": group_metrics,
    }


def control_metrics(
    command: np.ndarray | None,
    applied: np.ndarray | None,
    build_seconds: np.ndarray | None = None,
) -> dict[str, object]:
    if command is None or applied is None:
        return {
            "command_total_variation_db": 0.0,
            "maximum_command_slew_db": 0.0,
            "mean_active_mode_count": 114.0,
            "maximum_active_mode_count": 114.0,
            "payload_bytes_per_update": 0.0,
            "maximum_finite_action_db": None,
        }
    difference = (
        np.diff(command, axis=0)
        if len(command) > 1
        else np.zeros((0, 57, 2))
    )
    result: dict[str, object] = {
        "command_total_variation_db": float(np.abs(difference).sum()),
        "maximum_command_slew_db": float(
            np.abs(difference).max() if difference.size else 0.0
        ),
        "mean_active_mode_count": float(
            np.mean(np.sum(applied > 0.0, axis=(1, 2)))
        ),
        "maximum_active_mode_count": float(
            np.max(np.sum(applied > 0.0, axis=(1, 2)))
        ),
        "payload_bytes_per_update": float(57 * 2 * 4),
        "maximum_finite_action_db": float(np.max(applied)),
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
    protected_noise: float,
    protected_weight: float,
    alpha: float,
    epsilon: float,
    maximum_contribution: np.ndarray,
    allowance: float,
) -> tuple[np.ndarray, dict[str, object], np.ndarray]:
    cost, audit = build_online_moving_pf_cost_grid(
        q_grid,
        state,
        np.zeros((57, 2), dtype=float),
        average,
        eligible,
        floor,
        serving,
        stream,
        protected_noise,
        protected_weight,
        alpha,
        epsilon,
    )
    allocator = PriceAllocator(q_grid, cost, allowance)
    action, ratio, feasible, price = allocator.solve(maximum_contribution)
    if not feasible or ratio > 1.0 + 1e-10:
        raise RuntimeError("static corrected-criterion action is infeasible")
    return action, {**audit, "ratio": ratio, "price": price}, cost


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/dual_criterion_controller_reevaluation_v1.json",
    )
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--dual-root", default=None)
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    data = (
        Path(args.data_root).expanduser().resolve()
        if args.data_root
        else (ROOT / cfg["data_root"]).resolve()
    )
    dual = (
        Path(args.dual_root).expanduser().resolve()
        if args.dual_root
        else (ROOT / cfg["dual_criterion_root"]).resolve()
    )
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    for path in [results, evidence]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    validation = json.loads(
        (data / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json").read_text(
            encoding="utf-8"
        )
    )
    if validation["status"] != (
        "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
    ):
        raise ValueError("full-topology data are not V4 validated")
    dual_gate = json.loads(
        (
            ROOT
            / "evidence/eess_dual_criterion_audit_v1/"
            "EESS_DUAL_CRITERION_GATE_DECISION.json"
        ).read_text(encoding="utf-8")
    )
    if dual_gate["status"] != (
        "PASS_REGULATORY_DIAGNOSIS_CONTROLLER_REEVALUATION_REQUIRED"
    ):
        raise ValueError("dual-criterion audit gate is not accepted")

    frequency_response = np.load(data / "frequency_response.npy", mmap_mode="r")
    serving = np.load(data / "serving_bs_index.npy")
    stream = np.load(data / "serving_stream_index.npy")
    power_f = np.load(data / "transmit_power_by_frequency_w.npy")
    noise_f = np.load(data / "noise_power_by_frequency_w.npy")
    weights = np.load(data / "frequency_weights.npy")
    steering1 = np.load(data / "protected_steering_pol1.npy")
    steering2 = np.load(data / "protected_steering_pol2.npy")
    time_s = np.load(data / "protected_time_s.npy")
    full_load_nominal = np.load(
        data / "nominal_total_weighted_rate_per_user.npy"
    )
    users = pd.read_csv(data / "USER_TOPOLOGY.csv")
    indoor = users["indoor"].astype(bool).to_numpy()

    timing = cfg["controller_timing"]
    update_interval = int(timing["update_interval_s"])
    delay = int(timing["message_delay_intervals"])
    slew = float(timing["slew_db_per_update"])
    interval_count = int(math.ceil(len(time_s) / update_interval))
    load = cfg["load_schedule"]
    schedule, phase_records = build_rotating_load_schedule(
        serving,
        stream,
        interval_count,
        load["phase_lengths_intervals"],
        load["active_streams_per_sector"],
    )

    state_cache: dict[bytes, LoadState] = {}
    states: list[LoadState] = []
    state_records = []
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
            state_records.append(
                {
                    "state_index": len(state_records),
                    "first_interval": interval,
                    "active_user_count": int(schedule[interval].sum()),
                    "build_seconds": time.perf_counter() - started,
                }
            )
        states.append(state_cache[key])
    state_build_seconds = time.perf_counter() - state_started
    print(f"LOAD STATES: PASS ({len(state_cache)} unique, {state_build_seconds:.3f} s)", flush=True)

    full_state = states[0]
    maximum_user_reproduction_error = float(
        np.max(np.abs(full_state.nominal_total_rate - full_load_nominal))
    )
    network_sum_relative_error = float(
        abs(full_state.nominal_total_rate.sum() - full_load_nominal.sum())
        / full_load_nominal.sum()
    )
    if maximum_user_reproduction_error > 2e-4:
        raise RuntimeError("full-load per-user RZF reproduction failed")
    if network_sum_relative_error > 5e-6:
        raise RuntimeError("full-load network-sum RZF reproduction failed")

    fairness = cfg["fairness_policy"]
    eligible = full_load_nominal >= float(
        fairness["serviceability_threshold_bps_hz"]
    )
    floors = np.zeros((interval_count, 228), dtype=float)
    for interval, state in enumerate(states):
        active_eligible = state.active_user & eligible
        floors[interval, active_eligible] = np.maximum(
            float(fairness["absolute_total_band_floor_bps_hz"]),
            float(fairness["relative_current_load_floor_fraction"])
            * state.nominal_total_rate[active_eligible],
        )

    moving = cfg["moving_average"]
    alpha = exponential_average_alpha(
        update_interval,
        float(moving["time_constant_s"]),
    )
    epsilon = float(moving["epsilon_bps_hz"])
    initial_average = full_load_nominal.copy()
    grid_cfg = cfg["action_grid"]
    q_grid = action_grid(
        int(grid_cfg["minimum_db"]),
        int(grid_cfg["maximum_db"]),
        int(grid_cfg["step_db"]),
    )
    maximum_action = float(grid_cfg["maximum_db"])
    protected_noise = float(noise_f[4])
    protected_weight = float(weights[4])

    criterion_data: dict[str, dict[str, object]] = {}
    for case_name, case_cfg in cfg["criteria"].items():
        kappa = np.load(dual / case_cfg["kappa_file"])
        allowance_second = np.load(dual / case_cfg["allowance_file"])
        kappa_interval, interval_lengths = interval_reduce(
            kappa, update_interval, "max"
        )
        allowance_interval, allowance_lengths = interval_reduce(
            allowance_second, update_interval, "min"
        )
        if not np.array_equal(interval_lengths, allowance_lengths):
            raise RuntimeError("criterion interval lengths do not align")
        contribution = np.asarray(
            [
                kappa_interval[index, :, None]
                * states[index].mode_leakage_w
                for index in range(interval_count)
            ],
            dtype=float,
        )
        application_env, command_env, _ = full_horizon_dynamic_envelope(
            contribution,
            delay,
            slew,
        )
        criterion_data[case_name] = {
            "config": case_cfg,
            "kappa": kappa,
            "allowance_second": allowance_second,
            "interval_lengths": interval_lengths,
            "allowance_interval": allowance_interval,
            "contribution": contribution,
            "application_envelope": application_env,
            "command_envelope": command_env,
        }

    summary_rows: list[dict[str, object]] = []
    time_rows: list[dict[str, object]] = []
    detailed: dict[str, dict[str, object]] = {}
    primary_actions: dict[str, np.ndarray] = {}
    predictive_actions_by_case: dict[str, np.ndarray] = {}

    def add_result(
        case_name: str,
        controller: str,
        command: np.ndarray | None,
        applied: np.ndarray | None,
        delivered_total: np.ndarray,
        delivered_protected: np.ndarray,
        average_trace: np.ndarray,
        second_ratio: np.ndarray,
        runtime_seconds: float,
        command_feasible: bool,
        fail_safe_count: int,
        certificate: dict[str, object] | None,
        build_seconds: np.ndarray | None = None,
        queue_maximum: float | None = None,
        exact_hard_null: bool = False,
    ) -> None:
        case = criterion_data[case_name]
        metrics = moving_pf_metrics(
            delivered_total,
            delivered_protected,
            average_trace,
            states,
            floors,
            eligible,
            indoor,
            case["interval_lengths"],
            epsilon,
        )
        controls = control_metrics(command, applied, build_seconds)
        row = {
            "case": case_name,
            "p452_time_percentage": case["config"]["p452_time_percentage"],
            "threshold_dbw_per_10mhz": case["config"][
                "threshold_dbw_per_10mhz"
            ],
            "pattern": case["config"]["pattern"],
            "controller": controller,
            "command_feasible_all_intervals": command_feasible,
            "violation_seconds": int(np.sum(second_ratio > 1.0 + 1e-10)),
            "maximum_threshold_excess_db": float(
                10.0 * np.log10(max(float(second_ratio.max()), 1e-300))
            ),
            "minimum_safety_margin_db": float(
                -10.0 * np.log10(max(float(second_ratio.max()), 1e-300))
            ),
            "fail_safe_command_count": fail_safe_count,
            "certificate_status": (
                certificate["status"] if certificate is not None else "NOT_APPLICABLE"
            ),
            "runtime_seconds": runtime_seconds,
            "queue_maximum": queue_maximum,
            "exact_hard_null": exact_hard_null,
            **{
                key: value
                for key, value in metrics.items()
                if key != "groups" and not isinstance(value, dict)
            },
            **controls,
        }
        summary_rows.append(row)
        detailed[f"{case_name}:{controller}"] = {
            "summary": row,
            "groups": metrics["groups"],
            "certificate": certificate,
        }
        if case_name == "long_multiple" and command is not None:
            primary_actions[f"{controller}_command_db"] = command
            primary_actions[f"{controller}_applied_db"] = applied

        for second in range(587):
            if len(time_rows) <= second:
                time_rows.append({"time_s": float(time_s[second])})
            time_rows[second][f"{case_name}_{controller}_ratio"] = float(
                second_ratio[second]
            )

    for case_name, case in criterion_data.items():
        print(f"CASE {case_name}: START", flush=True)
        contribution = case["contribution"]
        allowance_interval = case["allowance_interval"]
        kappa = case["kappa"]
        allowance_second = case["allowance_second"]
        application_env = case["application_envelope"]
        command_env = case["command_envelope"]

        # Predictive online constrained PF.
        print(f"CASE {case_name}: predictive start", flush=True)
        started = time.perf_counter()
        predictive = simulate_online_predictive_controller(
            q_grid,
            states,
            contribution,
            allowance_interval,
            application_env,
            command_env,
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
            fail_safe_drop_command_indices=(),
        )
        predictive_runtime = time.perf_counter() - started
        print(f"CASE {case_name}: predictive done ({predictive_runtime:.3f} s)", flush=True)
        predictive_second = exact_second_safety_ratio(
            kappa,
            states,
            predictive.applied_db,
            update_interval,
            allowance_second,
        )
        predictive_certificate = finite_pass_dynamic_certificate(
            predictive.command_db,
            predictive.applied_db,
            predictive.command_feasible,
            application_env,
            command_env,
            predictive.upper_interval_ratio,
            allowance_interval,
            slew,
            maximum_action,
        )
        predictive_actions_by_case[case_name] = predictive.applied_db.copy()
        add_result(
            case_name,
            "online_predictive_constrained_pf",
            predictive.command_db,
            predictive.applied_db,
            predictive.delivered_total_rate,
            predictive.delivered_protected_rate,
            predictive.moving_average_rate,
            predictive_second,
            predictive_runtime,
            bool(np.all(predictive.command_feasible)),
            int(predictive.fail_safe_used.sum()),
            predictive_certificate,
            predictive.local_table_build_seconds,
        )

        # Delayed myopic online constrained PF.
        print(f"CASE {case_name}: myopic start", flush=True)
        started = time.perf_counter()
        myopic = simulate_online_myopic_controller(
            q_grid,
            states,
            contribution,
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
        print(f"CASE {case_name}: myopic done ({myopic_runtime:.3f} s)", flush=True)
        myopic_second = exact_second_safety_ratio(
            kappa,
            states,
            myopic.applied_db,
            update_interval,
            allowance_second,
        )
        add_result(
            case_name,
            "online_delayed_myopic_constrained_pf",
            myopic.command_db,
            myopic.applied_db,
            myopic.delivered_total_rate,
            myopic.delivered_protected_rate,
            myopic.moving_average_rate,
            myopic_second,
            myopic_runtime,
            bool(np.all(myopic.command_feasible)),
            0,
            None,
            myopic.local_table_build_seconds,
        )

        # Static safe constrained-PF reference and its cost table.
        print(f"CASE {case_name}: static start", flush=True)
        static_q, static_audit, frozen_cost = static_action(
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
            np.max(contribution, axis=0),
            float(allowance_interval[0]),
        )
        static_actions = np.repeat(
            static_q[None, :, :], interval_count, axis=0
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
        static_second = exact_second_safety_ratio(
            kappa,
            states,
            static_actions,
            update_interval,
            allowance_second,
        )
        add_result(
            case_name,
            "static_constrained_pf",
            static_actions,
            static_actions,
            static_total,
            static_protected,
            static_average,
            static_second,
            0.0,
            True,
            0,
            None,
        )
        detailed[f"{case_name}:static_constrained_pf"]["static_audit"] = (
            static_audit
        )

        print(f"CASE {case_name}: static done", flush=True)
        # Online PF virtual queue with gain 1; no hard guarantee.
        print(f"CASE {case_name}: virtual queue start", flush=True)
        started = time.perf_counter()
        queue_run = simulate_online_virtual_queue(
            q_grid,
            states,
            contribution,
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
            price_gain=1.0,
        )
        queue_runtime = time.perf_counter() - started
        print(f"CASE {case_name}: virtual queue done ({queue_runtime:.3f} s)", flush=True)
        queue_second = exact_second_safety_ratio(
            kappa,
            states,
            queue_run.applied_db,
            update_interval,
            allowance_second,
        )
        add_result(
            case_name,
            "virtual_queue_gain_1_online_pf",
            queue_run.command_db,
            queue_run.applied_db,
            queue_run.delivered_total_rate,
            queue_run.delivered_protected_rate,
            queue_run.moving_average_rate,
            queue_second,
            queue_runtime,
            bool(np.all(queue_run.command_feasible)),
            0,
            None,
            queue_run.local_table_build_seconds,
            float(queue_run.queue.max()),
        )

        # Instantaneous common-scale upper reference; no delay or slew.
        common_actions = common_scale_action(contribution, allowance_interval)
        common_total, common_protected, common_average = (
            evaluate_actions_across_states(
                common_actions,
                states,
                serving,
                stream,
                protected_noise,
                protected_weight,
                initial_average,
                alpha,
            )
        )
        common_second = exact_second_safety_ratio(
            kappa,
            states,
            common_actions,
            update_interval,
            allowance_second,
        )
        add_result(
            case_name,
            "instantaneous_common_scale_oracle",
            common_actions,
            common_actions,
            common_total,
            common_protected,
            common_average,
            common_second,
            0.0,
            True,
            0,
            None,
        )

        # Exact hard null: scale both incumbent-parallel modes to zero.
        hard_total = []
        hard_protected = []
        for state in states:
            total_rate, protected_rate = exact_hard_null_rates(
                state,
                serving,
                stream,
                protected_noise,
                protected_weight,
            )
            hard_total.append(total_rate)
            hard_protected.append(protected_rate)
        hard_total_array = np.asarray(hard_total)
        hard_protected_array = np.asarray(hard_protected)
        hard_average = sequential_average_trace(
            hard_total_array, initial_average, alpha
        )
        hard_ratio = np.zeros(587, dtype=float)
        add_result(
            case_name,
            "exact_hard_null_reference",
            None,
            None,
            hard_total_array,
            hard_protected_array,
            hard_average,
            hard_ratio,
            0.0,
            True,
            0,
            None,
            exact_hard_null=True,
        )

        # Q=70 terminal check on the exact second-resolution criterion.
        q70 = np.full((interval_count, 57, 2), maximum_action, dtype=float)
        q70_ratio = exact_second_safety_ratio(
            kappa,
            states,
            q70,
            update_interval,
            allowance_second,
        )
        detailed[f"{case_name}:terminal_q70"] = {
            "maximum_ratio": float(q70_ratio.max()),
            "minimum_margin_db": float(-10.0 * np.log10(q70_ratio.max())),
            "safe": bool(np.all(q70_ratio <= 1.0 + 1e-10)),
        }

        # The two-command-drop fail-safe is rerun for the primary joint-design
        # long-term multiple-entry case.
        if case_name == cfg["additional_primary_case"]["case"]:
            print(f"CASE {case_name}: two-drop predictive start", flush=True)
            started = time.perf_counter()
            dropped = simulate_online_predictive_controller(
                q_grid,
                states,
                contribution,
                allowance_interval,
                application_env,
                command_env,
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
                fail_safe_drop_command_indices=tuple(
                    int(value)
                    for value in timing[
                        "message_drop_command_indices_primary"
                    ]
                ),
            )
            dropped_runtime = time.perf_counter() - started
            print(f"CASE {case_name}: two-drop predictive done ({dropped_runtime:.3f} s)", flush=True)
            dropped_second = exact_second_safety_ratio(
                kappa,
                states,
                dropped.applied_db,
                update_interval,
                allowance_second,
            )
            dropped_certificate = finite_pass_dynamic_certificate(
                dropped.command_db,
                dropped.applied_db,
                dropped.command_feasible,
                application_env,
                command_env,
                dropped.upper_interval_ratio,
                allowance_interval,
                slew,
                maximum_action,
            )
            add_result(
                case_name,
                "online_predictive_constrained_pf_two_drops",
                dropped.command_db,
                dropped.applied_db,
                dropped.delivered_total_rate,
                dropped.delivered_protected_rate,
                dropped.moving_average_rate,
                dropped_second,
                dropped_runtime,
                bool(np.all(dropped.command_feasible)),
                int(dropped.fail_safe_used.sum()),
                dropped_certificate,
                dropped.local_table_build_seconds,
            )

    # Long-term normalized constraints dominate the paired short-term
    # constraints for every second and sector in this deterministic model.
    dominance = {}
    for pattern in ["multiple", "single"]:
        short = criterion_data[f"short_{pattern}"]
        long = criterion_data[f"long_{pattern}"]
        ratio = normalized_short_to_long_ratio(
            short["kappa"],
            short["allowance_second"],
            long["kappa"],
            long["allowance_second"],
        )
        dominance[pattern] = {
            "maximum_short_to_long_normalized_ratio": float(ratio.max()),
            "minimum_short_to_long_normalized_ratio": float(ratio.min()),
            "minimum_long_dominance_margin_db": float(
                -10.0 * np.log10(ratio.max())
            ),
            "long_constraint_elementwise_dominates": bool(
                np.all(ratio < 1.0)
            ),
        }

        action = predictive_actions_by_case[f"long_{pattern}"]
        short_ratio = exact_second_safety_ratio(
            short["kappa"],
            states,
            action,
            update_interval,
            short["allowance_second"],
        )
        dominance[pattern][
            "long_predictive_actions_short_term_violation_seconds"
        ] = int(np.sum(short_ratio > 1.0 + 1e-10))
        dominance[pattern][
            "long_predictive_actions_short_term_maximum_ratio"
        ] = float(short_ratio.max())

    write_csv(results / "DUAL_CRITERION_CONTROLLER_SUMMARY.csv", summary_rows)
    write_csv(results / "DUAL_CRITERION_SECOND_TIME_SERIES.csv", time_rows)
    write_csv(results / "LOAD_PHASES.csv", phase_records)
    write_csv(results / "LOAD_STATE_BUILD_AUDIT.csv", state_records)
    np.savez_compressed(
        results / "PRIMARY_LONG_MULTIPLE_ACTIONS.npz", **primary_actions
    )
    write_json(results / "DUAL_CRITERION_DETAILED_RESULTS.json", detailed)
    write_json(results / "DUAL_CRITERION_DOMINANCE_AUDIT.json", dominance)

    rows_by_key = {
        f"{row['case']}:{row['controller']}": row for row in summary_rows
    }
    decisive = {}
    for case_name in cfg["criteria"]:
        predictive = rows_by_key[
            f"{case_name}:online_predictive_constrained_pf"
        ]
        myopic = rows_by_key[
            f"{case_name}:online_delayed_myopic_constrained_pf"
        ]
        static = rows_by_key[f"{case_name}:static_constrained_pf"]
        queue = rows_by_key[
            f"{case_name}:virtual_queue_gain_1_online_pf"
        ]
        hard = rows_by_key[f"{case_name}:exact_hard_null_reference"]
        decisive[case_name] = {
            "myopic_violation_seconds": myopic["violation_seconds"],
            "predictive_violation_seconds": predictive["violation_seconds"],
            "static_violation_seconds": static["violation_seconds"],
            "virtual_queue_violation_seconds": queue["violation_seconds"],
            "predictive_certificate_status": predictive[
                "certificate_status"
            ],
            "predictive_mean_moving_pf_utility": predictive[
                "mean_moving_pf_utility"
            ],
            "static_mean_moving_pf_utility": static[
                "mean_moving_pf_utility"
            ],
            "hard_null_mean_moving_pf_utility": hard[
                "mean_moving_pf_utility"
            ],
            "predictive_minus_static_pf_utility": (
                predictive["mean_moving_pf_utility"]
                - static["mean_moving_pf_utility"]
            ),
            "predictive_mean_protected_retention": predictive[
                "mean_protected_network_retention_secondary"
            ],
            "static_mean_protected_retention": static[
                "mean_protected_network_retention_secondary"
            ],
            "predictive_minimum_floor_ratio": predictive[
                "minimum_floor_ratio"
            ],
            "predictive_floor_violation_user_intervals": predictive[
                "eligible_floor_violation_user_interval_count"
            ],
            "terminal_q70": detailed[f"{case_name}:terminal_q70"],
        }

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_CORRECTED_DUAL_CRITERION_CONTROLLER_REEVALUATION_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"],
        "data_validation_status": validation["status"],
        "dual_criterion_gate_status": dual_gate["status"],
        "full_load_rzf_reproduction": {
            "maximum_per_user_error_bps_hz": maximum_user_reproduction_error,
            "network_sum_relative_error": network_sum_relative_error,
        },
        "action_grid": cfg["action_grid"],
        "controller_timing": cfg["controller_timing"],
        "fairness_policy": cfg["fairness_policy"],
        "load_schedule": {
            "interval_count": interval_count,
            "unique_recomputed_load_states": len(state_cache),
            "state_build_total_seconds": state_build_seconds,
            "phases": phase_records,
        },
        "decisive_results": decisive,
        "dominance": dominance,
        "joint_criterion_interpretation": (
            "Within this percentile-matched deterministic per-geometry model, "
            "the long-term normalized constraint elementwise dominates the "
            "paired short-term constraint by at least 13.897 dB. The separate "
            "short-term runs are retained for transparency; a long-term-safe "
            "action is jointly safe for the paired short-term test. This is "
            "not a claim that the full regulatory time functional has been "
            "statistically demonstrated."
        ),
        "limitations": [
            "one channel/topology seed and one protected pass",
            "percentile-matched criteria are enforced deterministically at every geometry sample as an engineering compatibility test",
            "no measured earth-station pattern; SA.509 single-entry is a +3 dB sensitivity",
            "0-70 dB ideal-digital action grid and exact hard-null reference are not hardware null-depth claims",
            "no held-out P.452, terrain, ephemeris, array, or CSI uncertainty calibration",
            "deterministic rotating load schedule and backlogged-unscheduled inactive-user semantics",
            "moving-PF local tables hold other-sector actions fixed at the current applied action",
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(results / "DUAL_CRITERION_CONTROLLER_AUDIT.json", audit)

    # Concise evidence; large action arrays remain in ignored results only.
    for name in [
        "DUAL_CRITERION_CONTROLLER_SUMMARY.csv",
        "DUAL_CRITERION_SECOND_TIME_SERIES.csv",
        "LOAD_PHASES.csv",
        "LOAD_STATE_BUILD_AUDIT.csv",
        "DUAL_CRITERION_DETAILED_RESULTS.json",
        "DUAL_CRITERION_DOMINANCE_AUDIT.json",
        "DUAL_CRITERION_CONTROLLER_AUDIT.json",
    ]:
        shutil.copy2(results / name, evidence / name)
    write_json(
        evidence / "DUAL_CRITERION_CONTROLLER_GATE_DECISION.json",
        {
            "created_utc": audit["created_utc"],
            "status": "PASS_CORRECTED_DUAL_CRITERION_CONTROLLER_ONE_SEED",
            "paper_result": False,
            "regulatory_compliance_result": False,
            "all_predictive_cases_safe": bool(
                all(
                    value["predictive_violation_seconds"] == 0
                    for value in decisive.values()
                )
            ),
            "all_predictive_certificates_pass": bool(
                all(
                    value["predictive_certificate_status"]
                    == "PASS_CORRECTED_FINITE_PASS_DYNAMIC_CERTIFICATE"
                    for value in decisive.values()
                )
            ),
            "all_predictive_floor_violations_zero": bool(
                all(
                    value["predictive_floor_violation_user_intervals"] == 0
                    for value in decisive.values()
                )
            ),
            "q70_terminal_safe_all_cases": bool(
                all(value["terminal_q70"]["safe"] for value in decisive.values())
            ),
            "long_term_dominates_short_term": bool(
                all(
                    value["long_constraint_elementwise_dominates"]
                    for value in dominance.values()
                )
            ),
            "new_nibi_job_required": False,
            "next_gate": cfg["next_gate"],
        },
    )
    (evidence / "README.md").write_text(
        "# Corrected EESS dual-criterion controller reevaluation\n\n"
        "This one-seed local stage reruns online constrained-PF static, delayed "
        "myopic, predictive, virtual-queue, common-scale, and exact hard-null "
        "references for percentile-matched EESS long- and short-term criteria. "
        "It uses a provisional 0--70 dB ideal-digital grid and SA.509 pattern "
        "sensitivity. It is not regulatory-compliance evidence or a paper "
        "result.\n",
        encoding="utf-8",
    )
    source_hashes = {
        "full_topology_validation": sha256_file(
            data / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json"
        ),
        "frequency_response": sha256_file(data / "frequency_response.npy"),
        "dual_criterion_audit": sha256_file(
            ROOT
            / "evidence/eess_dual_criterion_audit_v1/"
            "EESS_DUAL_CRITERION_AUDIT.json"
        ),
        **{
            f"dual_array:{name}": sha256_file(dual / name)
            for name in sorted(
                {
                    case["kappa_file"]
                    for case in cfg["criteria"].values()
                }
                | {
                    case["allowance_file"]
                    for case in cfg["criteria"].values()
                }
            )
        },
    }
    write_json(evidence / "SOURCE_HASHES.json", source_hashes)

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(ROOT).as_posix()}"
            )
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("CORRECTED DUAL-CRITERION CONTROLLER REEVALUATION: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
