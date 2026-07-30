#!/usr/bin/env python3
"""Strict validation of the robust delayed-safety and baseline milestone."""
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
        default="config/robust_safety_baselines_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]

    audit = json.loads(
        (results / "ROBUST_SAFETY_BASELINES_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    gate = json.loads(
        (evidence / "ROBUST_SAFETY_GATE_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    certificates = json.loads(
        (
            results
            / "ROBUST_REACHABILITY_THEOREM_CERTIFICATES.json"
        ).read_text(encoding="utf-8")
    )
    summary = pd.read_csv(results / "ROBUST_CONTROLLER_SUMMARY.csv")

    assert audit["status"] == (
        "PASS_ROBUST_DELAYED_SAFETY_BASELINES_REVIEW_REQUIRED"
    )
    assert gate["status"] == (
        "PASS_ROBUST_DELAYED_SAFETY_BASELINE_MILESTONE_ONE_SEED"
    )
    assert gate["paper_result"] is False
    assert gate["formal_finite_pass_safety_certificate"] is True
    assert gate["sum_rate_primary_objective"] is False

    for case_id, certificate in certificates.items():
        assert certificate["status"] == (
            "PASS_FINITE_PASS_ROBUST_REACHABILITY_CERTIFICATE"
        ), case_id
        assert all(certificate["checks"].values()), case_id
        assert certificate["maximum_command_slew_db"] <= 3.0 + 1e-12
        assert certificate["maximum_upper_safety_ratio"] <= (
            1.0 + 1e-10
        )

    by_name = summary.set_index("controller")
    assert by_name.loc[
        "delayed_myopic_constrained_pf",
        "upper_bound_violation_seconds",
    ] > 0
    assert by_name.loc[
        "predictive_nominal_full_horizon",
        "upper_bound_violation_seconds",
    ] == 0
    assert by_name.loc[
        "predictive_1db_with_two_message_drops",
        "upper_bound_violation_seconds",
    ] == 0
    assert by_name.loc[
        "predictive_1db_with_two_message_drops",
        "fail_safe_command_count",
    ] == 2
    assert by_name.loc[
        "predictive_3db",
        "upper_bound_violation_seconds",
    ] == 0
    assert by_name.loc[
        "predictive_1db_plus_one_stale_interval",
        "upper_bound_violation_seconds",
    ] == 0

    robust_rows = summary.loc[
        summary["controller"].str.startswith("predictive_")
    ]
    assert (
        robust_rows["eligible_floor_violation_user_intervals"] == 0
    ).all()
    assert (robust_rows["minimum_floor_ratio"] >= 1.0).all()

    assert by_name.loc[
        "predictive_1db_with_two_message_drops",
        "mean_pf_utility",
    ] > by_name.loc[
        "static_robust_constrained_pf_1db",
        "mean_pf_utility",
    ]
    assert by_name.loc[
        "predictive_3db",
        "mean_pf_utility",
    ] > by_name.loc[
        "static_robust_constrained_pf_3db",
        "mean_pf_utility",
    ]

    queue = summary.loc[
        summary["controller"].str.startswith("virtual_queue")
    ]
    assert (queue["upper_bound_violation_seconds"] > 0).all()

    approximation = audit["frozen_local_cost_approximation"]
    assert approximation["pearson_correlation"] > 0.99
    assert (
        audit["decisive_results"][
            "all_robust_theorem_certificates_pass"
        ]
        is True
    )
    assert (
        audit["decisive_results"][
            "all_robust_floor_violation_counts_zero"
        ]
        is True
    )

    print("ROBUST DELAYED SAFETY + BASELINES STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "status": gate["status"],
                "myopic_violation_seconds": int(
                    by_name.loc[
                        "delayed_myopic_constrained_pf",
                        "upper_bound_violation_seconds",
                    ]
                ),
                "predictive_nominal_violation_seconds": 0,
                "predictive_3db_violation_seconds": 0,
                "message_drop_fail_safe_count": 2,
                "virtual_queue_has_violations": True,
                "paper_result": False,
                "next_gate": cfg["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
