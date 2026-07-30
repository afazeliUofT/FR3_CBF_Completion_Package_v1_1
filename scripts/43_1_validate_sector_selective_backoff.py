#!/usr/bin/env python3
"""Strict validation of the declared-envelope sector-selective fallback."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/sector_selective_backoff_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]

    audit = json.loads(
        (results / "SECTOR_BACKOFF_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    gate = json.loads(
        (evidence / "SECTOR_BACKOFF_GATE_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    summary = pd.read_csv(
        results / "SECTOR_BACKOFF_SCENARIO_SUMMARY.csv"
    )
    users = pd.read_csv(results / "PRIMARY_USER_METRICS.csv")
    time_series = pd.read_csv(
        results / "PRIMARY_SECTOR_BACKOFF_TIME_SERIES.csv"
    )
    with np.load(
        results / "PRIMARY_SECTOR_BACKOFF_ACTIONS.npz"
    ) as actions:
        action_shapes = {
            key: tuple(actions[key].shape)
            for key in actions.files
        }

    assert audit["status"] == (
        "PASS_DECLARED_ENVELOPE_SECTOR_BACKOFF_REVIEW_REQUIRED"
    )
    assert gate["status"] == (
        "PASS_DECLARED_ENGINEERING_ENVELOPE_SECTOR_BACKOFF_ONE_SEED"
    )
    assert gate["paper_result"] is False
    assert gate["regulatory_compliance_result"] is False
    assert gate["measured_calibration"] is False
    assert gate["campaign_execution_authorized"] is False
    assert audit["campaign_execution_authorized"] is False
    assert audit["scenario_row_count"] == 36
    assert len(summary) == 36
    assert set(summary["pattern"]) == {"multiple", "single"}
    assert set(summary["method"]) == {"sector_selective", "uniform"}
    assert set(summary["null_depth_cap_db"]) == {60.0, 65.0, 67.0}
    assert set(summary["residual_coupling_uplift_db"]) == {
        0.0,
        1.0,
        3.0,
    }

    selective_rows = summary.loc[
        summary["method"] == "sector_selective"
    ]
    assert len(selective_rows) == 18
    assert (selective_rows["long_violation_seconds"] == 0).all()
    assert (
        selective_rows["paired_short_violation_seconds"] == 0
    ).all()
    assert (
        selective_rows["maximum_envelope_ratio"] <= 1.0 + 1e-10
    ).all()
    assert audit["all_sector_selective_long_safe"] is True
    assert audit["all_sector_selective_paired_short_safe"] is True

    declared = cfg["declared_engineering_envelope"]
    primary = declared["primary_decisive_screen"]
    primary_selective = summary.loc[
        (summary["pattern"] == primary["pattern"])
        & (
            summary["null_depth_cap_db"]
            == float(primary["null_depth_cap_db"])
        )
        & (
            summary["residual_coupling_uplift_db"]
            == float(primary["residual_coupling_uplift_db"])
        )
        & (summary["method"] == "sector_selective")
    ].iloc[0]
    primary_uniform = summary.loc[
        (summary["pattern"] == primary["pattern"])
        & (
            summary["null_depth_cap_db"]
            == float(primary["null_depth_cap_db"])
        )
        & (
            summary["residual_coupling_uplift_db"]
            == float(primary["residual_coupling_uplift_db"])
        )
        & (summary["method"] == "uniform")
    ].iloc[0]

    assert primary_selective["long_violation_seconds"] == 0
    assert primary_selective["paired_short_violation_seconds"] == 0
    assert (
        primary_selective["eligible_floor_violation_user_intervals"]
        == 0
    )
    assert primary_selective["minimum_floor_ratio"] >= 1.0
    assert (
        primary_uniform["eligible_floor_violation_user_intervals"]
        > 0
    )
    assert (
        primary_selective["mean_moving_pf_utility"]
        > primary_uniform["mean_moving_pf_utility"]
    )
    assert (
        primary_selective["mean_protected_network_retention"]
        > primary_uniform["mean_protected_network_retention"]
    )
    assert primary_selective["sector_mute_interval_count"] > 0

    boundary = declared["boundary_screen"]
    boundary_selective = summary.loc[
        (summary["pattern"] == boundary["pattern"])
        & (
            summary["null_depth_cap_db"]
            == float(boundary["null_depth_cap_db"])
        )
        & (
            summary["residual_coupling_uplift_db"]
            == float(boundary["residual_coupling_uplift_db"])
        )
        & (summary["method"] == "sector_selective")
    ].iloc[0]
    assert boundary_selective["long_violation_seconds"] == 0
    assert boundary_selective["paired_short_violation_seconds"] == 0
    # The 60 dB + 3 dB boundary is expected to expose a fairness limitation.
    assert (
        boundary_selective["eligible_floor_violation_user_intervals"]
        > 0
    )

    assert len(users) == 228
    assert users["user_id"].nunique() == 228
    assert users["eligible"].sum() == 207
    assert len(time_series) == 587
    assert time_series["long_ratio"].max() <= 1.0 + 1e-10
    assert time_series["short_ratio"].max() <= 1.0 + 1e-10
    assert time_series["muted_sector_count"].max() > 0

    expected_shapes = {
        "sector_selective_sector_backoff_db": (118, 57),
        "sector_selective_sector_power_scale": (118, 57),
        "uniform_sector_backoff_db": (118, 57),
        "uniform_sector_power_scale": (118, 57),
    }
    assert action_shapes == expected_shapes

    print("SECTOR-SELECTIVE BACKOFF STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "status": gate["status"],
                "primary_selective_floor_violations": int(
                    primary_selective[
                        "eligible_floor_violation_user_intervals"
                    ]
                ),
                "primary_uniform_floor_violations": int(
                    primary_uniform[
                        "eligible_floor_violation_user_intervals"
                    ]
                ),
                "primary_selective_pf_utility": float(
                    primary_selective["mean_moving_pf_utility"]
                ),
                "primary_uniform_pf_utility": float(
                    primary_uniform["mean_moving_pf_utility"]
                ),
                "boundary_selective_floor_violations": int(
                    boundary_selective[
                        "eligible_floor_violation_user_intervals"
                    ]
                ),
                "campaign_execution_authorized": False,
                "next_gate": cfg["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
