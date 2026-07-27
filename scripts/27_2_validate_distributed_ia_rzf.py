#!/usr/bin/env python3
"""Strict validator for the distributed IA-RZF architecture prototype."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from _bootstrap import ROOT


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/distributed_ia_rzf_architecture.yaml"
    )
    args = parser.parse_args()
    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["outputs"]["work_dir"]
    expected = cfg["expected"]

    architecture = json.loads(
        (work / "DISTRIBUTED_IA_RZF_ARCHITECTURE_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    audit = json.loads(
        (work / "DISTRIBUTED_IA_RZF_PROTOTYPE_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    static = pd.read_csv(work / "prototype_static_sector_models.csv")
    metrics = pd.read_csv(work / "prototype_sector_time_metrics.csv.gz")
    summary = pd.read_csv(work / "prototype_time_summary.csv")

    assert architecture["wmmse_disposition"]["main_operational_method"] == "REMOVED"
    assert architecture["aggregate_certificate"]["requires_inter_bs_ue_csi"] is False
    assert architecture["aggregate_certificate"]["requires_joint_beam_computation"] is False
    assert audit["status"] == "PASS_PROTOTYPE_ONLY"
    assert static["sector_id"].nunique() == int(expected["sector_count"])
    assert len(summary) == int(expected["protected_sample_count"])
    assert len(metrics) == int(expected["sector_count"]) * int(
        expected["protected_sample_count"]
    )
    assert metrics["local_budget_satisfied"].all()
    assert summary["local_budget_violation_count"].eq(0).all()

    budget_sums = metrics.groupby("time_s")["local_budget_w"].sum().sort_index()
    safe_sums = (
        metrics.groupby("time_s")["safe_received_interference_w"].sum().sort_index()
    )
    nominal_sums = (
        metrics.groupby("time_s")["nominal_received_interference_w"].sum().sort_index()
    )
    stored = summary.set_index("time_s").sort_index()
    assert np.allclose(
        budget_sums.to_numpy(float),
        stored["budget_sum_w"].to_numpy(float),
        rtol=1e-10,
        atol=1e-30,
    )
    assert np.allclose(
        safe_sums.to_numpy(float),
        stored["aggregate_safe_interference_w"].to_numpy(float),
        rtol=1e-10,
        atol=1e-30,
    )
    assert np.allclose(
        nominal_sums.to_numpy(float),
        stored["aggregate_nominal_interference_w"].to_numpy(float),
        rtol=1e-10,
        atol=1e-30,
    )
    assert (
        stored["aggregate_safe_interference_w"]
        <= stored["aggregate_allowance_w"] * (1.0 + 1e-9) + 1e-30
    ).all()
    assert (
        metrics["precoder_power_after_w"]
        <= metrics["precoder_power_before_w"] + 1e-10
    ).all()
    assert metrics["projection_scale"].between(0.0, 1.0).all()
    assert np.isfinite(metrics["safe_local_sum_rate_bps_hz"]).all()
    assert (metrics["safe_local_sum_rate_bps_hz"] >= 0).all()

    validation = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_ARCHITECTURE_AND_SOFTWARE_PROTOTYPE_ONLY",
        "claim_boundary": cfg["claim_boundary"]["prototype"],
        "sector_count": int(expected["sector_count"]),
        "protected_sample_count": int(expected["protected_sample_count"]),
        "local_budget_constraints_verified": True,
        "aggregate_budget_sum_verified": True,
        "aggregate_interference_certificate_verified": True,
        "transmit_power_nonincrease_verified": True,
        "central_instantaneous_ue_csi_used": False,
        "joint_network_beamformer_used": False,
        "minimum_rate_retention_fraction": float(
            stored["rate_retention_fraction"].min()
        ),
        "maximum_budget_sum_error_w": float(
            np.abs(
                budget_sums.to_numpy(float)
                - stored["aggregate_allowance_w"].to_numpy(float)
            ).max()
        ),
        "next_gate": cfg["next_gate"]["name"],
    }
    write_json(work / "DISTRIBUTED_IA_RZF_VALIDATION.json", validation)
    (work / "DISTRIBUTED_IA_RZF_VALIDATION.md").write_text(
        "# Distributed IA-RZF prototype validation\n\n"
        f"- Status: `{validation['status']}`\n"
        f"- Sectors: `{validation['sector_count']}`\n"
        f"- Protected samples: `{validation['protected_sample_count']}`\n"
        "- Local budgets: verified\n"
        "- Aggregate budget sum: verified\n"
        "- Aggregate interference certificate: verified\n"
        "- Transmit-power nonincrease: verified\n"
        "- Central instantaneous UE CSI: not used\n"
        "- Joint network beamformer: not used\n\n"
        "This remains a deterministic synthetic local-channel software audit. "
        "It is not the standards-aligned paper experiment.\n",
        encoding="utf-8",
    )

    print("DISTRIBUTED IA-RZF STRICT VALIDATION: PASS")
    print(json.dumps(validation, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
