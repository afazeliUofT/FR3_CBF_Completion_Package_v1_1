#!/usr/bin/env python3
"""Strict validation of the local full-topology evidence freeze."""
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
        default="config/full_topology_ingest_v4.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    evidence = ROOT / cfg["paths"]["evidence_dir"]

    gate = json.loads(
        (evidence / "FULL_TOPOLOGY_GATE_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    metrics = json.loads(
        (
            evidence / "FULL_TOPOLOGY_SCIENTIFIC_METRICS.json"
        ).read_text(encoding="utf-8")
    )
    validation = json.loads(
        (
            evidence / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json"
        ).read_text(encoding="utf-8")
    )
    dynamic = pd.read_csv(
        evidence / "DYNAMIC_RATE_LIMIT_GEOMETRY_SCREEN.csv"
    )

    assert gate["status"] == (
        "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_ONE_SEED"
    )
    assert gate["paper_result"] is False
    assert gate["full_228_user_topology_validated"] is True
    assert validation["status"] == (
        "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
    )
    assert validation["failures"] == []
    assert metrics["legacy_reproduction"]["pass"] is True
    assert (
        metrics["full_vs_chunked"][
            "per_user_nominal_rate_correlation"
        ]
        < 0.5
    )
    assert (
        metrics["common_scale_reference"][
            "total_band_network_retention_quantiles"
        ]["minimum"]
        > 0.99
    )
    assert (
        metrics["common_scale_reference"][
            "protected_band_network_retention_quantiles"
        ]["minimum"]
        < 0.95
    )
    assert (
        metrics["dynamic_geometry_screen"]["status"]
        == "PASS_NATURAL_RATE_LIMIT_TRAP_EXISTS"
    )
    assert (dynamic["myopic_violation_samples"] > 0).any()
    assert (
        dynamic.loc[
            dynamic["myopic_violation_samples"] > 0,
            "perfect_lookahead_violation_samples",
        ]
        == 0
    ).all()
    assert (
        metrics["static_nonuniform_opportunity_screen"][
            "screen_total_band_retention_quantiles"
        ]["minimum"]
        > metrics["static_nonuniform_opportunity_screen"][
            "common_total_band_retention_quantiles"
        ]["minimum"]
    )

    print("VALIDATED FULL-TOPOLOGY INGESTION STRICT CHECK: PASS")
    print(
        json.dumps(
            {
                "status": gate["status"],
                "paper_result": False,
                "dynamic_controller_proven": False,
                "next_gate": cfg["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
