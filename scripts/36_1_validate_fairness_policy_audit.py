#!/usr/bin/env python3
"""Strict validation of the one-seed fairness policy audit."""
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
        default="config/fairness_policy_audit_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]

    audit = json.loads(
        (results / "FAIRNESS_POLICY_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    decision = json.loads(
        (evidence / "FAIRNESS_POLICY_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    floor = pd.read_csv(
        results / "FAIRNESS_FLOOR_SENSITIVITY.csv"
    )
    outage = pd.read_csv(
        results / "ABSOLUTE_RATE_OUTAGE_COUNTS.csv"
    )

    assert audit["status"] == (
        "PASS_FAIRNESS_POLICY_AUDIT_REVIEW_REQUIRED"
    )
    assert decision["status"] == (
        "PASS_CONSTRAINED_PF_POLICY_FROZEN_FOR_ONE_SEED_CONTROLLER_MILESTONE"
    )
    assert decision["sum_rate_primary_objective"] is False
    assert decision["explicit_service_floor"] is True
    assert audit["user_counts"] == {
        "total": 228,
        "indoor": 184,
        "outdoor": 44,
    }
    assert audit["indoor_outdoor_audit"][
        "indoor_median_exceeds_outdoor_median"
    ] is True

    primary = floor.loc[
        (floor["serviceability_threshold_bps_hz"] == 0.1)
        & (floor["relative_floor_fraction"] == 0.9)
    ].iloc[0]
    assert int(primary["eligible_user_count"]) == 207
    assert int(primary["coverage_limited_user_count"]) == 21
    assert int(primary["coverage_limited_indoor_count"]) == 3
    assert int(primary["coverage_limited_outdoor_count"]) == 18
    assert int(
        primary[
            "common_scale_controller_induced_floor_violation_count"
        ]
    ) == 0

    strict = floor.loc[
        (floor["serviceability_threshold_bps_hz"] == 0.1)
        & (floor["relative_floor_fraction"] == 0.95)
    ].iloc[0]
    assert int(
        strict[
            "common_scale_controller_induced_floor_violation_count"
        ]
    ) == 10

    nominal_total_01 = outage.loc[
        (outage["scenario"] == "nominal_total_band")
        & (outage["absolute_rate_threshold_bps_hz"] == 0.1)
    ].iloc[0]
    assert int(nominal_total_01["below_threshold_count"]) == 21

    print("FR3 FAIRNESS POLICY AUDIT STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "paper_result": False,
                "primary_objective": "constrained_proportional_fairness",
                "eligible_users_at_0_1_bps_hz": 207,
                "coverage_limited_users": 21,
                "common_scale_90_percent_floor_violations": 0,
                "next_gate": cfg["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
