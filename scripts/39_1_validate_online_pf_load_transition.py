#!/usr/bin/env python3
"""Strict scientific validation of the online-PF load-transition milestone."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/online_pf_load_transition_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]

    audit = json.loads(
        (results / "ONLINE_PF_LOAD_TRANSITION_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    certificates = json.loads(
        (results / "ONLINE_PF_THEOREM_CERTIFICATES.json").read_text(
            encoding="utf-8"
        )
    )
    summary = pd.read_csv(results / "ONLINE_PF_CONTROLLER_SUMMARY.csv")
    phases = pd.read_csv(results / "LOAD_PHASES.csv")
    state_build = pd.read_csv(results / "LOAD_STATE_BUILD_AUDIT.csv")
    with np.load(
        results / "ONLINE_PF_ACTIONS_AND_AVERAGES.npz",
        allow_pickle=False,
    ) as arrays:
        action_arrays = {name: np.asarray(arrays[name]) for name in arrays.files}

    assert audit["status"] == (
        "PASS_ONLINE_MOVING_AVERAGE_PF_LOAD_TRANSITION_REVIEW_REQUIRED"
    )
    assert audit["data_validation_status"] == (
        "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
    )
    assert audit["claim_boundary"] == cfg["claim_boundary"]

    reproduction = audit["full_load_rzf_reproduction"]
    reproduction_decision = {
        "status": "PASS_PLATFORM_SCALED_FULL_LOAD_RZF_REPRODUCTION",
        "maximum_per_user_rate_error_bps_hz": reproduction[
            "maximum_per_user_rate_error_bps_hz"
        ],
        "maximum_per_user_tolerance_bps_hz": reproduction[
            "maximum_per_user_tolerance_bps_hz"
        ],
        "network_sum_error_bps_hz": reproduction[
            "network_sum_error_bps_hz"
        ],
        "network_sum_relative_error": reproduction[
            "network_sum_relative_error"
        ],
        "network_sum_relative_tolerance": reproduction[
            "network_sum_relative_tolerance"
        ],
        "interpretation": reproduction["interpretation"],
    }
    (results / "FULL_LOAD_RZF_REPRODUCTION_VALIDATION.json").write_text(
        json.dumps(reproduction_decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert reproduction[
        "maximum_per_user_rate_error_bps_hz"
    ] <= reproduction["maximum_per_user_tolerance_bps_hz"]
    assert reproduction[
        "network_sum_relative_error"
    ] <= reproduction["network_sum_relative_tolerance"]
    assert reproduction["network_sum_error_bps_hz"] <= (
        228.0
        * reproduction["maximum_per_user_rate_error_bps_hz"]
        + 1e-12
    )
    assert abs(
        reproduction["recomputed_network_sum_bps_hz"]
        - reproduction["reference_network_sum_bps_hz"]
    ) <= reproduction["network_sum_error_bps_hz"] + 1e-12

    assert len(phases) == 6
    assert int(phases["interval_count"].sum()) == 118
    assert phases["active_user_count"].tolist() == [228, 114, 228, 57, 171, 114]
    assert len(state_build) == 4
    assert audit["load_schedule"]["unique_recomputed_load_states"] == 4

    by_name = {
        row["controller"]: row
        for row in summary.to_dict(orient="records")
    }
    required = {
        "online_predictive_robust_1db",
        "online_predictive_robust_1db_two_drops",
        "online_predictive_robust_3db",
        "online_myopic_robust_1db",
        "static_robust_1db",
        "frozen_table_predictive_robust_1db",
    }
    assert set(by_name) == required

    myopic = by_name["online_myopic_robust_1db"]
    online = by_name["online_predictive_robust_1db"]
    dropped = by_name["online_predictive_robust_1db_two_drops"]
    robust3 = by_name["online_predictive_robust_3db"]
    static = by_name["static_robust_1db"]
    frozen = by_name["frozen_table_predictive_robust_1db"]

    assert int(myopic["upper_bound_violation_seconds"]) > 0
    assert int(online["upper_bound_violation_seconds"]) == 0
    assert int(dropped["upper_bound_violation_seconds"]) == 0
    assert int(robust3["upper_bound_violation_seconds"]) == 0
    assert int(dropped["fail_safe_command_count"]) == 2
    for row in [online, dropped, robust3, frozen]:
        assert row["certificate_status"] == (
            "PASS_CORRECTED_FINITE_PASS_DYNAMIC_CERTIFICATE"
        )
        assert int(row["eligible_floor_violation_user_interval_count"]) == 0
        assert float(row["maximum_command_slew_db"]) <= (
            float(cfg["slew_db_per_update"]) + 1e-12
        )
        assert float(row["minimum_floor_ratio"]) >= 1.0 - 1e-10
    assert float(online["mean_moving_pf_utility"]) > float(
        frozen["mean_moving_pf_utility"]
    )
    assert float(online["mean_moving_pf_utility"]) > (
        float(static["mean_moving_pf_utility"]) + 0.05
    )
    assert float(online["mean_protected_network_retention_secondary"]) > float(
        static["mean_protected_network_retention_secondary"]
    )
    assert float(robust3["minimum_active_eligible_rate_bps_hz"]) >= 0.1

    assert audit["decisive_results"]["all_online_predictive_certificates_pass"]
    assert audit["decisive_results"][
        "online_predictive_floor_violation_user_intervals"
    ] == 0
    assert audit["theorem_statement_repair"]["corrected_condition"].startswith(
        "F(q)=min(q+rho,Q)"
    )

    for name, record in certificates.items():
        assert record["status"] == (
            "PASS_CORRECTED_FINITE_PASS_DYNAMIC_CERTIFICATE"
        ), name
        assert all(record["checks"].values()), name

    for controller in [
        "online_predictive_robust_1db",
        "online_predictive_robust_1db_two_drops",
        "online_predictive_robust_3db",
    ]:
        assert action_arrays[f"{controller}_command_db"].shape == (118, 57, 2)
        assert action_arrays[f"{controller}_applied_db"].shape == (118, 57, 2)
        assert action_arrays[f"{controller}_moving_average_rate"].shape == (118, 228)

    alpha_expected = 1.0 - math.exp(
        -float(cfg["update_interval_s"])
        / float(cfg["moving_average"]["time_constant_s"])
    )
    assert abs(audit["moving_average"]["alpha"] - alpha_expected) <= 1e-15

    theorem = (ROOT / "docs/DELAYED_REACHABILITY_SAFETY_THEOREM.md").read_text(
        encoding="utf-8"
    )
    assert "F_i(q)=\\min(q_i+\\rho,Q)" in theorem
    assert "actual clipped candidate" in theorem
    assert "all-\\(Q\\)" not in theorem

    decision = {
        "status": "PASS_ONLINE_MOVING_AVERAGE_PF_LOAD_TRANSITION_ONE_SEED",
        "paper_result": False,
        "online_predictive_1db_safe": True,
        "online_predictive_3db_safe": True,
        "two_message_drop_fail_safe_safe": True,
        "active_user_floor_violations": 0,
        "online_pf_exceeds_frozen_pf": True,
        "theorem_saturation_statement_repaired": True,
        "next_gate": cfg["next_gate"],
    }
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "ONLINE_PF_LOAD_TRANSITION_GATE_DECISION.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("ONLINE PF LOAD-TRANSITION STRICT VALIDATION: PASS")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
