#!/usr/bin/env python3
"""Reproduce the immutable seed-43999 normalized diagnostic facts locally."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

PRED = "robust_predictive_constrained_pf_with_sector_selective_fallback"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--handoff-state", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(args.evidence_root).resolve()
    state = json.loads(Path(args.handoff_state).read_text(encoding="utf-8"))
    normalized = json.loads(
        (root / "PREDICTIVE_FLOOR_DIAGNOSTIC_NORMALIZED.json").read_text(
            encoding="utf-8"
        )
    )
    cells = pd.read_csv(root / "ALL_METHOD_CELL_SUMMARY.csv")
    passes = pd.read_csv(root / "PREDICTIVE_FLOOR_PASS_SUMMARY.csv")
    users = pd.read_csv(root / "PREDICTIVE_FLOOR_VIOLATING_USERS.csv")
    intervals = pd.read_csv(root / "PREDICTIVE_FLOOR_VIOLATING_INTERVALS.csv")

    assert state["campaign"]["execution_authorized"] is False
    assert state["frozen_primary"]["floor_rule"] == (
        "max(0.1, 0.9 * current_load_nominal_total_rate)"
    )
    assert state["frozen_primary"]["null_depth_cap_db"] == 65.0
    assert state["frozen_primary"]["coupling_uplift_db"] == 3.0
    assert normalized["diagnostic_seed"] == 43999
    assert normalized["confirmatory_campaign_authorized"] is False
    assert normalized["pass_count"] == 5
    assert normalized["method_count"] == 8
    assert normalized["eligible_user_count"] == 205

    pred = cells.loc[cells.method_id == PRED]
    assert len(pred) == 5
    assert int(pred.long_violation_seconds.sum()) == 0
    assert int(pred.short_violation_seconds.sum()) == 0
    assert int(pred.eligible_floor_violation_user_intervals.sum()) == 104
    assert int(pred.eligible_floor_violation_user_seconds.sum()) == 519
    assert int(passes.floor_violation_user_intervals.sum()) == 104
    assert int(passes.floor_violation_user_seconds.sum()) == 519
    assert int(intervals.violating_user_count.sum()) == 104

    grouped = users.groupby("user_id", sort=True)["violation_user_seconds"].sum()
    assert grouped.to_dict() == {
        "E3_SITE_02_SEC_3_UE_4": 500,
        "E3_SITE_07_SEC_1_UE_2": 19,
    }
    minimum = float(users.minimum_floor_ratio.min())
    maximum_shortfall = float(users.maximum_normalized_shortfall.max())
    assert np.isclose(minimum, 0.810696983385736, rtol=0.0, atol=1e-15)
    assert np.isclose(
        maximum_shortfall, 0.18930301661426396, rtol=0.0, atol=1e-15
    )
    assert normalized["overall_floor_violation_classification"] == "MATERIAL"

    report = {
        "status": "PASS_PACKAGED_SEED43999_DIAGNOSTIC_AUDIT",
        "floor_definition_audit": "PASS",
        "variable_pass_extension_audit": "PASS",
        "all_eight_methods_audit": "PASS",
        "predictive_long_violation_seconds": 0,
        "predictive_short_violation_seconds": 0,
        "predictive_floor_violation_user_intervals": 104,
        "predictive_floor_violation_user_seconds": 519,
        "minimum_floor_ratio": minimum,
        "maximum_normalized_shortfall": maximum_shortfall,
        "affected_physical_users": grouped.to_dict(),
        "classification": "MATERIAL",
        "confirmatory_campaign_authorized": False,
        "next_gate": "CPU_ONLY_RORQUAL_EXACT_SEED43999_FEASIBILITY_DIAGNOSTIC",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("PACKAGED_FLOOR_DEFINITION_AUDIT=PASS")
    print("PACKAGED_VARIABLE_PASS_EXTENSION_AUDIT=PASS")
    print("PACKAGED_ALL_EIGHT_METHOD_AGGREGATE_AUDIT=PASS")
    print("PACKAGED_SEED43999_MATERIAL_FAILURE_REPRODUCED=PASS")
    print("CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO")
    print("NEXT_GATE=CPU_ONLY_RORQUAL_EXACT_SEED43999_FEASIBILITY_DIAGNOSTIC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
