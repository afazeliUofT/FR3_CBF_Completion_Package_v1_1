#!/usr/bin/env python3
"""Strict validation of the constrained-PF controller milestone."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=(
            "config/"
            "constrained_pf_controller_milestone_v1.json"
        ),
    )
    args = parser.parse_args()
    cfg = json.loads(
        (ROOT / args.config).read_text(encoding="utf-8")
    )
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]

    audit = json.loads(
        (
            results / "CONSTRAINED_PF_CONTROLLER_AUDIT.json"
        ).read_text(encoding="utf-8")
    )
    decision = json.loads(
        (
            evidence
            / "CONSTRAINED_PF_CONTROLLER_GATE_DECISION.json"
        ).read_text(encoding="utf-8")
    )
    summary = pd.read_csv(
        results / "CONTROLLER_FAIRNESS_SUMMARY.csv"
    )
    users = pd.read_csv(
        results / "PRIMARY_USER_FAIRNESS.csv"
    )
    groups = pd.read_csv(
        results / "PRIMARY_GROUP_FAIRNESS.csv"
    )

    assert audit["status"] == (
        "PASS_CONSTRAINED_PF_CONTROLLER_MILESTONE_REVIEW_REQUIRED"
    )
    assert decision["status"] == (
        "PASS_CONSTRAINED_PF_CONTROLLER_MILESTONE_ONE_SEED"
    )
    assert decision["paper_result"] is False
    assert decision["sum_rate_primary_objective"] is False
    assert audit["user_classification"]["eligible_users"] == 207
    assert (
        audit["user_classification"]["coverage_limited_users"]
        == 21
    )

    rows = {
        row["controller"]: row
        for row in summary.to_dict(orient="records")
    }
    required = {
        "delayed_myopic_constrained_pf",
        "predictive_reachability_constrained_pf",
        "static_constrained_pf",
        "common_scale_oracle",
        "hard_spatial_null",
    }
    assert set(rows) == required

    myopic = rows["delayed_myopic_constrained_pf"]
    predictive = rows[
        "predictive_reachability_constrained_pf"
    ]
    static = rows["static_constrained_pf"]
    common = rows["common_scale_oracle"]
    hard = rows["hard_spatial_null"]

    assert myopic["incumbent_violation_seconds"] > 0
    assert predictive["incumbent_violation_seconds"] == 0
    assert static["incumbent_violation_seconds"] == 0
    assert common["incumbent_violation_seconds"] == 0
    assert hard["incumbent_violation_seconds"] == 0

    for row in rows.values():
        assert (
            row["eligible_floor_violation_user_intervals"]
            == 0
        )
        assert row["unique_eligible_floor_violation_users"] == 0
        assert row["maximum_normalized_floor_shortfall"] == 0.0
        assert row["minimum_floor_ratio"] >= 1.0 - 1e-12

    assert predictive["maximum_command_slew_db"] <= (
        cfg["primary_scenario"]["slew_db_per_update"]
        + 1e-12
    )
    assert predictive["command_feasible_all_intervals"]
    assert predictive["mean_pf_utility"] > (
        static["mean_pf_utility"] + 0.05
    )
    assert predictive["mean_geometric_rate_bps_hz"] > (
        static["mean_geometric_rate_bps_hz"] + 1e-4
    )
    assert predictive["mean_pf_utility"] >= (
        myopic["mean_pf_utility"] - 1e-6
    )
    assert predictive["mean_protected_network_retention_secondary"] > (
        static["mean_protected_network_retention_secondary"]
        + 5e-3
    )
    assert predictive["mean_total_network_retention_secondary"] > (
        static["mean_total_network_retention_secondary"]
        + 5e-4
    )

    assert users["user_id"].nunique() == 228
    assert int(users["eligible"].sum()) == 207
    assert int((~users["eligible"]).sum()) == 21
    for controller in required:
        assert (
            users[f"{controller}_floor_violation"].sum()
            == 0
        )
    assert set(groups["group"]) == {
        "eligible_all",
        "eligible_indoor",
        "eligible_outdoor",
        "coverage_limited_all",
        "coverage_limited_indoor",
        "coverage_limited_outdoor",
    }

    print("CONSTRAINED PF CONTROLLER STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "status": decision["status"],
                "myopic_incumbent_violation_seconds": int(
                    myopic["incumbent_violation_seconds"]
                ),
                "predictive_incumbent_violation_seconds": int(
                    predictive["incumbent_violation_seconds"]
                ),
                "predictive_floor_violation_user_intervals": int(
                    predictive[
                        "eligible_floor_violation_user_intervals"
                    ]
                ),
                "predictive_mean_pf_utility": float(
                    predictive["mean_pf_utility"]
                ),
                "static_mean_pf_utility": float(
                    static["mean_pf_utility"]
                ),
                "paper_result": False,
                "next_gate": cfg["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
