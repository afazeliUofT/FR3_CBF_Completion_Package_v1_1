#!/usr/bin/env python3
"""Independent structural and numerical validator for the full-topology export."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    required = [
        "FULL_TOPOLOGY_EXPORT_AUDIT.json",
        "FULL_TOPOLOGY_EXPORT_ENVIRONMENT.json",
        "FULL_VS_CHUNKED_COMPARISON.json",
        "OUTPUT_ARRAY_MANIFEST.json",
        "USER_TOPOLOGY.csv",
        "SECTOR_TOPOLOGY.csv",
    ]
    for name in required:
        if not (OUTPUT / name).is_file():
            raise FileNotFoundError(OUTPUT / name)

    audit = json.loads((OUTPUT / "FULL_TOPOLOGY_EXPORT_AUDIT.json").read_text(encoding="utf-8"))
    manifest = json.loads((OUTPUT / "OUTPUT_ARRAY_MANIFEST.json").read_text(encoding="utf-8"))
    comparison = json.loads((OUTPUT / "FULL_VS_CHUNKED_COMPARISON.json").read_text(encoding="utf-8"))
    if audit["status"] != "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_REVIEW_REQUIRED":
        raise ValueError("Export audit did not pass")
    if not comparison["legacy_numeric_reproduction"]["pass"]:
        raise ValueError("Legacy chunked platform was not numerically reproduced")
    if audit["full_topology"]["mode"] != "one_topology_call_all_228_users":
        raise ValueError("Hidden topology fallback detected")
    if audit["full_topology"]["coefficient_shape"][1] != 228:
        raise ValueError("Full topology did not contain all 228 users")

    arrays = {}
    for name, record in manifest["arrays"].items():
        path = OUTPUT / name
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"Array hash mismatch: {name}")
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if list(value.shape) != record["shape"] or str(value.dtype) != record["dtype"]:
            raise ValueError(f"Array metadata mismatch: {name}")
        if not np.all(np.isfinite(value)):
            raise ValueError(f"Array contains non-finite values: {name}")
        arrays[name] = value

    expected_shapes = {
        "frequency_response.npy": (9, 228, 57, 128),
        "nominal_precoder_by_frequency.npy": (9, 57, 128, 4),
        "nominal_amplitude_by_frequency.npy": (9, 228, 57, 4),
        "protected_amp_perpendicular.npy": (228, 57, 4),
        "protected_amp_pol1.npy": (228, 57, 4),
        "protected_amp_pol2.npy": (228, 57, 4),
        "protected_steering_pol1.npy": (57, 128),
        "protected_steering_pol2.npy": (57, 128),
        "protected_mode_coefficients.npy": (57, 2, 4),
        "nominal_mode_leakage_w.npy": (57, 2),
        "kappa_time_sector.npy": (587, 57),
        "common_scale_user_rate.npy": (587, 228),
    }
    for name, shape in expected_shapes.items():
        if tuple(arrays[name].shape) != shape:
            raise ValueError(f"Unexpected shape for {name}: {arrays[name].shape}")

    weights = np.asarray(arrays["frequency_weights.npy"])
    noise = np.asarray(arrays["noise_power_by_frequency_w.npy"])
    serving = np.asarray(arrays["serving_bs_index.npy"], dtype=np.int64)
    stream = np.asarray(arrays["serving_stream_index.npy"], dtype=np.int64)
    amplitudes = np.asarray(arrays["nominal_amplitude_by_frequency.npy"])
    desired_expected = np.asarray(arrays["nominal_user_desired_power_by_frequency_w.npy"])
    interference_expected = np.asarray(arrays["nominal_user_interference_power_by_frequency_w.npy"])
    rate_expected = np.asarray(arrays["nominal_user_rate_by_frequency.npy"])

    if not np.isclose(weights.sum(), 1.0, rtol=0.0, atol=1e-14):
        raise ValueError("Frequency weights do not sum to one")
    power = np.abs(amplitudes) ** 2
    total = power.sum(axis=(2, 3))
    desired = power[:, np.arange(228), serving, stream]
    interference = total - desired
    sinr = desired / (interference + noise[:, None])
    rate = np.log2(1.0 + sinr)
    if np.max(np.abs(desired - desired_expected)) > 1e-7:
        raise ValueError("Desired-power reconstruction failed")
    if np.max(np.abs(interference - interference_expected)) > 1e-7:
        raise ValueError("Interference-power reconstruction failed")
    if np.max(np.abs(rate - rate_expected)) > 1e-8:
        raise ValueError("Rate reconstruction failed")

    total_rate = (weights[:, None] * rate).sum(axis=0)
    if np.max(np.abs(total_rate - arrays["nominal_total_weighted_rate_per_user.npy"])) > 1e-8:
        raise ValueError("Weighted total-rate reconstruction failed")

    protected = 4
    reconstructed = (
        arrays["protected_amp_perpendicular.npy"]
        + arrays["protected_amp_pol1.npy"]
        + arrays["protected_amp_pol2.npy"]
    )
    if np.max(np.abs(reconstructed - amplitudes[protected])) > 2e-5:
        raise ValueError("Protected amplitude decomposition failed")

    coefficients = arrays["protected_mode_coefficients.npy"]
    leakage = np.sum(np.abs(coefficients) ** 2, axis=2)
    if np.max(np.abs(leakage - arrays["nominal_mode_leakage_w.npy"])) > 1e-6:
        raise ValueError("Mode leakage reconstruction failed")

    kappa = arrays["kappa_time_sector.npy"]
    nominal_aggregate = kappa @ leakage.sum(axis=1)
    if np.max(np.abs(nominal_aggregate - arrays["nominal_aggregate_interference_w.npy"])) > 1e-24:
        raise ValueError("Aggregate incumbent reconstruction failed")

    scale = arrays["common_scale_reference.npy"]
    allowance = arrays["aggregate_allowance_w.npy"]
    if np.any(nominal_aggregate * scale**2 > allowance * (1.0 + 3e-6) + 1e-30):
        raise ValueError("Common-scale reference violates allowance")

    users = pd.read_csv(OUTPUT / "USER_TOPOLOGY.csv")
    sectors = pd.read_csv(OUTPUT / "SECTOR_TOPOLOGY.csv")
    if len(users) != 228 or len(sectors) != 57:
        raise ValueError("Topology table row count mismatch")
    if not np.array_equal(
        np.bincount(serving, minlength=57),
        np.full(57, 4, dtype=np.int64),
    ):
        raise ValueError("Serving association is not four users per sector")

    validation = {
        "status": "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION",
        "full_topology_user_count": 228,
        "legacy_chunked_numeric_reproduction": True,
        "rate_reconstruction": True,
        "protected_decomposition_reconstruction": True,
        "mode_leakage_reconstruction": True,
        "aggregate_incumbent_reconstruction": True,
        "common_scale_safety": True,
        "next_gate": audit["next_gate"],
    }
    (OUTPUT / "FULL_TOPOLOGY_EXPORT_VALIDATION.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("CONTROLLER-READY FULL-TOPOLOGY EXPORT VALIDATION: PASS")
    print(json.dumps(validation, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
