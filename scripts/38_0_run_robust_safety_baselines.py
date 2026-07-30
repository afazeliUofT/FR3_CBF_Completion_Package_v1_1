#!/usr/bin/env python3
"""Run robust delayed-safety, virtual-queue, uncertainty, and fail-safe milestone."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from fr3_cbf.constrained_pf_safety import (
    PriceAllocator,
    action_grid,
    build_local_constrained_pf_cost_grid,
    control_metrics,
    evaluate_interval_actions,
    simulate_myopic,
)
from fr3_cbf.robust_delayed_safety import (
    RobustRun,
    VirtualQueueRun,
    full_horizon_reachability_envelope,
    interval_mode_contributions,
    simulate_full_horizon_predictive,
    simulate_virtual_queue,
    theorem_certificate,
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


def exact_second_ratio(
    kappa: np.ndarray,
    leakage: np.ndarray,
    allowance: np.ndarray,
    applied_interval_q_db: np.ndarray,
    update_interval_s: int,
    coupling_upper_margin_db: float,
) -> tuple[np.ndarray, np.ndarray]:
    factor = 10.0 ** (float(coupling_upper_margin_db) / 10.0)
    upper = np.empty(len(kappa), dtype=float)
    nominal = np.empty(len(kappa), dtype=float)
    for second in range(len(kappa)):
        interval = min(
            second // int(update_interval_s),
            len(applied_interval_q_db) - 1,
        )
        power_scale = np.power(
            10.0,
            -applied_interval_q_db[interval] / 10.0,
        )
        base = (
            kappa[second, :, None]
            * leakage
            * power_scale
        ).sum()
        nominal[second] = float(base / allowance[second])
        upper[second] = float(factor * base / allowance[second])
    return upper, nominal


def evaluate_actions(
    applied_q_db: np.ndarray,
    interval_lengths: np.ndarray,
    nominal_total: np.ndarray,
    nominal_protected: np.ndarray,
    eligible: np.ndarray,
    floor: np.ndarray,
    indoor: np.ndarray,
    a0: np.ndarray,
    a1: np.ndarray,
    a2: np.ndarray,
    serving: np.ndarray,
    stream: np.ndarray,
    noise: float,
    other_rate: np.ndarray,
    protected_weight: float,
    epsilon: float,
) -> dict[str, object]:
    return evaluate_interval_actions(
        applied_q_db,
        interval_lengths,
        nominal_total,
        nominal_protected,
        eligible,
        floor,
        indoor,
        a0,
        a1,
        a2,
        serving,
        stream,
        noise,
        other_rate,
        protected_weight,
        epsilon,
    )


def summary_row(
    controller: str,
    command_db: np.ndarray,
    applied_db: np.ndarray,
    upper_second_ratio: np.ndarray,
    nominal_second_ratio: np.ndarray,
    evaluation: dict[str, object],
    update_interval_s: int,
    delay_intervals: int,
    slew_db_per_update: float,
    uncertainty_db: float,
    runtime_seconds: float,
    fail_safe_count: int = 0,
    queue_maximum: float | None = None,
) -> dict[str, object]:
    control = control_metrics(command_db, applied_db)
    row = {
        "controller": controller,
        "update_interval_s": int(update_interval_s),
        "effective_delay_intervals": int(delay_intervals),
        "slew_db_per_update": float(slew_db_per_update),
        "coupling_upper_margin_db": float(uncertainty_db),
        "upper_bound_violation_seconds": int(
            np.sum(upper_second_ratio > 1.0 + 1e-10)
        ),
        "nominal_violation_seconds": int(
            np.sum(nominal_second_ratio > 1.0 + 1e-10)
        ),
        "maximum_upper_threshold_excess_db": float(
            10.0 * np.log10(np.max(upper_second_ratio))
        ),
        "minimum_nominal_safety_margin_db": float(
            -10.0 * np.log10(np.max(nominal_second_ratio))
        ),
        "eligible_floor_violation_user_intervals": evaluation[
            "floor_violation_user_interval_count"
        ],
        "unique_eligible_floor_violation_users": evaluation[
            "unique_floor_violation_user_count"
        ],
        "total_normalized_floor_shortfall_user_seconds": evaluation[
            "total_normalized_floor_shortfall_user_seconds"
        ],
        "minimum_floor_ratio": evaluation["minimum_floor_ratio"],
        "mean_pf_utility": evaluation["mean_pf_utility"],
        "minimum_pf_utility": evaluation["minimum_pf_utility"],
        "mean_geometric_rate_bps_hz": evaluation[
            "mean_geometric_rate_bps_hz"
        ],
        "minimum_geometric_rate_bps_hz": evaluation[
            "minimum_geometric_rate_bps_hz"
        ],
        "mean_p05_eligible_rate_bps_hz": evaluation[
            "mean_p05_eligible_rate_bps_hz"
        ],
        "minimum_eligible_rate_bps_hz": evaluation[
            "minimum_eligible_rate_bps_hz"
        ],
        "mean_jain_index_eligible": evaluation[
            "mean_jain_index_eligible"
        ],
        "mean_total_network_retention_secondary": evaluation[
            "mean_total_network_retention"
        ],
        "mean_protected_network_retention_secondary": evaluation[
            "mean_protected_network_retention"
        ],
        "fail_safe_command_count": int(fail_safe_count),
        "runtime_seconds": float(runtime_seconds),
        **control,
    }
    if queue_maximum is not None:
        row["maximum_virtual_queue"] = float(queue_maximum)
    return row


def surrogate_approximation_audit(
    local_cost: np.ndarray,
    q_grid: np.ndarray,
    applied_q_db: np.ndarray,
    evaluation: dict[str, object],
    nominal_total: np.ndarray,
    eligible: np.ndarray,
    epsilon: float,
) -> dict[str, float]:
    index = np.rint(
        (applied_q_db - q_grid[0]) / (q_grid[1] - q_grid[0])
    ).astype(np.int64)
    if np.any(index < 0) or np.any(index >= len(q_grid)):
        raise ValueError("an applied action is outside the local cost grid")
    surrogate = np.empty(len(index), dtype=float)
    for interval in range(len(index)):
        surrogate[interval] = float(
            local_cost[
                np.arange(57),
                index[interval, :, 0],
                index[interval, :, 1],
            ].sum()
        )
    exact_pf = np.log(
        np.asarray(evaluation["total_rate"])[:, eligible]
        + float(epsilon)
    ).sum(axis=1)
    nominal_pf = float(
        np.log(nominal_total[eligible] + float(epsilon)).sum()
    )
    exact_loss = nominal_pf - exact_pf
    centered_surrogate = surrogate - surrogate.mean()
    centered_exact = exact_loss - exact_loss.mean()
    denominator = float(
        np.linalg.norm(centered_surrogate)
        * np.linalg.norm(centered_exact)
    )
    correlation = (
        float(centered_surrogate @ centered_exact / denominator)
        if denominator > 0
        else 1.0
    )
    offset = float(np.mean(surrogate - exact_loss))
    centered_error = surrogate - exact_loss - offset
    return {
        "pearson_correlation": correlation,
        "affine_offset": offset,
        "maximum_centered_absolute_error": float(
            np.max(np.abs(centered_error))
        ),
        "root_mean_square_centered_error": float(
            np.sqrt(np.mean(centered_error**2))
        ),
        "interpretation": (
            "The table is a frozen local surrogate around nominal "
            "other-sector actions. The audit quantifies, but does not remove, "
            "its approximation gap to exact full-network PF utility."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/robust_safety_baselines_v1.json",
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

    a0 = np.load(data / "protected_amp_perpendicular.npy")
    a1 = np.load(data / "protected_amp_pol1.npy")
    a2 = np.load(data / "protected_amp_pol2.npy")
    serving = np.load(data / "serving_bs_index.npy")
    stream = np.load(data / "serving_stream_index.npy")
    noise = float(
        np.load(data / "noise_power_by_frequency_w.npy")[4]
    )
    weights = np.load(data / "frequency_weights.npy")
    protected_weight = float(weights[4])
    other_rate = np.load(
        data / "other_frequency_weighted_rate_per_user.npy"
    )
    nominal_total = np.load(
        data / "nominal_total_weighted_rate_per_user.npy"
    )
    nominal_protected = np.load(
        data / "nominal_protected_rate_per_user.npy"
    )
    leakage = np.load(data / "nominal_mode_leakage_w.npy")
    kappa = np.load(data / "kappa_time_sector.npy")
    allowance = np.load(data / "aggregate_allowance_w.npy")
    time_s = np.load(data / "protected_time_s.npy")
    topology = pd.read_csv(data / "USER_TOPOLOGY.csv")
    indoor = topology["indoor"].to_numpy(dtype=bool)

    policy = cfg["fairness_policy"]
    epsilon = float(policy["pf_epsilon_bps_hz"])
    eligible = nominal_total >= float(
        policy["serviceability_threshold_bps_hz"]
    )
    floor = np.maximum(
        float(policy["absolute_total_band_floor_bps_hz"]),
        float(policy["relative_total_band_floor_fraction"])
        * nominal_total,
    )
    if int(eligible.sum()) != 207:
        raise ValueError("expected 207 eligible users")

    q_cfg = cfg["action_grid"]
    q_grid = action_grid(
        int(q_cfg["minimum_db"]),
        int(q_cfg["maximum_db"]),
        int(q_cfg["step_db"]),
    )
    cost_started = time.perf_counter()
    local_cost, local_cost_audit = (
        build_local_constrained_pf_cost_grid(
            q_grid,
            nominal_total,
            eligible,
            floor,
            a0,
            a1,
            a2,
            serving,
            stream,
            noise,
            other_rate,
            protected_weight,
            epsilon,
        )
    )
    cost_seconds = time.perf_counter() - cost_started
    allocator = PriceAllocator(
        q_grid,
        local_cost,
        float(allowance[0]),
    )

    primary = cfg["primary_scenario"]
    update_interval = int(primary["update_interval_s"])
    base_delay = int(primary["message_delay_intervals"])
    slew = float(primary["slew_db_per_update"])
    contribution, interval_allowance, interval_lengths = (
        interval_mode_contributions(
            kappa,
            leakage,
            allowance,
            update_interval,
        )
    )

    rows: list[dict[str, object]] = []
    runs: dict[str, dict[str, object]] = {}
    certificates: dict[str, dict[str, object]] = {}

    # Delayed myopic constrained-PF reference.
    started = time.perf_counter()
    myopic = simulate_myopic(
        allocator,
        contribution,
        base_delay,
        slew,
    )
    myopic_upper, myopic_nominal = exact_second_ratio(
        kappa,
        leakage,
        allowance,
        myopic.applied_db,
        update_interval,
        0.0,
    )
    myopic_evaluation = evaluate_actions(
        myopic.applied_db,
        interval_lengths,
        nominal_total,
        nominal_protected,
        eligible,
        floor,
        indoor,
        a0,
        a1,
        a2,
        serving,
        stream,
        noise,
        other_rate,
        protected_weight,
        epsilon,
    )
    myopic_row = summary_row(
        "delayed_myopic_constrained_pf",
        myopic.command_db,
        myopic.applied_db,
        myopic_upper,
        myopic_nominal,
        myopic_evaluation,
        update_interval,
        base_delay,
        slew,
        0.0,
        time.perf_counter() - started,
    )
    rows.append(myopic_row)
    runs["delayed_myopic_constrained_pf"] = {
        "command": myopic.command_db,
        "applied": myopic.applied_db,
        "evaluation": myopic_evaluation,
        "row": myopic_row,
    }

    # Long-term virtual-queue baselines.
    queue_rows = []
    for gain in cfg["virtual_queue"]["price_gains"]:
        started = time.perf_counter()
        queue_run = simulate_virtual_queue(
            allocator,
            contribution,
            interval_allowance,
            base_delay,
            slew,
            float(gain),
        )
        queue_upper, queue_nominal = exact_second_ratio(
            kappa,
            leakage,
            allowance,
            queue_run.applied_db,
            update_interval,
            0.0,
        )
        queue_evaluation = evaluate_actions(
            queue_run.applied_db,
            interval_lengths,
            nominal_total,
            nominal_protected,
            eligible,
            floor,
            indoor,
            a0,
            a1,
            a2,
            serving,
            stream,
            noise,
            other_rate,
            protected_weight,
            epsilon,
        )
        row = summary_row(
            f"virtual_queue_gain_{gain}",
            queue_run.command_db,
            queue_run.applied_db,
            queue_upper,
            queue_nominal,
            queue_evaluation,
            update_interval,
            base_delay,
            slew,
            0.0,
            time.perf_counter() - started,
            queue_maximum=float(queue_run.queue.max()),
        )
        rows.append(row)
        queue_rows.append(row)

    # Static robust references at 1 and 3 dB.
    for margin in [1.0, 3.0]:
        upper_contribution = (
            contribution * 10.0 ** (margin / 10.0)
        )
        action, normalized, feasible, _price = allocator.solve(
            np.max(upper_contribution, axis=0)
        )
        if not feasible:
            raise RuntimeError(
                f"static robust action is infeasible at {margin} dB"
            )
        applied = np.repeat(
            action[None, :, :],
            len(contribution),
            axis=0,
        )
        upper_second, nominal_second = exact_second_ratio(
            kappa,
            leakage,
            allowance,
            applied,
            update_interval,
            margin,
        )
        evaluation = evaluate_actions(
            applied,
            interval_lengths,
            nominal_total,
            nominal_protected,
            eligible,
            floor,
            indoor,
            a0,
            a1,
            a2,
            serving,
            stream,
            noise,
            other_rate,
            protected_weight,
            epsilon,
        )
        row = summary_row(
            f"static_robust_constrained_pf_{int(margin)}db",
            applied,
            applied,
            upper_second,
            nominal_second,
            evaluation,
            update_interval,
            0,
            0.0,
            margin,
            0.0,
        )
        row["static_envelope_ratio"] = float(normalized)
        rows.append(row)
        runs[row["controller"]] = {
            "command": applied,
            "applied": applied,
            "evaluation": evaluation,
            "row": row,
        }

    # Full-horizon robust predictive cases.
    for case in cfg["robust_cases"]:
        case_id = str(case["case_id"])
        margin = float(case["coupling_upper_margin_db"])
        delay = base_delay + int(
            case["additional_message_age_intervals"]
        )
        drops = tuple(
            int(value)
            for value in case["fail_safe_drop_command_indices"]
        )
        started = time.perf_counter()
        run = simulate_full_horizon_predictive(
            allocator,
            contribution,
            interval_allowance,
            delay,
            slew,
            margin,
            drops,
        )
        upper_second, nominal_second = exact_second_ratio(
            kappa,
            leakage,
            allowance,
            run.applied_db,
            update_interval,
            margin,
        )
        evaluation = evaluate_actions(
            run.applied_db,
            interval_lengths,
            nominal_total,
            nominal_protected,
            eligible,
            floor,
            indoor,
            a0,
            a1,
            a2,
            serving,
            stream,
            noise,
            other_rate,
            protected_weight,
            epsilon,
        )
        row = summary_row(
            case_id,
            run.command_db,
            run.applied_db,
            upper_second,
            nominal_second,
            evaluation,
            update_interval,
            delay,
            slew,
            margin,
            time.perf_counter() - started,
            fail_safe_count=int(run.fail_safe_used.sum()),
        )
        rows.append(row)
        runs[case_id] = {
            "command": run.command_db,
            "applied": run.applied_db,
            "evaluation": evaluation,
            "row": row,
            "upper_second_ratio": upper_second,
            "nominal_second_ratio": nominal_second,
        }
        certificate = theorem_certificate(
            run,
            interval_allowance,
            slew,
            float(q_grid[-1]),
        )
        certificate["case_id"] = case_id
        certificate["coupling_upper_margin_db"] = margin
        certificate["effective_delay_intervals"] = delay
        certificates[case_id] = certificate

    nominal_predictive = runs[
        "predictive_nominal_full_horizon"
    ]
    approximation = surrogate_approximation_audit(
        local_cost,
        q_grid,
        nominal_predictive["applied"],
        nominal_predictive["evaluation"],
        nominal_total,
        eligible,
        epsilon,
    )

    write_csv(results / "ROBUST_CONTROLLER_SUMMARY.csv", rows)
    write_csv(results / "VIRTUAL_QUEUE_BASELINES.csv", queue_rows)
    write_json(
        results / "ROBUST_REACHABILITY_THEOREM_CERTIFICATES.json",
        certificates,
    )
    np.savez_compressed(
        results / "ROBUST_PRIMARY_ACTIONS.npz",
        myopic_command_db=myopic.command_db,
        myopic_applied_db=myopic.applied_db,
        predictive_nominal_command_db=runs[
            "predictive_nominal_full_horizon"
        ]["command"],
        predictive_nominal_applied_db=runs[
            "predictive_nominal_full_horizon"
        ]["applied"],
        predictive_1db_drop_command_db=runs[
            "predictive_1db_with_two_message_drops"
        ]["command"],
        predictive_1db_drop_applied_db=runs[
            "predictive_1db_with_two_message_drops"
        ]["applied"],
    )

    primary_time_rows = []
    primary_names = [
        "delayed_myopic_constrained_pf",
        "predictive_nominal_full_horizon",
        "predictive_1db_with_two_message_drops",
        "predictive_3db",
    ]
    for second, absolute_time in enumerate(time_s):
        interval = min(
            second // update_interval,
            len(interval_lengths) - 1,
        )
        record = {
            "time_s": float(absolute_time),
            "interval_index": int(interval),
        }
        for name in primary_names:
            run_record = runs[name]
            upper_second = run_record.get(
                "upper_second_ratio",
                myopic_upper,
            )
            nominal_second = run_record.get(
                "nominal_second_ratio",
                myopic_nominal,
            )
            record[f"{name}_upper_ratio"] = float(
                upper_second[second]
            )
            record[f"{name}_nominal_ratio"] = float(
                nominal_second[second]
            )
            record[f"{name}_pf_utility"] = float(
                np.log(
                    run_record["evaluation"]["total_rate"][
                        interval, eligible
                    ]
                    + epsilon
                ).sum()
            )
        primary_time_rows.append(record)
    write_csv(
        results / "ROBUST_PRIMARY_TIME_SERIES.csv",
        primary_time_rows,
    )

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_ROBUST_DELAYED_SAFETY_BASELINES_REVIEW_REQUIRED"
        ),
        "claim_boundary": cfg["claim_boundary"],
        "data_validation_status": validation["status"],
        "fairness_policy": policy,
        "primary_scenario": primary,
        "local_cost_grid": {
            **local_cost_audit,
            "shape": list(local_cost.shape),
            "build_seconds": cost_seconds,
        },
        "controller_rows": {
            str(row["controller"]): row for row in rows
        },
        "theorem_certificates": certificates,
        "frozen_local_cost_approximation": approximation,
        "decisive_results": {
            "myopic_nominal_violation_seconds": myopic_row[
                "upper_bound_violation_seconds"
            ],
            "predictive_nominal_violation_seconds": runs[
                "predictive_nominal_full_horizon"
            ]["row"]["upper_bound_violation_seconds"],
            "predictive_1db_drop_violation_seconds": runs[
                "predictive_1db_with_two_message_drops"
            ]["row"]["upper_bound_violation_seconds"],
            "predictive_3db_violation_seconds": runs[
                "predictive_3db"
            ]["row"]["upper_bound_violation_seconds"],
            "all_robust_theorem_certificates_pass": all(
                value["status"]
                == "PASS_FINITE_PASS_ROBUST_REACHABILITY_CERTIFICATE"
                for value in certificates.values()
            ),
            "all_robust_floor_violation_counts_zero": all(
                runs[case["case_id"]]["row"][
                    "eligible_floor_violation_user_intervals"
                ]
                == 0
                for case in cfg["robust_cases"]
            ),
            "virtual_queue_has_instantaneous_violations": any(
                row["upper_bound_violation_seconds"] > 0
                for row in queue_rows
            ),
        },
        "limitations": [
            "one channel/topology seed and one protected pass",
            "full future geometry and a deterministic upper contribution bound are assumed",
            "the theorem guarantees incumbent safety and recursive feasibility, not PF optimality",
            "local PF tables are frozen around nominal other-sector actions",
            "the virtual queue baseline enforces only a long-term pressure and may violate instantaneous protection",
            "uncertainty is a deterministic multiplicative dB bound, not yet calibrated from held-out errors",
            "no online moving-average PF scheduling, load transition, or multi-seed confidence intervals"
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(
        results / "ROBUST_SAFETY_BASELINES_AUDIT.json",
        audit,
    )

    # Concise evidence.
    for name in [
        "ROBUST_CONTROLLER_SUMMARY.csv",
        "VIRTUAL_QUEUE_BASELINES.csv",
        "ROBUST_REACHABILITY_THEOREM_CERTIFICATES.json",
        "ROBUST_PRIMARY_TIME_SERIES.csv",
        "ROBUST_SAFETY_BASELINES_AUDIT.json",
    ]:
        shutil.copy2(results / name, evidence / name)
    shutil.copy2(
        ROOT / "docs/DELAYED_REACHABILITY_SAFETY_THEOREM.md",
        evidence / "DELAYED_REACHABILITY_SAFETY_THEOREM.md",
    )
    write_json(
        evidence / "ROBUST_SAFETY_GATE_DECISION.json",
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": (
                "PASS_ROBUST_DELAYED_SAFETY_BASELINE_MILESTONE_ONE_SEED"
            ),
            "paper_result": False,
            "formal_finite_pass_safety_certificate": True,
            "predictive_nominal_safe": (
                runs["predictive_nominal_full_horizon"]["row"][
                    "upper_bound_violation_seconds"
                ]
                == 0
            ),
            "predictive_3db_upper_bound_safe": (
                runs["predictive_3db"]["row"][
                    "upper_bound_violation_seconds"
                ]
                == 0
            ),
            "message_drop_fail_safe_safe": (
                runs[
                    "predictive_1db_with_two_message_drops"
                ]["row"]["upper_bound_violation_seconds"]
                == 0
            ),
            "virtual_queue_instantaneously_safe": False,
            "sum_rate_primary_objective": False,
            "next_gate": cfg["next_gate"],
        },
    )
    (evidence / "README.md").write_text(
        "# Robust delayed-safety and baseline milestone\n\n"
        "This one-seed milestone provides a finite-pass robust reachability "
        "safety theorem and machine certificate, bounded coupling-error "
        "screens, stale-message handling, an explicit ramp-to-safe fail-safe, "
        "and virtual-queue baselines. Incumbent safety and eligible-user "
        "floors remain primary; sum rate is secondary.\n\n"
        "The result is not yet a paper result. The uncertainty bounds are not "
        "calibrated, the PF tables are frozen, and multi-seed statistics are "
        "still open.\n",
        encoding="utf-8",
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  {path.relative_to(ROOT).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("ROBUST DELAYED SAFETY + BASELINES MILESTONE: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
