#!/usr/bin/env python3
"""Independent structural and accounting validation for the Narval pilot."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"


def main() -> int:
    required = [
        OUTPUT / "NARVAL_GPU_ENVIRONMENT.json",
        OUTPUT / "NARVAL_ONE_SEED_DLP_RZF_PILOT_AUDIT.json",
        OUTPUT / "PILOT_TIME_SUMMARY.csv",
        OUTPUT / "PILOT_SECTOR_TIME_METRICS.csv.gz",
        OUTPUT / "PILOT_USER_RATE_SUMMARY.csv",
        OUTPUT / "PILOT_NUMERICAL_EVIDENCE.npz",
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    audit = json.loads((OUTPUT / "NARVAL_ONE_SEED_DLP_RZF_PILOT_AUDIT.json").read_text(encoding="utf-8"))
    env = json.loads((OUTPUT / "NARVAL_GPU_ENVIRONMENT.json").read_text(encoding="utf-8"))
    time = pd.read_csv(OUTPUT / "PILOT_TIME_SUMMARY.csv")
    sector = pd.read_csv(OUTPUT / "PILOT_SECTOR_TIME_METRICS.csv.gz")
    users = pd.read_csv(OUTPUT / "PILOT_USER_RATE_SUMMARY.csv")
    with np.load(OUTPUT / "PILOT_NUMERICAL_EVIDENCE.npz", allow_pickle=False) as data:
        safe_rates = data["safe_rate_matrix"]
        nominal = data["nominal_rate_per_user"]
        aggregate_safe = data["aggregate_safe_w"]
        allowance = data["aggregate_allowance_w"]

    assert audit["status"] == "PASS_ONE_SEED_GPU_DLP_RZF_PILOT_REVIEW_REQUIRED"
    gates = audit["standards_and_port_gates"]
    assert gates["incumbent_local_frame_status"] == (
        "PASS_EXACT_SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT"
    )
    assert gates["incumbent_steering_coordinate_model"] == (
        "exact_world_to_local_rotation_Rz_alpha_Ry_beta_Rx_gamma"
    )
    assert gates["transmit_polarization_bound"] == (
        "conservative_sum_of_two_orthogonal_sionna_port_group_spatial_mode_powers"
    )
    assert gates["steering_vector_convention"].startswith(
        "a=exp(-j k r_local dot d_local)"
    )
    assert "A100" in env["gpu_name"]
    assert len(time) == 587
    assert len(sector) == 587 * 57
    assert len(users) == 228
    assert safe_rates.shape == (587, 228)
    assert nominal.shape == (228,)
    assert np.all(np.isfinite(safe_rates)) and np.all(safe_rates >= 0)
    assert np.all(aggregate_safe <= allowance * (1.0 + 3e-6) + 1e-30)
    assert sector["budget_satisfied"].all()
    assert time["local_violation_count"].eq(0).all()
    assert np.allclose(
        sector.groupby("time_s")["safe_received_w"].sum().to_numpy(),
        time["aggregate_safe_interference_w"].to_numpy(),
        rtol=2e-6,
        atol=1e-30,
    )
    assert np.allclose(
        sector.groupby("time_s")["budget_w"].sum().to_numpy(),
        time["budget_sum_w"].to_numpy(),
        rtol=2e-6,
        atol=1e-30,
    )
    assert np.allclose(
        safe_rates.sum(axis=1),
        time["network_safe_sum_se_bps_hz"].to_numpy(),
        rtol=2e-6,
        atol=1e-8,
    )
    print("NARVAL ONE-SEED DLP-RZF PILOT VALIDATION: PASS")
    print("GPU:", env["gpu_name"])
    print("Rows:", len(sector))
    print("Minimum rate retention:", time["rate_retention_fraction"].min())
    print("Maximum safe-minus-allowance:", (aggregate_safe - allowance).max())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
