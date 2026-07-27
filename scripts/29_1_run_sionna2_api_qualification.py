#!/usr/bin/env python3
"""Run a small deterministic Sionna 2.0.1 UMa/UMi API qualification on CPU."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]


def tensor_digest(tensor: torch.Tensor) -> str:
    value = tensor.detach().cpu().contiguous().numpy()
    return hashlib.sha256(value.tobytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reset_seed(seed: int) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
    try:
        from sionna.phy import config as sionna_config

        sionna_config.seed = seed
    except Exception:
        pass


def generate_scenario(
    name: str,
    parameters: dict[str, object],
    common: dict[str, object],
    seed: int,
) -> tuple[dict[str, object], torch.Tensor, torch.Tensor]:
    from sionna.phy.channel.tr38901 import PanelArray, UMa, UMi
    from sionna.sys import gen_hexgrid_topology

    reset_seed(seed)
    device = "cpu"
    carrier = float(common["carrier_frequency_hz"])

    bs_array = PanelArray(
        num_rows_per_panel=int(common["pilot_bs_array_rows"]),
        num_cols_per_panel=int(common["pilot_bs_array_cols"]),
        polarization=str(common["pilot_bs_array_polarization"]),
        polarization_type=str(common["pilot_bs_array_polarization_type"]),
        antenna_pattern="38.901",
        carrier_frequency=carrier,
        precision="single",
        device=device,
    )
    ut_array = PanelArray(
        num_rows_per_panel=1,
        num_cols_per_panel=1,
        polarization="single",
        polarization_type="V",
        antenna_pattern="omni",
        carrier_frequency=carrier,
        precision="single",
        device=device,
    )
    model_class = UMa if name == "uma" else UMi
    model = model_class(
        carrier_frequency=carrier,
        o2i_model="low",
        ut_array=ut_array,
        bs_array=bs_array,
        direction="downlink",
        enable_pathloss=True,
        enable_shadow_fading=True,
        always_generate_lsp=False,
        precision="single",
        device=device,
    )

    topology = gen_hexgrid_topology(
        batch_size=1,
        num_rings=int(common["pilot_num_rings"]),
        num_ut_per_sector=int(common["pilot_users_per_sector"]),
        scenario=name,
        min_bs_ut_dist=float(parameters["minimum_bs_ut_distance_m"]),
        isd=float(parameters["isd_m"]),
        bs_height=float(parameters["bs_height_m"]),
        min_ut_height=float(parameters["ut_height_m"]),
        max_ut_height=float(parameters["ut_height_m"]),
        indoor_probability=float(parameters["indoor_probability"]),
        min_ut_velocity=0.0,
        max_ut_velocity=0.0,
        return_grid=False,
        precision="single",
        device=device,
    )
    model.set_topology(*topology)
    coefficients, delays = model(
        num_time_samples=1,
        sampling_frequency=15_000.0,
    )

    ut_loc, bs_loc, ut_orientations, bs_orientations, ut_velocities, in_state, los, bs_virtual_loc = topology
    expected_bs = int(common["pilot_bs_sectors"])
    expected_ut = int(common["pilot_users"])
    if tuple(ut_loc.shape) != (1, expected_ut, 3):
        raise ValueError(f"{name}: unexpected UT topology shape {tuple(ut_loc.shape)}")
    if tuple(bs_loc.shape) != (1, expected_bs, 3):
        raise ValueError(f"{name}: unexpected BS topology shape {tuple(bs_loc.shape)}")
    if coefficients.ndim != 7 or delays.ndim != 4:
        raise ValueError(
            f"{name}: unexpected channel ranks {coefficients.ndim}, {delays.ndim}"
        )
    if coefficients.shape[0] != 1:
        raise ValueError(f"{name}: unexpected batch dimension")
    if coefficients.shape[1] != expected_ut or coefficients.shape[3] != expected_bs:
        raise ValueError(f"{name}: channel link dimensions do not match topology")
    if coefficients.shape[2] != int(common["pilot_ut_antenna_count"]):
        raise ValueError(f"{name}: unexpected UT antenna count")
    if coefficients.shape[4] != int(common["pilot_bs_antenna_count"]):
        raise ValueError(f"{name}: unexpected BS antenna count")
    if coefficients.shape[-1] != 1 or coefficients.shape[5] <= 0:
        raise ValueError(f"{name}: invalid path/time dimensions")
    if not torch.isfinite(coefficients.real).all() or not torch.isfinite(
        coefficients.imag
    ).all():
        raise ValueError(f"{name}: channel coefficients contain non-finite values")
    if not torch.isfinite(delays).all():
        raise ValueError(f"{name}: delays contain non-finite values")

    path_energy = torch.sum(torch.abs(coefficients) ** 2, dim=(2, 4, 5, 6))
    valid_delays = delays[delays >= 0]
    summary = {
        "scenario": name,
        "carrier_frequency_hz": carrier,
        "topology_shapes": {
            "ut_loc": list(ut_loc.shape),
            "bs_loc": list(bs_loc.shape),
            "ut_orientations": list(ut_orientations.shape),
            "bs_orientations": list(bs_orientations.shape),
            "ut_velocities": list(ut_velocities.shape),
            "in_state": list(in_state.shape),
            "los": None if los is None else list(los.shape),
            "bs_virtual_loc": list(bs_virtual_loc.shape),
        },
        "channel_shapes": {
            "coefficients": list(coefficients.shape),
            "delays": list(delays.shape),
        },
        "array": {
            "bs_num_ant": int(bs_array.num_ant),
            "ut_num_ant": int(ut_array.num_ant),
        },
        "topology_statistics": {
            "bs_height_unique_m": sorted(
                {float(value) for value in bs_loc[0, :, 2].cpu().tolist()}
            ),
            "ut_height_unique_m": sorted(
                {float(value) for value in ut_loc[0, :, 2].cpu().tolist()}
            ),
            "indoor_fraction": float(in_state.float().mean().item()),
        },
        "channel_statistics": {
            "path_count": int(coefficients.shape[5]),
            "path_energy_min": float(path_energy.min().item()),
            "path_energy_median": float(path_energy.median().item()),
            "path_energy_max": float(path_energy.max().item()),
            "nonzero_path_energy_fraction": float(
                (path_energy > 0).float().mean().item()
            ),
            "valid_delay_count": int(valid_delays.numel()),
            "valid_delay_min_s": (
                None if valid_delays.numel() == 0 else float(valid_delays.min().item())
            ),
            "valid_delay_max_s": (
                None if valid_delays.numel() == 0 else float(valid_delays.max().item())
            ),
        },
        "fingerprints": {
            "coefficients_sha256": tensor_digest(coefficients),
            "delays_sha256": tensor_digest(delays),
            "ut_locations_sha256": tensor_digest(ut_loc),
            "bs_locations_sha256": tensor_digest(bs_loc),
        },
    }
    return summary, coefficients, delays


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/sionna2_channel_qualification.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    work = ROOT / cfg["environment"]["work_dir"]
    work.mkdir(parents=True, exist_ok=True)

    torch_version = importlib.metadata.version("torch")
    torch_base_version = torch_version.split("+", 1)[0]
    sionna_distribution_version = importlib.metadata.version(
        str(expected["sionna_distribution"])
    )
    if torch_base_version != str(expected["torch_version"]):
        raise ValueError(
            f"Expected torch base version {expected['torch_version']}, "
            f"found {torch_version}"
        )
    if sionna_distribution_version != str(expected["sionna_version"]):
        raise ValueError(
            f"Expected Sionna {expected['sionna_version']}, "
            f"found {sionna_distribution_version}"
        )

    seed = 29001
    uma_summary, uma_a, uma_tau = generate_scenario(
        "uma", cfg["pilot_scenarios"]["uma"], expected, seed
    )
    umi_summary, _umi_a, _umi_tau = generate_scenario(
        "umi", cfg["pilot_scenarios"]["umi"], expected, seed + 1
    )
    uma_repeat_summary, uma_a_repeat, uma_tau_repeat = generate_scenario(
        "uma", cfg["pilot_scenarios"]["uma"], expected, seed
    )
    coefficient_repeat_error = float(
        torch.max(torch.abs(uma_a - uma_a_repeat)).item()
    )
    delay_repeat_error = float(
        torch.max(torch.abs(uma_tau - uma_tau_repeat)).item()
    )
    reproducible = bool(
        torch.allclose(uma_a, uma_a_repeat, rtol=1e-5, atol=1e-7)
        and torch.allclose(uma_tau, uma_tau_repeat, rtol=1e-6, atol=1e-9)
    )
    if not reproducible:
        raise ValueError(
            "Seeded CPU UMa qualification was not reproducible within tolerance"
        )
    if uma_summary["fingerprints"] != uma_repeat_summary["fingerprints"]:
        raise ValueError("Seeded UMa qualification fingerprints differ")

    environment = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "torch_version": torch_version,
        "torch_base_version": torch_base_version,
        "sionna_distribution": expected["sionna_distribution"],
        "sionna_version": sionna_distribution_version,
        "torch_cuda_available": bool(torch.cuda.is_available()),
        "torch_device_used": "cpu",
    }
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_ENVIRONMENT_AND_API_QUALIFICATION",
        "claim_boundary": cfg["claim_boundary"]["api_qualification"],
        "environment": environment,
        "uma": uma_summary,
        "umi": umi_summary,
        "seeded_uma_reproducibility": {
            "passed": reproducible,
            "maximum_coefficient_absolute_error": coefficient_repeat_error,
            "maximum_delay_absolute_error_s": delay_repeat_error,
        },
        "standards_boundary": cfg["standards_boundary"],
        "next_gate": cfg["next_gate"],
    }
    write_json(work / "SIONNA2_API_QUALIFICATION_AUDIT.json", audit)
    write_json(work / "UMA_API_QUALIFICATION_SUMMARY.json", uma_summary)
    write_json(work / "UMI_API_QUALIFICATION_SUMMARY.json", umi_summary)
    write_json(work / "SIONNA2_ENVIRONMENT.json", environment)

    print("SIONNA 2.0.1 CHANNEL API QUALIFICATION: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
