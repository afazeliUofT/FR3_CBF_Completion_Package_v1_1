#!/usr/bin/env python3
"""Strict validation of the generic practical architecture mapping."""
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
        default="config/practical_architecture_mapping_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    audit = json.loads(
        (results / "PRACTICAL_ARCHITECTURE_MAPPING_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    gate = json.loads(
        (evidence / "ARCHITECTURE_GATE_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    table = pd.read_csv(results / "ARCHITECTURE_CASE_SUMMARY.csv").set_index(
        "architecture_id"
    )

    assert audit["status"] == (
        "PASS_PRACTICAL_ARCHITECTURE_MAPPING_REVIEW_REQUIRED"
    )
    assert gate["status"] == (
        "PASS_GENERIC_64T64R_ARCHITECTURE_MAPPING_ONE_SEED"
    )
    assert gate["campaign_execution_authorized"] is False
    assert gate["product_mapping"] is False
    assert gate["measured_calibration"] is False

    primary = table.loc["generic_64t64r_subarray_6bit"]
    upper = table.loc["ideal_128fd"]
    phase_8bit = table.loc["generic_64t64r_subarray_8bit"]
    hybrid = table.loc["generic_32t32r_subarray_6bit"]

    assert bool(primary.phase1_primary_acceptance)
    assert primary.controller_evaluated
    assert primary.hard_safety_violation_seconds == 0
    assert primary.eligible_floor_violation_user_intervals == 0
    assert primary.nominal_sum_rate_retention_vs_128 >= 0.97
    assert primary.minimum_available_digital_nullspace_dimension >= 58
    assert primary.common_ideal_eligible_user_nominal_outage_count == 0
    assert primary.local_channel_rank_failure_count == 0

    assert upper.controller_evaluated
    assert upper.hard_safety_violation_seconds == 0
    assert upper.eligible_floor_violation_user_intervals == 0
    assert abs(upper.nominal_sum_rate_retention_vs_128 - 1.0) < 5e-6

    assert not phase_8bit.controller_evaluated
    assert phase_8bit.nominal_sum_rate_retention_vs_128 >= 0.97
    assert phase_8bit.common_ideal_eligible_user_nominal_outage_count == 0

    assert not hybrid.controller_evaluated
    assert not bool(hybrid.phase1_primary_acceptance)
    assert (
        hybrid.nominal_sum_rate_retention_vs_128 < 0.97
        or hybrid.common_ideal_eligible_user_nominal_outage_count > 0
    )

    print("PRACTICAL ARCHITECTURE MAPPING STRICT VALIDATION: PASS")
    print(json.dumps(gate, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
