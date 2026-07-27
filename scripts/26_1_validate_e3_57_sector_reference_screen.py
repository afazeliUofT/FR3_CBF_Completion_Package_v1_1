#!/usr/bin/env python3
"""Strict validation for the 57-sector reference feasibility screen."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/e3_57_sector_reference_screen.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["outputs"]["work_dir"]
    expected = cfg["expected"]

    static = pd.read_csv(work / "sector_static_reference_accounting.csv")
    es = pd.read_csv(work / "earth_station_site_gain_timeseries.csv.gz")
    aggregate = pd.read_csv(work / "network_aggregate_reference_timeseries.csv.gz")
    scenario = pd.read_csv(work / "network_reference_scenario_summary.csv")
    peaks = pd.read_csv(work / "peak_top_sector_contributions.csv")
    mechanism = json.loads(
        (work / "P452_MECHANISM_FACTORISATION_DECISION.json").read_text(encoding="utf-8")
    )
    decision = json.loads(
        (work / "E3_57_SECTOR_REFERENCE_SCREEN_DECISION.json").read_text(encoding="utf-8")
    )

    assert mechanism["external_direct_gain_factorization_supported"]
    assert len(static) == int(expected["expected_static_sector_rows"])
    assert static["sector_id"].nunique() == int(expected["sector_count"])
    assert static["site_id"].nunique() == int(expected["site_count"])
    assert len(es) == int(expected["expected_es_gain_rows"])
    assert es["time_s"].nunique() == int(expected["protected_sample_count"])
    assert len(aggregate) == int(expected["expected_aggregate_rows"])
    assert len(scenario) == 84
    assert decision["aggregate_row_count"] == len(aggregate)

    required_short = np.maximum(
        0.0,
        aggregate["aggregate_interference_dbw_per_10mhz"].to_numpy(float)
        - aggregate["short_threshold_dbw_per_10mhz"].to_numpy(float),
    )
    required_long = np.maximum(
        0.0,
        aggregate["aggregate_interference_dbw_per_10mhz"].to_numpy(float)
        - aggregate["long_threshold_dbw_per_10mhz"].to_numpy(float),
    )
    assert np.allclose(
        required_short,
        aggregate["required_short_backoff_db"],
        atol=1e-10,
        rtol=0,
    )
    assert np.allclose(
        required_long,
        aggregate["required_long_backoff_db"],
        atol=1e-10,
        rtol=0,
    )
    assert np.allclose(
        aggregate["maximum_common_scale_for_short"],
        10.0 ** (-required_short / 10.0),
        atol=1e-14,
        rtol=1e-10,
    )
    assert np.allclose(
        aggregate["maximum_common_scale_for_long"],
        10.0 ** (-required_long / 10.0),
        atol=1e-14,
        rtol=1e-10,
    )

    group_cols = [
        "p452_time_percentage",
        "polarization_label",
        "bs_gain_case",
        "earth_station_pattern_type",
    ]
    rebuilt = (
        aggregate.groupby(group_cols, as_index=False)
        .agg(
            maximum_aggregate_interference_dbw_per_10mhz=(
                "aggregate_interference_dbw_per_10mhz",
                "max",
            ),
            minimum_aggregate_interference_dbw_per_10mhz=(
                "aggregate_interference_dbw_per_10mhz",
                "min",
            ),
            mean_aggregate_interference_dbw_per_10mhz=(
                "aggregate_interference_dbw_per_10mhz",
                "mean",
            ),
            long_exceedance_fraction=("long_exceeded", "mean"),
            short_exceedance_fraction=("short_exceeded", "mean"),
            maximum_required_long_backoff_db=("required_long_backoff_db", "max"),
            maximum_required_short_backoff_db=("required_short_backoff_db", "max"),
            median_required_long_backoff_db=("required_long_backoff_db", "median"),
            median_required_short_backoff_db=("required_short_backoff_db", "median"),
        )
        .sort_values(group_cols)
        .reset_index(drop=True)
    )
    stored = scenario.sort_values(group_cols).reset_index(drop=True)
    assert list(rebuilt[group_cols].itertuples(index=False, name=None)) == list(
        stored[group_cols].itertuples(index=False, name=None)
    )
    numeric = [c for c in rebuilt.columns if c not in group_cols]
    max_summary_error = float(
        np.abs(rebuilt[numeric].to_numpy(float) - stored[numeric].to_numpy(float)).max()
    )
    assert max_summary_error < 1e-9

    scenario_count = 7 * 2 * 3 * 2
    assert peaks.groupby(
        ["p452_time_percentage", "polarization_label", "bs_gain_case", "earth_station_pattern_type"]
    ).ngroups == scenario_count
    assert peaks["rank"].between(1, int(cfg["review"]["top_sector_count_per_scenario"])).all()
    assert peaks["fraction_of_aggregate_power"].between(0, 1).all()

    validation = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"]["sector_screen"],
        "sector_count": int(expected["sector_count"]),
        "site_count": int(expected["site_count"]),
        "protected_sample_count": int(expected["protected_sample_count"]),
        "aggregate_row_count": len(aggregate),
        "scenario_count": len(scenario),
        "maximum_scenario_reaggregation_error": max_summary_error,
        "mechanism_factorization_supported": True,
        "required_backoff_identity_verified": True,
        "common_scale_identity_verified": True,
        "review_required": True,
        "next_gate": cfg["review"]["next_gate"],
    }
    write_json(work / "E3_57_SECTOR_REFERENCE_SCREEN_VALIDATION.json", validation)
    (work / "E3_57_SECTOR_REFERENCE_SCREEN_VALIDATION.md").write_text(
        "# E3 57-sector reference-screen validation\n\n"
        f"- Status: `{validation['status']}`\n"
        f"- Sectors: `{validation['sector_count']}`\n"
        f"- Aggregate rows: `{validation['aggregate_row_count']}`\n"
        f"- Scenarios: `{validation['scenario_count']}`\n"
        f"- Maximum reaggregation error: "
        f"`{validation['maximum_scenario_reaggregation_error']:.3e}`\n"
        f"- Next gate: `{validation['next_gate']}`\n\n"
        "This remains a reference feasibility screen, not the final composite-"
        "beam, dynamic-controller, paper, or compliance result.\n",
        encoding="utf-8",
    )

    print("E3 57-SECTOR REFERENCE FEASIBILITY SCREEN VALIDATION: PASS")
    print(json.dumps(validation, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
