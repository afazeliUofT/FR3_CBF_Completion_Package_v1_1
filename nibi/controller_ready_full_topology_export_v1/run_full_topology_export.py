#!/usr/bin/env python3
"""Generate a controller-ready full-228-user Sionna export on one Nibi H100."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch

C_M_S = 299_792_458.0
ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input"
OUTPUT = ROOT / "output"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_array(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def wrap_deg(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def reset_seed(seed: int) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
    from sionna.phy import config as sionna_config

    sionna_config.seed = seed


def build_topology(cfg: dict, device: str):
    sites = pd.read_csv(INPUT / "bs_sites.csv").sort_values("site_id").reset_index(drop=True)
    sectors = pd.read_csv(INPUT / "bs_sectors.csv").sort_values("sector_id").reset_index(drop=True)
    if len(sites) != cfg["site_count"] or len(sectors) != cfg["sector_count"]:
        raise ValueError("Frozen site/sector count mismatch")
    required = {"site_id", "east_m", "north_m"}
    missing = sorted(required - set(sites.columns))
    if missing:
        raise ValueError(f"bs_sites.csv is missing {missing}")
    sites = sites.copy()
    sites["x_m"] = pd.to_numeric(sites["east_m"], errors="raise")
    sites["y_m"] = pd.to_numeric(sites["north_m"], errors="raise")
    if not np.isfinite(sites[["x_m", "y_m"]].to_numpy(float)).all():
        raise ValueError("Frozen site coordinates are non-finite")
    site_index = sites.set_index("site_id")

    rng = np.random.default_rng(int(cfg["user_seed"]))
    bs_rows, ut_rows, serving, stream_index = [], [], [], []
    for bs_index, sector in sectors.iterrows():
        site = site_index.loc[str(sector["site_id"])]
        azimuth = float(sector["azimuth_deg"]) % 360.0
        bs_rows.append(
            {
                "bs_index": int(bs_index),
                "sector_id": str(sector["sector_id"]),
                "site_id": str(sector["site_id"]),
                "x_m": float(site["x_m"]),
                "y_m": float(site["y_m"]),
                "z_m": 25.0,
                "yaw_rad": math.radians((90.0 - azimuth) % 360.0),
                "pitch_rad": math.radians(float(sector["downtilt_deg"])),
                "roll_rad": 0.0,
            }
        )
        for local_stream in range(int(cfg["users_per_sector"])):
            radius = math.sqrt(
                rng.uniform(
                    float(cfg["user_radius_min_m"]) ** 2,
                    float(cfg["user_radius_max_m"]) ** 2,
                )
            )
            offset = float(
                rng.uniform(
                    -float(cfg["sector_half_width_deg"]),
                    float(cfg["sector_half_width_deg"]),
                )
            )
            user_azimuth = (azimuth + offset) % 360.0
            user_azimuth_rad = math.radians(user_azimuth)
            indoor = bool(rng.random() < float(cfg["indoor_probability"]))
            ut_rows.append(
                {
                    "user_index": len(ut_rows),
                    "user_id": f"{sector['sector_id']}_UE_{local_stream+1}",
                    "serving_bs_index": int(bs_index),
                    "serving_sector_id": str(sector["sector_id"]),
                    "local_stream_index": local_stream,
                    "x_m": float(site["x_m"]) + radius * math.sin(user_azimuth_rad),
                    "y_m": float(site["y_m"]) + radius * math.cos(user_azimuth_rad),
                    "z_m": 1.5,
                    "radius_m": radius,
                    "offset_deg": wrap_deg(user_azimuth - azimuth),
                    "indoor": indoor,
                }
            )
            serving.append(int(bs_index))
            stream_index.append(int(local_stream))

    bs = pd.DataFrame(bs_rows)
    ut = pd.DataFrame(ut_rows)
    if len(bs) != int(cfg["sector_count"]) or len(ut) != int(cfg["user_count"]):
        raise ValueError("Unexpected topology dimensions")
    if not np.array_equal(
        np.bincount(np.asarray(serving, dtype=np.int64), minlength=len(bs)),
        np.full(len(bs), int(cfg["users_per_sector"]), dtype=np.int64),
    ):
        raise ValueError("Every sector must serve exactly four users")

    bs_loc = torch.tensor(bs[["x_m", "y_m", "z_m"]].to_numpy(np.float32)[None], device=device)
    bs_ori = torch.tensor(bs[["yaw_rad", "pitch_rad", "roll_rad"]].to_numpy(np.float32)[None], device=device)
    ut_loc = torch.tensor(ut[["x_m", "y_m", "z_m"]].to_numpy(np.float32)[None], device=device)
    ut_ori = torch.zeros_like(ut_loc)
    ut_vel = torch.zeros_like(ut_loc)
    in_state = torch.tensor(ut["indoor"].to_numpy(bool)[None], device=device)
    return (
        bs,
        ut,
        bs_loc,
        bs_ori,
        ut_loc,
        ut_ori,
        ut_vel,
        in_state,
        np.asarray(serving, dtype=np.int64),
        np.asarray(stream_index, dtype=np.int64),
    )


def local_rzf(h_rows: torch.Tensor, power_w: float, noise_w: float) -> torch.Tensor:
    k, _m = h_rows.shape
    columns = h_rows.conj().transpose(0, 1)
    alpha = max(float(k * noise_w / power_w), 1e-20)
    gram = columns.conj().transpose(0, 1) @ columns
    eye = torch.eye(k, dtype=columns.dtype, device=columns.device)
    w = columns @ torch.linalg.solve(gram + alpha * eye, eye)
    norm = torch.sum(torch.abs(w) ** 2).real
    if not torch.isfinite(norm) or norm <= 0:
        raise ValueError("Invalid RZF norm")
    return w * math.sqrt(power_w / float(norm.item()))


def make_arrays(cfg: dict, device: str):
    from sionna.phy.channel.tr38901 import PanelArray

    bs_array = PanelArray(
        num_rows_per_panel=int(cfg["bs_array_rows"]),
        num_cols_per_panel=int(cfg["bs_array_cols"]),
        polarization=str(cfg["bs_array_polarization"]),
        polarization_type=str(cfg["bs_array_polarization_type"]),
        antenna_pattern="38.901",
        carrier_frequency=float(cfg["carrier_frequency_hz"]),
        element_vertical_spacing=0.5,
        element_horizontal_spacing=0.5,
        precision="single",
        device=device,
    )
    ut_array = PanelArray(
        num_rows_per_panel=1,
        num_cols_per_panel=1,
        polarization="single",
        polarization_type="V",
        antenna_pattern="omni",
        carrier_frequency=float(cfg["carrier_frequency_hz"]),
        precision="single",
        device=device,
    )
    if int(bs_array.num_ant) != int(cfg["bs_port_count"]):
        raise ValueError("Unexpected BS port count")
    return bs_array, ut_array


def make_model(cfg: dict, bs_array, ut_array, device: str):
    from sionna.phy.channel.tr38901 import UMa

    return UMa(
        carrier_frequency=float(cfg["carrier_frequency_hz"]),
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


def steering_modes(array, local_direction_xyz, frequency_hz: float, device: str):
    positions = array.ant_pos.to(device=device, dtype=torch.float64)
    pol1 = array.ant_ind_pol1.to(device)
    pol2 = array.ant_ind_pol2.to(device)
    direction = torch.as_tensor(local_direction_xyz, dtype=torch.float64, device=device).reshape(3)
    direction = direction / torch.linalg.norm(direction)
    phase = 2.0 * math.pi * frequency_hz / C_M_S * (positions @ direction)
    spatial = torch.exp(-1j * phase).to(torch.complex64)
    a1 = torch.zeros(array.num_ant, dtype=torch.complex64, device=device)
    a2 = torch.zeros(array.num_ant, dtype=torch.complex64, device=device)
    a1[pol1] = spatial[pol1]
    a2[pol2] = spatial[pol2]
    return a1, a2


def verify_port_and_frame_inputs(cfg: dict, array) -> pd.DataFrame:
    mapping = json.loads(
        (INPUT / "TR38901_USED_SUBSET_MAPPING_DECISION.json").read_text(encoding="utf-8")
    )
    if mapping["status"] != "USED_SUBSET_READY_FOR_NONPAPER_GPU_PILOT_WITH_RELEASE19_GAPS":
        raise ValueError("Used-subset mapping is not pilot-ready")

    port_reference = pd.read_csv(INPUT / "SIONNA_8X8_DUAL_PORT_ORDER.csv")
    if len(port_reference) != int(array.num_ant):
        raise ValueError("Port-reference count mismatch")
    actual_positions = array.ant_pos.detach().cpu().numpy().astype(np.float64)
    reference_positions = port_reference[["x_m", "y_m", "z_m"]].to_numpy(float)
    if float(np.max(np.abs(actual_positions - reference_positions))) > 2e-7:
        raise ValueError("GPU array positions differ from the audited order")
    expected_pol1 = port_reference.loc[
        port_reference["polarization"] == "pol1", "port_index"
    ].to_numpy(np.int64)
    expected_pol2 = port_reference.loc[
        port_reference["polarization"] == "pol2", "port_index"
    ].to_numpy(np.int64)
    if not np.array_equal(array.ant_ind_pol1.detach().cpu().numpy(), expected_pol1):
        raise ValueError("Polarization-1 port order mismatch")
    if not np.array_equal(array.ant_ind_pol2.detach().cpu().numpy(), expected_pol2):
        raise ValueError("Polarization-2 port order mismatch")

    frame_audit = json.loads(
        (INPUT / "SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT.json").read_text(encoding="utf-8")
    )
    if frame_audit["status"] != "PASS_EXACT_SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT":
        raise ValueError("Incumbent local-frame audit is not accepted")
    frame = pd.read_csv(INPUT / "SIONNA_INCUMBENT_LOCAL_FRAME.csv")
    if len(frame) != int(cfg["sector_count"]) or frame["sector_id"].nunique() != len(frame):
        raise ValueError("Local-frame table must contain 57 unique sectors")
    norms = np.linalg.norm(
        frame[["local_direction_x", "local_direction_y", "local_direction_z"]].to_numpy(float),
        axis=1,
    )
    if not np.allclose(norms, 1.0, rtol=0.0, atol=2e-12):
        raise ValueError("A local incumbent direction is not unit norm")
    return frame.set_index("sector_id")


def generate_full_channel(
    cfg: dict,
    model,
    topology_tensors: tuple[torch.Tensor, ...],
    device: str,
):
    from sionna.phy.channel import cir_to_ofdm_channel

    reset_seed(int(cfg["channel_seed"]))
    model.reset_topology()
    model.set_topology(*topology_tensors)
    started = time.perf_counter()
    coefficients, delays = model(num_time_samples=1, sampling_frequency=15_000.0)
    offsets = torch.tensor(cfg["frequency_offsets_hz"], dtype=delays.dtype, device=device)
    response = cir_to_ofdm_channel(offsets, coefficients, delays, normalize=False)
    h = response[0, :, 0, :, :, 0, :]
    expected = (
        int(cfg["user_count"]),
        int(cfg["sector_count"]),
        int(cfg["bs_port_count"]),
        len(cfg["frequency_offsets_hz"]),
    )
    if tuple(h.shape) != expected:
        raise ValueError(f"Unexpected full response shape {tuple(h.shape)} != {expected}")
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    record = {
        "mode": "one_topology_call_all_228_users",
        "coefficient_shape": list(coefficients.shape),
        "delay_shape": list(delays.shape),
        "response_shape": list(h.shape),
        "elapsed_seconds": elapsed,
        "gpu_peak_allocated_gib": torch.cuda.max_memory_allocated(0) / 1024.0**3,
        "coefficients_sha256": sha256_array(coefficients.detach().cpu().numpy()),
        "delays_sha256": sha256_array(delays.detach().cpu().numpy()),
        "frequency_response_sha256": sha256_array(h.detach().cpu().numpy()),
    }
    return h, record


def generate_chunked_reference(
    cfg: dict,
    bs_array,
    ut_array,
    topology_tensors: tuple[torch.Tensor, ...],
    serving: np.ndarray,
    device: str,
):
    from sionna.phy.channel import cir_to_ofdm_channel

    ut_loc, bs_loc, ut_ori, bs_ori, ut_vel, in_state = topology_tensors
    reset_seed(int(cfg["channel_seed"]))
    model = make_model(cfg, bs_array, ut_array, device)
    h = torch.empty(
        (
            int(cfg["user_count"]),
            int(cfg["sector_count"]),
            int(cfg["bs_port_count"]),
            len(cfg["frequency_offsets_hz"]),
        ),
        dtype=torch.complex64,
        device=device,
    )
    response_hasher = hashlib.sha256()
    started = time.perf_counter()
    for start in range(0, int(cfg["user_count"]), int(cfg["users_per_sector"])):
        stop = start + int(cfg["users_per_sector"])
        if len(np.unique(serving[start:stop])) != 1:
            raise ValueError("Legacy reproduction chunk crosses serving sectors")
        model.reset_topology()
        model.set_topology(
            ut_loc[:, start:stop],
            bs_loc,
            ut_ori[:, start:stop],
            bs_ori,
            ut_vel[:, start:stop],
            in_state[:, start:stop],
        )
        coefficients, delays = model(num_time_samples=1, sampling_frequency=15_000.0)
        offsets = torch.tensor(cfg["frequency_offsets_hz"], dtype=delays.dtype, device=device)
        full = cir_to_ofdm_channel(offsets, coefficients, delays, normalize=False)
        chunk = full[0, :, 0, :, :, 0, :]
        h[start:stop] = chunk
        response_hasher.update(chunk.detach().cpu().contiguous().numpy().tobytes())
        del coefficients, delays, full, chunk
        torch.cuda.empty_cache()
    torch.cuda.synchronize()
    return h, {
        "mode": "legacy_57_four_user_chunks",
        "elapsed_seconds": time.perf_counter() - started,
        "frequency_response_chunk_stream_sha256": response_hasher.hexdigest(),
        "expected_frequency_response_chunk_stream_sha256": cfg[
            "reference_frequency_response_chunk_stream_sha256"
        ],
    }


def process_channel(
    cfg: dict,
    h: torch.Tensor,
    serving: np.ndarray,
    stream_index: np.ndarray,
):
    weights = np.asarray(cfg["frequency_weights"], dtype=np.float64)
    if not np.isclose(weights.sum(), 1.0, rtol=0.0, atol=1e-14):
        raise ValueError("Frequency weights do not sum to one")
    total_power_w = 10.0 ** ((float(cfg["conducted_power_dbm_per_100mhz"]) - 30.0) / 10.0)
    noise_total_dbm = (
        float(cfg["thermal_noise_density_dbm_per_hz"])
        + 10.0 * math.log10(float(cfg["total_bandwidth_hz"]))
        + float(cfg["noise_figure_db"])
    )
    noise_total_w = 10.0 ** ((noise_total_dbm - 30.0) / 10.0)
    power_by_frequency = total_power_w * weights
    noise_by_frequency = noise_total_w * weights

    frequency_count = len(weights)
    nominal_w = []
    for bs in range(int(cfg["sector_count"])):
        users = np.flatnonzero(serving == bs)
        if len(users) != int(cfg["users_per_sector"]):
            raise ValueError(f"BS {bs}: wrong local user count")
        per_frequency = []
        for f in range(frequency_count):
            per_frequency.append(
                local_rzf(
                    h[users, bs, :, f],
                    float(power_by_frequency[f]),
                    float(noise_by_frequency[f]),
                )
            )
        nominal_w.append(torch.stack(per_frequency, dim=0))
    nominal_w = torch.stack(nominal_w, dim=0)  # [B,F,M,K]

    amplitudes, desired_rows, interference_rows, sinr_rows, rate_rows = [], [], [], [], []
    user_indices = torch.arange(int(cfg["user_count"]), device=h.device)
    serving_tensor = torch.as_tensor(serving, device=h.device)
    stream_tensor = torch.as_tensor(stream_index, device=h.device)
    for f in range(frequency_count):
        amplitude = torch.einsum("ubm,bmk->ubk", h[:, :, :, f], nominal_w[:, f])
        power = torch.abs(amplitude) ** 2
        total = torch.sum(power, dim=(1, 2))
        desired = power[user_indices, serving_tensor, stream_tensor]
        interference = total - desired
        sinr = desired / (interference + float(noise_by_frequency[f]))
        rate = torch.log2(1.0 + sinr)
        amplitudes.append(amplitude)
        desired_rows.append(desired)
        interference_rows.append(interference)
        sinr_rows.append(sinr)
        rate_rows.append(rate)

    amplitude_by_frequency = torch.stack(amplitudes, dim=0)  # [F,U,B,K]
    desired_by_frequency = torch.stack(desired_rows, dim=0)
    interference_by_frequency = torch.stack(interference_rows, dim=0)
    sinr_by_frequency = torch.stack(sinr_rows, dim=0)
    rate_by_frequency = torch.stack(rate_rows, dim=0).to(torch.float64)
    weighted_total_rate = torch.sum(
        torch.as_tensor(weights, device=h.device, dtype=torch.float64)[:, None]
        * rate_by_frequency,
        dim=0,
    )
    protected = int(cfg["protected_frequency_index"])
    other_weighted_rate = weighted_total_rate - float(weights[protected]) * rate_by_frequency[protected]

    return {
        "weights": weights,
        "power_by_frequency": power_by_frequency,
        "noise_by_frequency": noise_by_frequency,
        "nominal_w": nominal_w,
        "amplitude_by_frequency": amplitude_by_frequency,
        "desired_by_frequency": desired_by_frequency.to(torch.float64),
        "interference_by_frequency": interference_by_frequency.to(torch.float64),
        "sinr_by_frequency": sinr_by_frequency.to(torch.float64),
        "rate_by_frequency": rate_by_frequency,
        "weighted_total_rate": weighted_total_rate,
        "other_weighted_rate": other_weighted_rate,
        "protected_rate": rate_by_frequency[protected],
    }


def build_protected_decomposition(
    cfg: dict,
    bs: pd.DataFrame,
    array,
    frame_reference: pd.DataFrame,
    h: torch.Tensor,
    nominal_w: torch.Tensor,
):
    protected = int(cfg["protected_frequency_index"])
    steering1, steering2, coefficients, leakage = [], [], [], []
    amp0, amp1, amp2 = [], [], []
    for bs_index, row in bs.iterrows():
        reference = frame_reference.loc[row["sector_id"]]
        direction = [
            float(reference["local_direction_x"]),
            float(reference["local_direction_y"]),
            float(reference["local_direction_z"]),
        ]
        a1, a2 = steering_modes(
            array,
            direction,
            float(cfg["carrier_frequency_hz"]),
            h.device,
        )
        w = nominal_w[bs_index, protected]
        u1 = a1 / torch.linalg.norm(a1)
        u2 = a2 / torch.linalg.norm(a2)
        p1 = u1[:, None] * (u1.conj() @ w)[None, :]
        p2 = u2[:, None] * (u2.conj() @ w)[None, :]
        perpendicular = w - p1 - p2
        c1 = a1.conj() @ w
        c2 = a2.conj() @ w
        steering1.append(a1)
        steering2.append(a2)
        coefficients.append(torch.stack([c1, c2], dim=0))
        leakage.append(
            torch.stack(
                [
                    torch.sum(torch.abs(c1) ** 2).real,
                    torch.sum(torch.abs(c2) ** 2).real,
                ]
            )
        )
        amp0.append(torch.einsum("um,mk->uk", h[:, bs_index, :, protected], perpendicular))
        amp1.append(torch.einsum("um,mk->uk", h[:, bs_index, :, protected], p1))
        amp2.append(torch.einsum("um,mk->uk", h[:, bs_index, :, protected], p2))

    return {
        "steering_pol1": torch.stack(steering1, dim=0),
        "steering_pol2": torch.stack(steering2, dim=0),
        "mode_coefficients": torch.stack(coefficients, dim=0),
        "mode_leakage": torch.stack(leakage, dim=0).to(torch.float64),
        "amp_perpendicular": torch.stack(amp0, dim=1),
        "amp_pol1": torch.stack(amp1, dim=1),
        "amp_pol2": torch.stack(amp2, dim=1),
    }


def build_kappa(cfg: dict, bs: pd.DataFrame):
    static = pd.read_csv(INPUT / "sector_static_reference_accounting.csv")
    static = static.loc[
        np.isclose(static["p452_time_percentage"], float(cfg["p452_time_percentage"]))
        & (static["polarization_label"] == str(cfg["p452_polarization"]))
        & (static["bs_gain_case"] == "ELEMENT_PATTERN_REFERENCE")
    ].drop_duplicates("sector_id").set_index("sector_id")
    if len(static) != int(cfg["sector_count"]):
        raise ValueError("Static P.452 table does not contain 57 sectors")

    earth = pd.read_csv(INPUT / "earth_station_site_gain_timeseries.csv.gz")
    earth = earth.loc[
        (earth["earth_station_pattern_type"] == str(cfg["earth_station_pattern_type"]))
        & np.isclose(earth["aperture_efficiency"], float(cfg["aperture_efficiency"]))
    ]
    pivot = earth.pivot(index="time_s", columns="site_id", values="earth_station_gain_dbi").sort_index()
    if len(pivot) != 587:
        raise ValueError("Expected 587 protected-pass samples")

    kappa = np.zeros((len(pivot), int(cfg["sector_count"])), dtype=np.float64)
    for t_index, (_time_s, gains) in enumerate(pivot.iterrows()):
        for bs_index, row in bs.iterrows():
            srow = static.loc[row["sector_id"]]
            kappa[t_index, bs_index] = 10.0 ** (
                (
                    float(srow["element_pattern_gain_dbi"])
                    - float(srow["basic_transmission_loss_db"])
                    + float(gains[row["site_id"]])
                )
                / 10.0
            )
    threshold = 10.0 ** (float(cfg["short_threshold_dbw_per_10mhz"]) / 10.0)
    allowance = np.full(
        len(pivot),
        (1.0 - float(cfg["reserve_fraction"])) * threshold,
        dtype=np.float64,
    )
    return pivot.index.to_numpy(np.float64), kappa, allowance


def common_scale_reference(
    cfg: dict,
    decomposition: dict,
    processing: dict,
    kappa: np.ndarray,
    allowance: np.ndarray,
    serving: np.ndarray,
    stream_index: np.ndarray,
):
    leakage = decomposition["mode_leakage"].detach().cpu().numpy()
    nominal_aggregate = kappa @ leakage.sum(axis=1)
    scale = np.minimum(
        1.0,
        np.sqrt(allowance / np.maximum(nominal_aggregate, 1e-300)),
    )
    a0 = decomposition["amp_perpendicular"].detach().cpu().numpy()
    a1 = decomposition["amp_pol1"].detach().cpu().numpy()
    a2 = decomposition["amp_pol2"].detach().cpu().numpy()
    other = processing["other_weighted_rate"].detach().cpu().numpy()
    protected_weight = float(processing["weights"][int(cfg["protected_frequency_index"])])
    noise = float(processing["noise_by_frequency"][int(cfg["protected_frequency_index"])])
    user_rates = np.zeros((len(scale), int(cfg["user_count"])), dtype=np.float64)
    for t, value in enumerate(scale):
        amplitude = a0 + value * a1 + value * a2
        power = np.abs(amplitude) ** 2
        total = power.sum(axis=(1, 2))
        desired = power[np.arange(len(serving)), serving, stream_index]
        sinr = desired / (total - desired + noise)
        user_rates[t] = other + protected_weight * np.log2(1.0 + sinr)
    return nominal_aggregate, scale, user_rates


def save_array(name: str, value: np.ndarray, manifest: dict[str, dict[str, object]]) -> None:
    path = OUTPUT / name
    np.save(path, value, allow_pickle=False)
    manifest[name] = {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def quantiles(value: np.ndarray) -> dict[str, float]:
    return {
        key: float(np.quantile(value, q))
        for key, q in [
            ("min", 0.0),
            ("p01", 0.01),
            ("p05", 0.05),
            ("p50", 0.50),
            ("p95", 0.95),
            ("p99", 0.99),
            ("max", 1.0),
        ]
    }


def main() -> int:
    started = time.perf_counter()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((ROOT / "export_config.json").read_text(encoding="utf-8"))

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is not visible")
    device = "cuda:0"
    props = torch.cuda.get_device_properties(0)
    if "H100" not in torch.cuda.get_device_name(0) or props.total_memory < 75 * 1024**3:
        raise RuntimeError("The full-topology export requires one H100 80 GB-class GPU")

    (
        bs,
        ut,
        bs_loc,
        bs_ori,
        ut_loc,
        ut_ori,
        ut_vel,
        in_state,
        serving,
        stream_index,
    ) = build_topology(cfg, device)
    topology_tensors = (ut_loc, bs_loc, ut_ori, bs_ori, ut_vel, in_state)
    bs_array, ut_array = make_arrays(cfg, device)
    frame_reference = verify_port_and_frame_inputs(cfg, bs_array)

    full_model = make_model(cfg, bs_array, ut_array, device)
    h_full, full_record = generate_full_channel(cfg, full_model, topology_tensors, device)
    full_processing_started = time.perf_counter()
    full_processing = process_channel(cfg, h_full, serving, stream_index)
    full_decomposition = build_protected_decomposition(
        cfg,
        bs,
        bs_array,
        frame_reference,
        h_full,
        full_processing["nominal_w"],
    )
    full_processing_seconds = time.perf_counter() - full_processing_started

    protected = int(cfg["protected_frequency_index"])
    reconstructed = (
        full_decomposition["amp_perpendicular"]
        + full_decomposition["amp_pol1"]
        + full_decomposition["amp_pol2"]
    )
    reconstruction_error = float(
        torch.max(
            torch.abs(
                reconstructed
                - full_processing["amplitude_by_frequency"][protected]
            )
        ).item()
    )
    if reconstruction_error > 2e-5:
        raise RuntimeError(f"Protected amplitude decomposition error: {reconstruction_error}")

    time_s, kappa, allowance = build_kappa(cfg, bs)
    nominal_aggregate, common_scale, common_rate = common_scale_reference(
        cfg,
        full_decomposition,
        full_processing,
        kappa,
        allowance,
        serving,
        stream_index,
    )
    if np.any(nominal_aggregate * common_scale**2 > allowance * (1.0 + 3e-6) + 1e-30):
        raise RuntimeError("Common-scale reference violates aggregate allowance")

    # Reproduce the immutable legacy chunked mode before comparing platforms.
    h_chunked, chunk_record = generate_chunked_reference(
        cfg,
        bs_array,
        ut_array,
        topology_tensors,
        serving,
        device,
    )
    chunk_processing = process_channel(cfg, h_chunked, serving, stream_index)
    chunk_decomposition = build_protected_decomposition(
        cfg,
        bs,
        bs_array,
        frame_reference,
        h_chunked,
        chunk_processing["nominal_w"],
    )
    chunk_nominal_aggregate, chunk_common_scale, chunk_common_rate = common_scale_reference(
        cfg,
        chunk_decomposition,
        chunk_processing,
        kappa,
        allowance,
        serving,
        stream_index,
    )

    reference_users = pd.read_csv(INPUT / "reference_job_18658301/PILOT_USER_RATE_SUMMARY.csv")
    reference_time = pd.read_csv(INPUT / "reference_job_18658301/PILOT_TIME_SUMMARY.csv")
    reference_audit = json.loads(
        (INPUT / "reference_job_18658301/NIBI_ONE_SEED_DLP_RZF_PILOT_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    reference_nominal_user = reference_users["nominal_se_bps_hz"].to_numpy(np.float64)
    chunk_nominal_user = chunk_processing["weighted_total_rate"].detach().cpu().numpy()
    max_user_rate_error = float(np.max(np.abs(chunk_nominal_user - reference_nominal_user)))
    network_sum_error = float(
        abs(
            chunk_nominal_user.sum()
            - float(reference_time["network_nominal_sum_se_bps_hz"].iloc[0])
        )
    )
    reference_nominal_aggregate = reference_time["aggregate_nominal_interference_w"].to_numpy(np.float64)
    incumbent_relative_error = float(
        np.max(
            np.abs(chunk_nominal_aggregate - reference_nominal_aggregate)
            / np.maximum(np.abs(reference_nominal_aggregate), 1e-300)
        )
    )
    numeric_reproduction_pass = (
        max_user_rate_error <= float(cfg["numeric_reproduction_rate_atol"])
        and network_sum_error <= float(cfg["numeric_reproduction_network_sum_atol"])
        and incumbent_relative_error <= float(cfg["numeric_reproduction_incumbent_rtol"])
    )
    if not numeric_reproduction_pass:
        raise RuntimeError(
            "Legacy chunked numerical reproduction failed: "
            f"user={max_user_rate_error}, sum={network_sum_error}, "
            f"incumbent={incumbent_relative_error}"
        )

    full_nominal_user = full_processing["weighted_total_rate"].detach().cpu().numpy()
    full_interference = full_processing["interference_by_frequency"].detach().cpu().numpy()
    chunk_interference = chunk_processing["interference_by_frequency"].detach().cpu().numpy()
    full_desired = full_processing["desired_by_frequency"].detach().cpu().numpy()
    chunk_desired = chunk_processing["desired_by_frequency"].detach().cpu().numpy()

    def top_sector_order(kappa_matrix: np.ndarray, leakage_tensor: np.ndarray) -> list[int]:
        received = kappa_matrix * leakage_tensor.sum(axis=1)[None, :]
        worst = int(np.argmax(received.sum(axis=1)))
        return np.argsort(received[worst])[::-1].tolist()

    full_leakage = full_decomposition["mode_leakage"].detach().cpu().numpy()
    chunk_leakage = chunk_decomposition["mode_leakage"].detach().cpu().numpy()
    full_order = top_sector_order(kappa, full_leakage)
    chunk_order = top_sector_order(kappa, chunk_leakage)
    top10_overlap = len(set(full_order[:10]).intersection(chunk_order[:10]))

    comparison = {
        "reference_job_id": str(cfg["reference_job_id"]),
        "legacy_numeric_reproduction": {
            "pass": numeric_reproduction_pass,
            "maximum_user_nominal_rate_error_bps_hz": max_user_rate_error,
            "network_sum_rate_error_bps_hz": network_sum_error,
            "maximum_nominal_incumbent_relative_error": incumbent_relative_error,
            "bitwise_response_hash_match": (
                chunk_record["frequency_response_chunk_stream_sha256"]
                == str(cfg["reference_frequency_response_chunk_stream_sha256"])
            ),
            "prior_audit_response_hash": reference_audit["fingerprints"][
                "frequency_response_chunk_stream_sha256"
            ],
            "new_response_hash": chunk_record["frequency_response_chunk_stream_sha256"],
        },
        "full_vs_chunked": {
            "full_nominal_network_sum_se_bps_hz": float(full_nominal_user.sum()),
            "chunked_nominal_network_sum_se_bps_hz": float(chunk_nominal_user.sum()),
            "relative_network_sum_difference": float(
                (full_nominal_user.sum() - chunk_nominal_user.sum())
                / max(abs(chunk_nominal_user.sum()), 1e-300)
            ),
            "per_user_nominal_rate_difference_quantiles_bps_hz": quantiles(
                full_nominal_user - chunk_nominal_user
            ),
            "per_user_nominal_rate_correlation": float(
                np.corrcoef(full_nominal_user, chunk_nominal_user)[0, 1]
            ),
            "desired_power_ratio_quantiles": quantiles(
                full_desired.reshape(-1)
                / np.maximum(chunk_desired.reshape(-1), 1e-300)
            ),
            "interference_power_ratio_quantiles": quantiles(
                full_interference.reshape(-1)
                / np.maximum(chunk_interference.reshape(-1), 1e-300)
            ),
            "nominal_incumbent_db_difference_quantiles": quantiles(
                10.0
                * np.log10(
                    np.maximum(nominal_aggregate, 1e-300)
                    / np.maximum(chunk_nominal_aggregate, 1e-300)
                )
            ),
            "top10_dominant_sector_overlap_count": top10_overlap,
            "full_common_scale_minimum_network_retention": float(
                np.min(common_rate.sum(axis=1) / full_nominal_user.sum())
            ),
            "chunked_common_scale_minimum_network_retention": float(
                np.min(chunk_common_rate.sum(axis=1) / chunk_nominal_user.sum())
            ),
            "interpretation": (
                "Differences combine topology-generation mode, random-number "
                "mapping, and correlation structure; they are not attributed "
                "only to spatial correlation."
            ),
        },
    }
    write_json(OUTPUT / "FULL_VS_CHUNKED_COMPARISON.json", comparison)

    bs.to_csv(OUTPUT / "SECTOR_TOPOLOGY.csv", index=False)
    ut.to_csv(OUTPUT / "USER_TOPOLOGY.csv", index=False)

    arrays: dict[str, dict[str, object]] = {}
    h_full_cpu = np.transpose(h_full.detach().cpu().numpy(), (3, 0, 1, 2)).astype(np.complex64)
    save_array("frequency_response.npy", h_full_cpu, arrays)
    save_array("serving_bs_index.npy", serving.astype(np.int64), arrays)
    save_array("serving_stream_index.npy", stream_index.astype(np.int64), arrays)
    save_array("frequency_offsets_hz.npy", np.asarray(cfg["frequency_offsets_hz"], dtype=np.float64), arrays)
    save_array("frequency_weights.npy", full_processing["weights"].astype(np.float64), arrays)
    save_array("transmit_power_by_frequency_w.npy", full_processing["power_by_frequency"].astype(np.float64), arrays)
    save_array("noise_power_by_frequency_w.npy", full_processing["noise_by_frequency"].astype(np.float64), arrays)
    save_array(
        "nominal_precoder_by_frequency.npy",
        np.transpose(
            full_processing["nominal_w"].detach().cpu().numpy(),
            (1, 0, 2, 3),
        ).astype(np.complex64),
        arrays,
    )
    save_array(
        "nominal_precoder_power_w.npy",
        np.transpose(
            torch.sum(torch.abs(full_processing["nominal_w"]) ** 2, dim=(2, 3))
            .real.detach().cpu().numpy(),
            (1, 0),
        ).astype(np.float64),
        arrays,
    )
    save_array(
        "nominal_amplitude_by_frequency.npy",
        full_processing["amplitude_by_frequency"].detach().cpu().numpy().astype(np.complex64),
        arrays,
    )
    save_array(
        "nominal_user_desired_power_by_frequency_w.npy",
        full_processing["desired_by_frequency"].detach().cpu().numpy().astype(np.float64),
        arrays,
    )
    save_array(
        "nominal_user_interference_power_by_frequency_w.npy",
        full_processing["interference_by_frequency"].detach().cpu().numpy().astype(np.float64),
        arrays,
    )
    save_array(
        "nominal_user_sinr_by_frequency.npy",
        full_processing["sinr_by_frequency"].detach().cpu().numpy().astype(np.float64),
        arrays,
    )
    save_array(
        "nominal_user_rate_by_frequency.npy",
        full_processing["rate_by_frequency"].detach().cpu().numpy().astype(np.float64),
        arrays,
    )
    save_array(
        "nominal_total_weighted_rate_per_user.npy",
        full_nominal_user.astype(np.float64),
        arrays,
    )
    save_array(
        "other_frequency_weighted_rate_per_user.npy",
        full_processing["other_weighted_rate"].detach().cpu().numpy().astype(np.float64),
        arrays,
    )
    save_array(
        "nominal_protected_rate_per_user.npy",
        full_processing["protected_rate"].detach().cpu().numpy().astype(np.float64),
        arrays,
    )
    for filename, key in [
        ("protected_amp_perpendicular.npy", "amp_perpendicular"),
        ("protected_amp_pol1.npy", "amp_pol1"),
        ("protected_amp_pol2.npy", "amp_pol2"),
        ("protected_steering_pol1.npy", "steering_pol1"),
        ("protected_steering_pol2.npy", "steering_pol2"),
        ("protected_mode_coefficients.npy", "mode_coefficients"),
        ("nominal_mode_leakage_w.npy", "mode_leakage"),
    ]:
        value = full_decomposition[key].detach().cpu().numpy()
        if np.iscomplexobj(value):
            value = value.astype(np.complex64)
        else:
            value = value.astype(np.float64)
        save_array(filename, value, arrays)
    save_array("kappa_time_sector.npy", kappa.astype(np.float64), arrays)
    save_array("protected_time_s.npy", time_s.astype(np.float64), arrays)
    save_array("aggregate_allowance_w.npy", allowance.astype(np.float64), arrays)
    save_array("nominal_aggregate_interference_w.npy", nominal_aggregate.astype(np.float64), arrays)
    save_array("common_scale_reference.npy", common_scale.astype(np.float64), arrays)
    save_array("common_scale_user_rate.npy", common_rate.astype(np.float64), arrays)

    output_manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "arrays": arrays,
        "tables": {
            name: {
                "bytes": (OUTPUT / name).stat().st_size,
                "sha256": sha256_file(OUTPUT / name),
            }
            for name in ["USER_TOPOLOGY.csv", "SECTOR_TOPOLOGY.csv"]
        },
    }
    write_json(OUTPUT / "OUTPUT_ARRAY_MANIFEST.json", output_manifest)

    environment = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": os.sys.version,
        "torch_version": importlib.metadata.version("torch"),
        "sionna_version": importlib.metadata.version("sionna-no-rt"),
        "cuda_version": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_total_memory_bytes": props.total_memory,
        "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(0),
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    write_json(OUTPUT / "FULL_TOPOLOGY_EXPORT_ENVIRONMENT.json", environment)

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"],
        "full_topology": full_record,
        "chunked_reference": chunk_record,
        "protected_decomposition_max_error": reconstruction_error,
        "dimensions": {
            "sites": int(cfg["site_count"]),
            "sectors": int(cfg["sector_count"]),
            "users": int(cfg["user_count"]),
            "users_per_sector": int(cfg["users_per_sector"]),
            "ports_per_bs": int(cfg["bs_port_count"]),
            "frequency_samples": len(cfg["frequency_offsets_hz"]),
            "protected_pass_samples": len(time_s),
        },
        "output_manifest": "OUTPUT_ARRAY_MANIFEST.json",
        "comparison": comparison,
        "runtime_seconds": {
            "full_topology_channel_generation": full_record["elapsed_seconds"],
            "full_processing": full_processing_seconds,
            "legacy_chunked_reproduction": chunk_record["elapsed_seconds"],
            "total": time.perf_counter() - started,
        },
        "limitations": [
            "one channel/topology seed and one protected pass",
            "finite 19-site network without wraparound",
            "8x8 dual-polarized fully digital array",
            "nine frequency samples rather than the final OFDM grid",
            "common-scale DLP remains an oracle reference rather than the proposed controller",
            "full-versus-chunked differences are not attributed only to spatial correlation",
            "paper-grade uncertainty, mobility, practical-array, and statistical gates remain open",
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(OUTPUT / "FULL_TOPOLOGY_EXPORT_AUDIT.json", audit)

    print("CONTROLLER-READY FULL-TOPOLOGY EXPORT: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
