#!/usr/bin/env python3
"""Strict validation of the corrected dual-criterion controller rerun."""
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
        default="config/dual_criterion_controller_reevaluation_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]

    audit = json.loads(
        (results / "DUAL_CRITERION_CONTROLLER_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    gate = json.loads(
        (
            evidence / "DUAL_CRITERION_CONTROLLER_GATE_DECISION.json"
        ).read_text(encoding="utf-8")
    )
    dominance = json.loads(
        (results / "DUAL_CRITERION_DOMINANCE_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    summary = pd.read_csv(results / "DUAL_CRITERION_CONTROLLER_SUMMARY.csv")

    assert audit["status"] == (
        "PASS_CORRECTED_DUAL_CRITERION_CONTROLLER_REEVALUATION_REVIEW_REQUIRED"
    )
    assert gate["status"] == (
        "PASS_CORRECTED_DUAL_CRITERION_CONTROLLER_ONE_SEED"
    )
    assert gate["paper_result"] is False
    assert gate["regulatory_compliance_result"] is False
    assert gate["new_nibi_job_required"] is False
    assert gate["all_predictive_cases_safe"] is True
    assert gate["all_predictive_certificates_pass"] is True
    assert gate["all_predictive_floor_violations_zero"] is True
    assert gate["q70_terminal_safe_all_cases"] is True
    assert gate["long_term_dominates_short_term"] is True

    assert len(summary) == 25
    cases = set(cfg["criteria"])
    assert set(summary["case"]) == cases

    def row(case: str, controller: str) -> pd.Series:
        selected = summary.loc[
            (summary["case"] == case)
            & (summary["controller"] == controller)
        ]
        assert len(selected) == 1
        return selected.iloc[0]

    for case in cases:
        predictive = row(case, "online_predictive_constrained_pf")
        myopic = row(case, "online_delayed_myopic_constrained_pf")
        static = row(case, "static_constrained_pf")
        queue = row(case, "virtual_queue_gain_1_online_pf")
        common = row(case, "instantaneous_common_scale_oracle")
        hard = row(case, "exact_hard_null_reference")

        assert predictive["violation_seconds"] == 0
        assert static["violation_seconds"] == 0
        assert common["violation_seconds"] == 0
        assert hard["violation_seconds"] == 0
        assert myopic["violation_seconds"] > 0
        assert queue["violation_seconds"] > 0
        assert predictive["certificate_status"] == (
            "PASS_CORRECTED_FINITE_PASS_DYNAMIC_CERTIFICATE"
        )
        assert predictive["maximum_command_slew_db"] <= (
            cfg["controller_timing"]["slew_db_per_update"] + 1e-12
        )
        assert predictive["maximum_finite_action_db"] <= 70.0
        assert predictive["eligible_floor_violation_user_interval_count"] == 0
        assert predictive["minimum_floor_ratio"] >= 1.0 - 1e-10
        assert predictive["mean_moving_pf_utility"] > (
            hard["mean_moving_pf_utility"]
        )
        assert predictive["mean_moving_pf_utility"] > (
            static["mean_moving_pf_utility"]
        )

    dropped = row(
        "long_multiple",
        "online_predictive_constrained_pf_two_drops",
    )
    assert dropped["violation_seconds"] == 0
    assert dropped["fail_safe_command_count"] == 2
    assert dropped["certificate_status"] == (
        "PASS_CORRECTED_FINITE_PASS_DYNAMIC_CERTIFICATE"
    )
    assert dropped["eligible_floor_violation_user_interval_count"] == 0

    for pattern in ["multiple", "single"]:
        value = dominance[pattern]
        assert value["long_constraint_elementwise_dominates"] is True
        assert value["minimum_long_dominance_margin_db"] > 13.0
        assert (
            value[
                "long_predictive_actions_short_term_violation_seconds"
            ]
            == 0
        )
        assert (
            value[
                "long_predictive_actions_short_term_maximum_ratio"
            ]
            < 0.05
        )

    short_multiple = row(
        "short_multiple", "online_predictive_constrained_pf"
    )
    long_multiple = row(
        "long_multiple", "online_predictive_constrained_pf"
    )
    short_single = row(
        "short_single", "online_predictive_constrained_pf"
    )
    long_single = row(
        "long_single", "online_predictive_constrained_pf"
    )
    assert short_multiple["mean_moving_pf_utility"] > long_multiple[
        "mean_moving_pf_utility"
    ]
    assert short_single["mean_moving_pf_utility"] > long_single[
        "mean_moving_pf_utility"
    ]
    assert short_multiple["mean_moving_pf_utility"] > short_single[
        "mean_moving_pf_utility"
    ]
    assert long_multiple["mean_moving_pf_utility"] > long_single[
        "mean_moving_pf_utility"
    ]

    print("CORRECTED DUAL-CRITERION CONTROLLER STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "status": gate["status"],
                "long_multiple_predictive_pf_utility": float(
                    long_multiple["mean_moving_pf_utility"]
                ),
                "long_multiple_myopic_violation_seconds": int(
                    row(
                        "long_multiple",
                        "online_delayed_myopic_constrained_pf",
                    )["violation_seconds"]
                ),
                "long_single_predictive_pf_utility": float(
                    long_single["mean_moving_pf_utility"]
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
