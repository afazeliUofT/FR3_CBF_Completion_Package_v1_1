#!/usr/bin/env python3
"""Run a small finite 57-sector Sionna custom-topology and inter-cell-rate pilot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def reset_seed(seed: int) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
    from sionna.phy import config as sionna_config

    sionna_config.seed = seed


def generate(cfg: dict, topology: dict[str, np.ndarray], seed: int):
    from sionna.phy.channel import cir_to_ofdm_channel
    from sionna.phy.channel.tr38901 import PanelArray, UMa

    expected = cfg["expected"]
    adapter = cfg["adapter"]
    reset_seed(seed)
    bs_array = PanelArray(
        num_rows_per_panel=int(adapter["bs_array_rows"]),
        num_cols_per_panel=int(adapter["bs_array_cols"]),
        polarization=str(adapter["bs_array_polarization"]),
        polarization_type=str(adapter["bs_array_polarization_type"]),
        antenna_pattern="38.901",
        carrier_frequency=float(expected["carrier_frequency_hz"]),
        precision="single",
        device="cpu",
    )
    ut_array = PanelArray(
        num_rows_per_panel=1,
        num_cols_per_panel=1,
        polarization=str(adapter["ut_array_polarization"]),
        polarization_type=str(adapter["ut_array_polarization_type"]),
        antenna_pattern="omni",
        carrier_frequency=float(expected["carrier_frequency_hz"]),
        precision="single",
        device="cpu",
    )
    model = UMa(
        carrier_frequency=float(expected["carrier_frequency_hz"]),
        o2i_model=str(adapter["o2i_model"]),
        ut_array=ut_array,
        bs_array=bs_array,
        direction="downlink",
        enable_pathloss=True,
        enable_shadow_fading=True,
        always_generate_lsp=False,
        precision="single",
        device="cpu",
    )
    tensors = {
        key: torch.from_numpy(value)
        for key, value in topology.items()
        if key
        in {
            "ut_loc",
            "bs_loc",
            "ut_orientations",
            "bs_orientations",
            "ut_velocities",
            "in_state",
        }
    }
    model.set_topology(
        tensors["ut_loc"],
        tensors["bs_loc"],
        tensors["ut_orientations"],
        tensors["bs_orientations"],
        tensors["ut_velocities"],
        tensors["in_state"],
    )
    coefficients, delays = model(
        num_time_samples=1,
        sampling_frequency=15_000.0,
    )
    frequencies = torch.zeros(1, dtype=delays.dtype)
    h_f = cir_to_ofdm_channel(
        frequencies,
        coefficients,
        delays,
        normalize=False,
    )
    return bs_array, ut_array, coefficients, delays, h_f


def delay_support(coefficients: torch.Tensor, delays: torch.Tensor, fraction: float):
    energy = torch.abs(coefficients).square().sum(dim=(2, 4, 6)).cpu().numpy()
    tau = delays.cpu().numpy()
    maximum_support = 0.0
    maximum_rms = 0.0
    for index in np.ndindex(energy.shape[:-1]):
        p = energy[index].astype(np.float64)
        d = tau[index].astype(np.float64)
        total = p.sum()
        if total <= 0:
            raise ValueError("Nonpositive channel-link energy")
        w = p / total
        mean = float(np.sum(w * d))
        rms = float(np.sqrt(np.sum(w * np.square(d - mean))))
        order = np.argsort(d)
        position = min(
            int(np.searchsorted(np.cumsum(w[order]), fraction, side="left")),
            len(d) - 1,
        )
        maximum_support = max(maximum_support, float(d[order[position]]))
        maximum_rms = max(maximum_rms, rms)
    return maximum_support, maximum_rms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/sionna2_topology_readiness.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    adapter = cfg["adapter"]
    work = ROOT / cfg["environment"]["work_dir"]

    skipped = work / "CUSTOM_TOPOLOGY_ADAPTER_SKIPPED.json"
    if skipped.is_file():
        print("CUSTOM SIONNA PILOT: SKIPPED DUE TO SCIENTIFIC STOP")
        return 0

    topology_path = work / "CUSTOM_57_SECTOR_TOPOLOGY.npz"
    if not topology_path.is_file():
        raise FileNotFoundError(topology_path)
    with np.load(topology_path, allow_pickle=False) as archive:
        topology = {key: np.asarray(archive[key]) for key in archive.files}

    if importlib.metadata.version("sionna-no-rt") != expected["sionna_version"]:
        raise ValueError("Unexpected Sionna version")
    if importlib.metadata.version("torch").split("+", 1)[0] != expected[
        "torch_base_version"
    ]:
        raise ValueError("Unexpected PyTorch version")

    seed = int(adapter["random_seed"]) + 1
    bs_array, ut_array, a, tau, h_f = generate(cfg, topology, seed)
    _bs2, _ut2, a_repeat, tau_repeat, h_repeat = generate(cfg, topology, seed)

    coefficient_error = float(torch.max(torch.abs(a - a_repeat)).item())
    delay_error = float(torch.max(torch.abs(tau - tau_repeat)).item())
    response_error = float(torch.max(torch.abs(h_f - h_repeat)).item())
    if coefficient_error != 0.0 or delay_error != 0.0 or response_error != 0.0:
        raise ValueError("Custom seeded Sionna topology is not bitwise reproducible")

    expected_users = int(expected["adapter_user_count"])
    expected_bs = int(expected["sector_count"])
    expected_ant = int(expected["adapter_bs_antenna_count"])
    if tuple(h_f.shape[:5]) != (1, expected_users, 1, expected_bs, expected_ant):
        raise ValueError(f"Unexpected frequency-response shape: {tuple(h_f.shape)}")
    if h_f.shape[-2:] != (1, 1):
        raise ValueError(f"Unexpected time/frequency axes: {tuple(h_f.shape)}")

    support_delay, rms_delay = delay_support(
        a,
        tau,
        float(cfg["delay_audit"]["cumulative_energy_fraction"]),
    )
    if support_delay > float(
        cfg["delay_audit"]["maximum_energy_supported_delay_s"]
    ):
        raise ValueError("Custom topology energy-supported delay exceeds 1 ms")
    if rms_delay > float(cfg["delay_audit"]["maximum_rms_delay_spread_s"]):
        raise ValueError("Custom topology RMS delay spread exceeds 1 ms")

    h = h_f[0, :, 0, :, :, 0, 0].detach().cpu().numpy()
    serving = topology["serving_bs_index"].astype(np.int64)
    sector_ids = topology["sector_ids"].astype(str)
    user_ids = topology["user_ids"].astype(str)
    power_w = 10.0 ** (
        (float(adapter["conducted_power_dbm_per_100mhz"]) - 30.0) / 10.0
    )
    noise_dbm = (
        float(adapter["thermal_noise_density_dbm_per_hz"])
        + 10.0 * math.log10(float(adapter["bandwidth_hz"]))
        + float(adapter["noise_figure_db"])
    )
    noise_w = 10.0 ** ((noise_dbm - 30.0) / 10.0)

    beamformers = np.zeros((expected_bs, expected_ant), dtype=np.complex64)
    for bs in range(expected_bs):
        user_indices = np.flatnonzero(serving == bs)
        if user_indices.size != 1:
            raise ValueError(f"Adapter expects one user per BS; bs={bs}")
        channel = h[user_indices[0], bs]
        norm = float(np.linalg.norm(channel))
        if norm <= 0 or not np.isfinite(norm):
            raise ValueError(f"Invalid serving channel norm for bs={bs}")
        beamformers[bs] = np.conj(channel) * math.sqrt(power_w) / norm

    rows = []
    desired_values = []
    interference_values = []
    rates = []
    for user in range(expected_users):
        contributions = np.abs(
            np.einsum("ba,ba->b", h[user], beamformers)
        ) ** 2
        serving_bs = int(serving[user])
        desired = float(contributions[serving_bs])
        interference = float(contributions.sum() - desired)
        sinr = desired / (interference + noise_w)
        rate = math.log2(1.0 + sinr)
        desired_values.append(desired)
        interference_values.append(interference)
        rates.append(rate)
        rows.append(
            {
                "user_index": user,
                "user_id": str(user_ids[user]),
                "serving_bs_index": serving_bs,
                "serving_sector_id": str(sector_ids[serving_bs]),
                "desired_signal_w": desired,
                "inter_cell_interference_w": interference,
                "noise_w": noise_w,
                "sinr_linear": sinr,
                "sinr_db": 10.0 * math.log10(max(sinr, 1e-300)),
                "spectral_efficiency_bps_hz": rate,
            }
        )

    with (work / "CUSTOM_57_SECTOR_USER_RATE_AUDIT.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    beam_power = np.sum(np.abs(beamformers) ** 2, axis=1)
    if not np.allclose(beam_power, power_w, rtol=1e-5, atol=1e-8):
        raise ValueError("Beam power normalization failed")
    if not np.all(np.isfinite(rates)):
        raise ValueError("Non-finite rate")

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_CUSTOM_57_SECTOR_CPU_ADAPTER_AUDIT",
        "claim_boundary": cfg["claim_boundary"]["topology_adapter"],
        "environment": {
            "torch_version": importlib.metadata.version("torch"),
            "sionna_version": importlib.metadata.version("sionna-no-rt"),
            "device": "cpu",
        },
        "dimensions": {
            "users": expected_users,
            "bs_sectors": expected_bs,
            "bs_antennas": int(bs_array.num_ant),
            "ut_antennas": int(ut_array.num_ant),
            "coefficients": list(a.shape),
            "delays": list(tau.shape),
            "frequency_response": list(h_f.shape),
        },
        "reproducibility": {
            "maximum_coefficient_error": coefficient_error,
            "maximum_delay_error_s": delay_error,
            "maximum_frequency_response_error": response_error,
        },
        "delay_sanity": {
            "maximum_energy_support_delay_s": support_delay,
            "maximum_rms_delay_spread_s": rms_delay,
        },
        "rate_accounting": {
            "power_w_per_sector": power_w,
            "noise_dbm_over_100mhz": noise_dbm,
            "noise_w": noise_w,
            "network_sum_spectral_efficiency_bps_hz": float(np.sum(rates)),
            "minimum_user_spectral_efficiency_bps_hz": float(np.min(rates)),
            "median_user_spectral_efficiency_bps_hz": float(np.median(rates)),
            "maximum_user_spectral_efficiency_bps_hz": float(np.max(rates)),
            "minimum_sinr_db": float(
                10.0 * np.log10(max(np.min(np.asarray(desired_values) / (
                    np.asarray(interference_values) + noise_w
                )), 1e-300))
            ),
        },
        "limitations": [
            "One user per sector only.",
            "2x2 dual-polarized 8-port BS array only.",
            "Finite 19-site network without wraparound.",
            "Center-frequency flat response only.",
            "MRT/local one-user RZF equivalence; DLP projection not yet applied.",
            "Not the four-user GPU paper pilot."
        ],
        "fingerprints": {
            "coefficients_sha256": digest(a.detach().cpu().numpy()),
            "delays_sha256": digest(tau.detach().cpu().numpy()),
            "frequency_response_sha256": digest(h_f.detach().cpu().numpy()),
            "beamformers_sha256": digest(beamformers),
        },
        "next_gate": cfg["next_gate"],
    }
    write_json(work / "CUSTOM_57_SECTOR_SIONNA_PILOT_AUDIT.json", audit)
    print("CUSTOM 57-SECTOR SIONNA CPU ADAPTER PILOT: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
