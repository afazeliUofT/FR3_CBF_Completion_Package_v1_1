#!/usr/bin/env python3
"""Strict validation of the deterministic physical-impairment audit."""
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
        default="config/physical_impairment_sensitivity_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    audit = json.loads(
        (results / "PHYSICAL_IMPAIRMENT_SENSITIVITY_AUDIT.json").read_text(encoding="utf-8")
    )
    gate = json.loads(
        (evidence / "PHYSICAL_IMPAIRMENT_GATE_DECISION.json").read_text(encoding="utf-8")
    )
    cap = pd.read_csv(results / "NULL_DEPTH_CAP_AND_BACKOFF_SWEEP.csv")
    stress = pd.read_csv(results / "ARRAY_STEERING_QUANTIZATION_STRESS.csv")

    assert audit["status"] == "PASS_PHYSICAL_IMPAIRMENT_SENSITIVITY_AUDIT_CALIBRATION_REQUIRED"
    assert gate["status"] == "PASS_DETERMINISTIC_PHYSICAL_IMPAIRMENT_SENSITIVITY_CALIBRATION_DATA_REQUIRED"
    assert gate["paper_result"] is False
    assert gate["physical_null_depth_calibrated"] is False
    assert gate["campaign_execution_authorized"] is False
    assert len(cap) == 24
    assert set(cap["case"]) == {"long_multiple", "long_single"}
    long_single = cap.loc[cap["case"] == "long_single"].set_index("null_depth_cap_db")
    assert long_single.loc[60.0, "uncorrected_violation_seconds"] > 0
    assert long_single.loc[60.0, "minimum_uniform_protected_tone_backoff_db"] > 3.0
    assert long_single.loc[70.0, "uncorrected_violation_seconds"] == 0
    assert long_single.loc[70.0, "minimum_uniform_protected_tone_backoff_db"] < 1e-6
    assert (stress.loc[stress["stress_family"] != "phase_quantization_bits", "trials"] == 8).all()
    assert (stress["violation_seconds_p95"] > 0).any()
    campaign = json.loads((ROOT / "config/phased_campaign_spec_v2.json").read_text(encoding="utf-8"))
    assert campaign["execution_authorized"] is False
    assert campaign["phase_1_paired_primary"]["channel_topology_seeds"] == 30
    assert campaign["phase_2_factor_sensitivities"]["paired_subset_seeds"] == 10

    print("PHYSICAL IMPAIRMENT SENSITIVITY STRICT VALIDATION: PASS")
    print(json.dumps({
        "status": gate["status"],
        "long_single_cap60_backoff_db": float(long_single.loc[60.0, "minimum_uniform_protected_tone_backoff_db"]),
        "long_single_cap70_safe": True,
        "campaign_execution_authorized": False,
        "next_gate": cfg["next_gate"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
