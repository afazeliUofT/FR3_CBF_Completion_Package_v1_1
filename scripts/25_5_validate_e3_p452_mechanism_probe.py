#!/usr/bin/env python3
"""Validate the numerical P.452 troposcatter-isolation probe."""
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
    out = ROOT / cfg["outputs"]["work_dir"]
    probe = pd.read_csv(out / "p452_troposcatter_suppressed_probe.csv")
    audit = json.loads(
        (out / "P452_MECHANISM_PROBE_MATLAB_AUDIT.json").read_text(encoding="utf-8")
    )

    expected_rows = int(cfg["expected"]["p452_row_count"])
    assert audit["status"] == "PASS"
    assert audit["matlab_release"] == str(cfg["expected"]["matlab_release"])
    assert audit["p452_reference_commit"] == str(
        cfg["expected"]["p452_reference_commit"]
    )
    assert len(probe) == expected_rows
    key = ["site_id", "coast_distance_km", "polarization_code", "time_percentage"]
    assert not probe.duplicated(key).any()

    delta = probe["troposcatter_contribution_delta_db"].to_numpy(float)
    tolerance = float(cfg["mechanism_probe"]["tolerance_db"])
    if float(delta.min()) < -tolerance:
        raise ValueError("Mechanism probe produced a negative contribution delta")

    threshold = float(
        cfg["mechanism_probe"]["maximum_allowed_troposcatter_contribution_db"]
    )
    max_delta = float(delta.max())
    supported = max_delta <= threshold

    summary = (
        probe.groupby("site_id", as_index=False)
        .agg(
            maximum_troposcatter_contribution_delta_db=(
                "troposcatter_contribution_delta_db",
                "max",
            ),
            median_troposcatter_contribution_delta_db=(
                "troposcatter_contribution_delta_db",
                "median",
            ),
        )
        .sort_values(
            "maximum_troposcatter_contribution_delta_db", ascending=False
        )
    )
    summary.to_csv(out / "p452_mechanism_probe_site_summary.csv", index=False)

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_EXTERNAL_DIRECT_GAIN_FACTORIZATION_SUPPORTED"
            if supported
            else "REPAIR_REQUIRED_MECHANISM_SPECIFIC_GAIN_MODEL"
        ),
        "claim_boundary": cfg["claim_boundary"]["mechanism"],
        "row_count": len(probe),
        "maximum_troposcatter_contribution_delta_db": max_delta,
        "allowed_maximum_delta_db": threshold,
        "external_direct_gain_factorization_supported": supported,
        "interpretation": (
            "The probe numerically suppresses the P.452 troposcatter branch by "
            "using a very large horizon-gain coupling-loss input. It is an "
            "audit device, not a physical antenna scenario."
        ),
        "next_gate": (
            cfg["mechanism_probe"]["next_gate_if_passed"]
            if supported
            else cfg["mechanism_probe"]["next_gate_if_failed"]
        ),
    }
    write_json(out / "P452_MECHANISM_FACTORISATION_DECISION.json", decision)
    (out / "P452_MECHANISM_FACTORISATION_DECISION.md").write_text(
        "# P.452 mechanism-factorization decision\n\n"
        f"- Status: `{decision['status']}`\n"
        f"- Rows: `{len(probe)}`\n"
        f"- Maximum troposcatter contribution: `{max_delta:.9f}` dB\n"
        f"- Acceptance threshold: `{threshold:.9f}` dB\n"
        f"- Next gate: `{decision['next_gate']}`\n\n"
        "The +100 dBi horizon-gain inputs are a numerical mechanism-isolation "
        "probe, not a physical antenna case.\n",
        encoding="utf-8",
    )

    print("E3 P.452 MECHANISM-ISOLATION VALIDATION: PASS")
    print(json.dumps(decision, indent=2))
    print("\nSITE SUMMARY")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
