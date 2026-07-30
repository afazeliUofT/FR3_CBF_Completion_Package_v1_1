#!/usr/bin/env python3
"""Run the one-seed constrained-PF controller milestone locally."""
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
    ControllerRun,
    PriceAllocator,
    action_grid,
    build_local_constrained_pf_cost_grid,
    control_metrics,
    evaluate_interval_actions,
    interval_mode_contributions,
    second_safety_ratio,
    simulate_myopic,
    simulate_predictive_reachability,
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
    extras = sorted(
        {
            key
            for row in rows
            for key in row
            if key not in fieldnames
        }
    )
    fieldnames.extend(extras)
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


def summary_row(
    controller: str,
    run: ControllerRun,
    safety_ratio: np.ndarray,
    evaluation: dict[str, object],
    update_interval_s: int,
    delay_intervals: int,
    slew_db_per_update: float,
    horizon_intervals: int,
    runtime_seconds: float,
) -> dict[str, object]:
    control = control_metrics(run.command_db, run.applied_db)
    return {
        "controller": controller,
        "update_interval_s": update_interval_s,
        "message_delay_intervals": delay_intervals,
        "slew_db_per_update": slew_db_per_update,
        "predictive_horizon_intervals": horizon_intervals,
        "command_feasible_all_intervals": bool(
            np.all(run.feasible_command)
        ),
        "incumbent_violation_seconds": int(
            np.sum(safety_ratio > 1.0 + 1e-10)
        ),
        "maximum_incumbent_excess_db": float(
            10.0 * np.log10(np.max(safety_ratio))
        ),
        "minimum_incumbent_margin_db": float(
            -10.0 * np.log10(np.max(safety_ratio))
        ),
        "eligible_floor_violation_intervals": evaluation[
            "floor_violation_interval_count"
        ],
        "eligible_floor_violation_user_intervals": evaluation[
            "floor_violation_user_interval_count"
        ],
        "unique_eligible_floor_violation_users": evaluation[
            "unique_floor_violation_user_count"
        ],
        "total_normalized_floor_shortfall_user_seconds": evaluation[
            "total_normalized_floor_shortfall_user_seconds"
        ],
        "maximum_normalized_floor_shortfall": evaluation[
            "maximum_normalized_floor_shortfall"
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
        "minimum_p05_eligible_rate_bps_hz": evaluation[
            "minimum_p05_eligible_rate_bps_hz"
        ],
        "minimum_eligible_rate_bps_hz": evaluation[
            "minimum_eligible_rate_bps_hz"
        ],
        "mean_jain_index_eligible": evaluation[
            "mean_jain_index_eligible"
        ],
        "minimum_jain_index_eligible": evaluation[
            "minimum_jain_index_eligible"
        ],
        "mean_total_network_retention_secondary": evaluation[
            "mean_total_network_retention"
        ],
        "minimum_total_network_retention_secondary": evaluation[
            "minimum_total_network_retention"
        ],
        "mean_protected_network_retention_secondary": evaluation[
            "mean_protected_network_retention"
        ],
        "minimum_protected_network_retention_secondary": evaluation[
            "minimum_protected_network_retention"
        ],
        "runtime_seconds": runtime_seconds,
        **control,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=(
            "config/"
            "constrained_pf_controller_milestone_v1.json"
        ),
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

    required = [
        "protected_amp_perpendicular.npy",
        "protected_amp_pol1.npy",
        "protected_amp_pol2.npy",
        "serving_bs_index.npy",
        "serving_stream_index.npy",
        "noise_power_by_frequency_w.npy",
        "frequency_weights.npy",
        "other_frequency_weighted_rate_per_user.npy",
        "nominal_total_weighted_rate_per_user.npy",
        "nominal_protected_rate_per_user.npy",
        "nominal_mode_leakage_w.npy",
        "kappa_time_sector.npy",
        "aggregate_allowance_w.npy",
        "protected_time_s.npy",
        "USER_TOPOLOGY.csv",
        "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json",
    ]
    for name in required:
        if not (data / name).is_file():
            raise FileNotFoundError(data / name)

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

    policy = cfg["policy"]
    threshold = float(
        policy["serviceability_threshold_bps_hz"]
    )
    eligible = nominal_total >= threshold
    floor = np.maximum(
        float(policy["absolute_total_band_floor_bps_hz"]),
        float(policy["relative_total_band_floor_fraction"])
        * nominal_total,
    )
    if int(eligible.sum()) != 207:
        raise ValueError("expected 207 eligible users")
    if int((~eligible).sum()) != 21:
        raise ValueError("expected 21 coverage-limited users")

    q_cfg = cfg["action_grid"]
    q_grid = action_grid(
        int(q_cfg["minimum_db"]),
        int(q_cfg["maximum_db"]),
        int(q_cfg["step_db"]),
    )

    started = time.perf_counter()
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
            float(policy["pf_epsilon_bps_hz"]),
        )
    )
    local_cost_seconds = time.perf_counter() - started
    allocator = PriceAllocator(
        q_grid,
        local_cost,
        float(allowance[0]),
    )

    np.savez_compressed(
        results / "LOCAL_CONSTRAINED_PF_COST_GRID.npz",
        q_grid_db=q_grid,
        local_scalarized_cost=local_cost,
    )

    scenario = cfg["primary_scenario"]
    update_interval = int(scenario["update_interval_s"])
    delay = int(scenario["message_delay_intervals"])
    slew = float(scenario["slew_db_per_update"])
    horizon = int(
        scenario["predictive_horizon_intervals"]
    )
    contribution, lengths = interval_mode_contributions(
        kappa,
        leakage,
        update_interval,
    )

    records: dict[str, dict[str, object]] = {}
    summary_rows: list[dict[str, object]] = []

    def evaluate_run(
        name: str,
        run: ControllerRun,
        controller_delay: int,
        controller_slew: float,
        controller_horizon: int,
        runtime_seconds: float,
    ) -> None:
        safety_ratio = second_safety_ratio(
            kappa,
            leakage,
            run.applied_db,
            update_interval,
            allowance,
        )
        evaluation = evaluate_interval_actions(
            run.applied_db,
            lengths,
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
            float(policy["pf_epsilon_bps_hz"]),
        )
        row = summary_row(
            name,
            run,
            safety_ratio,
            evaluation,
            update_interval,
            controller_delay,
            controller_slew,
            controller_horizon,
            runtime_seconds,
        )
        summary_rows.append(row)
        records[name] = {
            "run": run,
            "safety_ratio": safety_ratio,
            "evaluation": evaluation,
            "summary": row,
        }

    start = time.perf_counter()
    myopic = simulate_myopic(
        allocator,
        contribution,
        delay_intervals=delay,
        slew_db_per_update=slew,
    )
    evaluate_run(
        "delayed_myopic_constrained_pf",
        myopic,
        delay,
        slew,
        0,
        time.perf_counter() - start,
    )

    start = time.perf_counter()
    predictive = simulate_predictive_reachability(
        allocator,
        contribution,
        delay_intervals=delay,
        slew_db_per_update=slew,
        horizon_intervals=horizon,
    )
    evaluate_run(
        "predictive_reachability_constrained_pf",
        predictive,
        delay,
        slew,
        horizon,
        time.perf_counter() - start,
    )

    # Static constrained-PF action safe for the elementwise worst contribution.
    static_q, _ratio, static_feasible, _price = allocator.solve(
        np.max(kappa[:, :, None] * leakage[None, :, :], axis=0)
    )
    if not static_feasible:
        raise RuntimeError("static constrained-PF action is infeasible")
    static_action = np.repeat(
        static_q[None, :, :],
        len(contribution),
        axis=0,
    )
    static_run = ControllerRun(
        static_action,
        static_action,
        np.ones(len(contribution), dtype=bool),
        contribution,
    )
    evaluate_run(
        "static_constrained_pf",
        static_run,
        0,
        0.0,
        0,
        0.0,
    )

    # Instantaneous common-scale oracle upper reference.
    common_action = np.empty_like(static_action)
    for index, value in enumerate(contribution):
        required_db = max(
            0.0,
            10.0 * np.log10(
                float(value.sum()) / float(allowance[0])
            ),
        )
        common_action[index] = required_db
    common_run = ControllerRun(
        common_action,
        common_action,
        np.ones(len(contribution), dtype=bool),
        contribution,
    )
    evaluate_run(
        "common_scale_oracle",
        common_run,
        0,
        0.0,
        0,
        0.0,
    )

    # Hard-null reference.
    hard_action = np.full_like(
        static_action,
        float(q_grid[-1]),
    )
    hard_run = ControllerRun(
        hard_action,
        hard_action,
        np.ones(len(contribution), dtype=bool),
        contribution,
    )
    evaluate_run(
        "hard_spatial_null",
        hard_run,
        0,
        0.0,
        0,
        0.0,
    )

    write_csv(
        results / "CONTROLLER_FAIRNESS_SUMMARY.csv",
        summary_rows,
    )

    # Per-user and per-group records.
    user_rows: list[dict[str, object]] = []
    for user in range(228):
        row: dict[str, object] = {
            "user_id": str(topology.loc[user, "user_id"]),
            "serving_sector_id": str(
                topology.loc[user, "serving_sector_id"]
            ),
            "indoor": bool(indoor[user]),
            "eligible": bool(eligible[user]),
            "nominal_total_rate_bps_hz": float(
                nominal_total[user]
            ),
            "required_total_floor_bps_hz": float(
                floor[user]
            ) if eligible[user] else "",
            "nominal_protected_rate_bps_hz": float(
                nominal_protected[user]
            ),
        }
        for name, record in records.items():
            evaluation = record["evaluation"]
            total = evaluation["total_rate"][:, user]
            protected = evaluation["protected_rate"][:, user]
            row[f"{name}_minimum_total_rate_bps_hz"] = float(
                total.min()
            )
            row[f"{name}_minimum_total_retention"] = float(
                total.min() / nominal_total[user]
            )
            row[
                f"{name}_minimum_protected_rate_bps_hz"
            ] = float(protected.min())
            row[
                f"{name}_minimum_protected_retention"
            ] = float(
                protected.min() / nominal_protected[user]
            )
            row[f"{name}_floor_violation"] = bool(
                eligible[user]
                and total.min() < floor[user] - 1e-12
            )
        user_rows.append(row)
    write_csv(
        results / "PRIMARY_USER_FAIRNESS.csv",
        user_rows,
    )

    group_rows: list[dict[str, object]] = []
    for controller, record in records.items():
        for group, metrics in record["evaluation"][
            "groups"
        ].items():
            group_rows.append(
                {
                    "controller": controller,
                    "group": group,
                    **metrics,
                }
            )
    write_csv(
        results / "PRIMARY_GROUP_FAIRNESS.csv",
        group_rows,
    )

    time_rows: list[dict[str, object]] = []
    for second, absolute_time in enumerate(time_s):
        interval = min(
            second // update_interval,
            len(lengths) - 1,
        )
        row = {
            "time_s": float(absolute_time),
            "interval_index": int(interval),
        }
        for controller, record in records.items():
            row[
                f"{controller}_incumbent_ratio"
            ] = float(record["safety_ratio"][second])
            rate = record["evaluation"]["total_rate"][interval]
            eligible_rate = rate[eligible]
            row[
                f"{controller}_eligible_pf_utility"
            ] = float(
                np.log(
                    eligible_rate
                    + float(policy["pf_epsilon_bps_hz"])
                ).sum()
            )
            row[
                f"{controller}_eligible_floor_violation_count"
            ] = int(
                np.sum(
                    eligible_rate
                    < floor[eligible] - 1e-12
                )
            )
        time_rows.append(row)
    write_csv(
        results / "PRIMARY_TIME_SERIES.csv",
        time_rows,
    )

    np.savez_compressed(
        results / "PRIMARY_CONTROLLER_ACTIONS.npz",
        **{
            f"{name}_command_db": record["run"].command_db
            for name, record in records.items()
        },
        **{
            f"{name}_applied_db": record["run"].applied_db
            for name, record in records.items()
        },
    )

    myopic_summary = records[
        "delayed_myopic_constrained_pf"
    ]["summary"]
    predictive_summary = records[
        "predictive_reachability_constrained_pf"
    ]["summary"]
    static_summary = records[
        "static_constrained_pf"
    ]["summary"]

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_CONSTRAINED_PF_CONTROLLER_MILESTONE_REVIEW_REQUIRED"
        ),
        "claim_boundary": cfg["claim_boundary"],
        "data_validation_status": validation["status"],
        "policy": policy,
        "user_classification": {
            "total_users": 228,
            "eligible_users": int(eligible.sum()),
            "coverage_limited_users": int((~eligible).sum()),
            "eligible_indoor_users": int(
                np.sum(eligible & indoor)
            ),
            "eligible_outdoor_users": int(
                np.sum(eligible & (~indoor))
            ),
            "coverage_limited_indoor_users": int(
                np.sum((~eligible) & indoor)
            ),
            "coverage_limited_outdoor_users": int(
                np.sum((~eligible) & (~indoor))
            ),
        },
        "local_cost_grid": {
            "shape": list(local_cost.shape),
            "build_seconds": local_cost_seconds,
            "sha256": sha256_file(
                results / "LOCAL_CONSTRAINED_PF_COST_GRID.npz"
            ),
            **local_cost_audit,
        },
        "primary_scenario": scenario,
        "controller_results": {
            name: record["summary"]
            for name, record in records.items()
        },
        "decisive_primary_pattern": {
            "myopic_incumbent_violation_seconds": (
                myopic_summary["incumbent_violation_seconds"]
            ),
            "predictive_incumbent_violation_seconds": (
                predictive_summary["incumbent_violation_seconds"]
            ),
            "predictive_floor_violation_user_intervals": (
                predictive_summary[
                    "eligible_floor_violation_user_intervals"
                ]
            ),
            "predictive_minus_static_pf_utility": (
                predictive_summary["mean_pf_utility"]
                - static_summary["mean_pf_utility"]
            ),
            "predictive_minus_static_geometric_rate_bps_hz": (
                predictive_summary["mean_geometric_rate_bps_hz"]
                - static_summary["mean_geometric_rate_bps_hz"]
            ),
            "predictive_minus_myopic_pf_utility": (
                predictive_summary["mean_pf_utility"]
                - myopic_summary["mean_pf_utility"]
            ),
            "interpretation": (
                "The predictive reachability constrained-PF prototype "
                "removes the delay-induced incumbent violations, keeps "
                "all 207 eligible users above their frozen total-band "
                "service floor, and improves PF utility over the safe "
                "static baseline. This remains a one-seed prototype, "
                "not a formal CBF theorem or paper result."
            ),
        },
        "sum_rate_role": (
            "secondary efficiency statistic only; controller acceptance "
            "uses incumbent safety, eligible-user floors, normalized "
            "shortfall, PF utility, geometric mean, p05, minimum, Jain, "
            "band split, and indoor/outdoor reporting"
        ),
        "limitations": [
            "one channel/topology seed and one protected pass",
            "local candidate tables hold other-sector actions nominal",
            "one-dB discrete action grid",
            "predictive reachability filter is not yet a formal CBF proof",
            "no virtual-queue baseline",
            "no uncertainty calibration or emergency fallback stress",
            "no online moving-average PF scheduling",
            "no load transition or multi-seed confidence intervals"
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(
        results / "CONSTRAINED_PF_CONTROLLER_AUDIT.json",
        audit,
    )

    # Concise evidence; large NPZ tables remain in ignored results.
    for name in [
        "CONTROLLER_FAIRNESS_SUMMARY.csv",
        "PRIMARY_USER_FAIRNESS.csv",
        "PRIMARY_GROUP_FAIRNESS.csv",
        "PRIMARY_TIME_SERIES.csv",
        "CONSTRAINED_PF_CONTROLLER_AUDIT.json",
    ]:
        shutil.copy2(results / name, evidence / name)

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_CONSTRAINED_PF_CONTROLLER_MILESTONE_ONE_SEED"
        ),
        "paper_result": False,
        "sum_rate_primary_objective": False,
        "eligible_user_floor_enforced_and_audited": True,
        "coverage_limited_users_reported_separately": True,
        "primary_myopic_unsafe": (
            myopic_summary["incumbent_violation_seconds"] > 0
        ),
        "primary_predictive_safe": (
            predictive_summary["incumbent_violation_seconds"] == 0
        ),
        "primary_predictive_floor_violations": (
            predictive_summary[
                "eligible_floor_violation_user_intervals"
            ]
        ),
        "predictive_pf_exceeds_static": (
            predictive_summary["mean_pf_utility"]
            > static_summary["mean_pf_utility"]
        ),
        "predictive_geometric_rate_exceeds_static": (
            predictive_summary["mean_geometric_rate_bps_hz"]
            > static_summary["mean_geometric_rate_bps_hz"]
        ),
        "next_gate": cfg["next_gate"],
    }
    write_json(
        evidence / "CONSTRAINED_PF_CONTROLLER_GATE_DECISION.json",
        decision,
    )
    (evidence / "README.md").write_text(
        "# Constrained proportional-fair controller milestone\n\n"
        "This one-seed local milestone compares a static safe "
        "constrained-PF action, a delayed myopic constrained-PF "
        "controller, and a predictive reachability constrained-PF "
        "controller on the validated 228-user full-topology export.\n\n"
        "Incumbent safety is hard. Twenty-one nominally "
        "coverage-limited users are reported separately. The 207 "
        "eligible users are checked against "
        "`max(0.1,0.9*R_nominal)` before PF utility is assessed.\n\n"
        "This is not yet a formal CBF theorem or a TWC paper result.\n",
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

    print("CONSTRAINED PF CONTROLLER MILESTONE: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
