#!/usr/bin/env python3
"""One-seed 57-sector, four-user-per-sector Sionna/DLP-RZF GPU pilot."""
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
from pyproj import CRS, Transformer

C_M_S = 299_792_458.0
ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input"
OUTPUT = ROOT / "output"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest_array(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


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

    lat0 = float(sites["latitude_deg"].mean())
    lon0 = float(sites["longitude_deg"].mean())
    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat0:.12f} +lon_0={lon0:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)
    x, y = transformer.transform(
        sites["longitude_deg"].to_numpy(float),
        sites["latitude_deg"].to_numpy(float),
    )
    sites = sites.copy()
    sites["x_m"], sites["y_m"] = x, y
    site_index = sites.set_index("site_id")

    rng = np.random.default_rng(cfg["user_seed"])
    bs_rows, ut_rows, serving, local_stream = [], [], [], []
    for bs_index, sector in sectors.iterrows():
        site = site_index.loc[str(sector["site_id"])]
        az = float(sector["azimuth_deg"]) % 360.0
        yaw = math.radians((90.0 - az) % 360.0)
        pitch = math.radians(float(sector["downtilt_deg"]))
        bs_rows.append(
            {
                "bs_index": int(bs_index),
                "sector_id": str(sector["sector_id"]),
                "site_id": str(sector["site_id"]),
                "x_m": float(site["x_m"]),
                "y_m": float(site["y_m"]),
                "z_m": 25.0,
                "yaw_rad": yaw,
                "pitch_rad": pitch,
                "roll_rad": 0.0,
            }
        )
        for stream in range(cfg["users_per_sector"]):
            radius = math.sqrt(
                rng.uniform(cfg["user_radius_min_m"] ** 2, cfg["user_radius_max_m"] ** 2)
            )
            offset = float(
                rng.uniform(-cfg["sector_half_width_deg"], cfg["sector_half_width_deg"])
            )
            user_az = (az + offset) % 360.0
            user_az_rad = math.radians(user_az)
            indoor = bool(rng.random() < cfg["indoor_probability"])
            ut_rows.append(
                {
                    "user_index": len(ut_rows),
                    "user_id": f"{sector['sector_id']}_UE_{stream+1}",
                    "serving_bs_index": int(bs_index),
                    "serving_sector_id": str(sector["sector_id"]),
                    "local_stream_index": stream,
                    "x_m": float(site["x_m"]) + radius * math.sin(user_az_rad),
                    "y_m": float(site["y_m"]) + radius * math.cos(user_az_rad),
                    "z_m": 1.5,
                    "radius_m": radius,
                    "offset_deg": wrap_deg(user_az - az),
                    "indoor": indoor,
                }
            )
            serving.append(int(bs_index))
            local_stream.append(stream)

    bs = pd.DataFrame(bs_rows)
    ut = pd.DataFrame(ut_rows)
    if len(ut) != cfg["user_count"]:
        raise ValueError("Unexpected user count")
    bs_loc = torch.tensor(bs[["x_m", "y_m", "z_m"]].to_numpy(np.float32)[None], device=device)
    bs_ori = torch.tensor(bs[["yaw_rad", "pitch_rad", "roll_rad"]].to_numpy(np.float32)[None], device=device)
    ut_loc = torch.tensor(ut[["x_m", "y_m", "z_m"]].to_numpy(np.float32)[None], device=device)
    ut_ori = torch.zeros_like(ut_loc)
    ut_vel = torch.zeros_like(ut_loc)
    in_state = torch.tensor(ut["indoor"].to_numpy(bool)[None], device=device)
    return bs, ut, bs_loc, bs_ori, ut_loc, ut_ori, ut_vel, in_state, np.asarray(serving), np.asarray(local_stream)


def local_rzf(h_rows: torch.Tensor, power_w: float, noise_w: float) -> torch.Tensor:
    # h_rows [K,M], received convention y = h w.
    k, _m = h_rows.shape
    columns = h_rows.conj().transpose(0, 1)  # [M,K] for the repository convention.
    alpha = max(float(k * noise_w / power_w), 1e-20)
    gram = columns.conj().transpose(0, 1) @ columns
    eye = torch.eye(k, dtype=columns.dtype, device=columns.device)
    w = columns @ torch.linalg.solve(gram + alpha * eye, eye)
    norm = torch.sum(torch.abs(w) ** 2).real
    if not torch.isfinite(norm) or norm <= 0:
        raise ValueError("Invalid RZF norm")
    return w * math.sqrt(power_w / float(norm.item()))


def steering_modes(array, horizontal_deg: float, vertical_deg: float, frequency_hz: float, device: str):
    pos = array.ant_pos.to(device=device, dtype=torch.float64)
    pol1 = array.ant_ind_pol1.to(device)
    pol2 = array.ant_ind_pol2.to(device)
    az = math.radians(horizontal_deg)
    el = math.radians(vertical_deg)
    direction = torch.tensor(
        [math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)],
        dtype=torch.float64,
        device=device,
    )
    phase = 2.0 * math.pi * frequency_hz / C_M_S * (pos @ direction)
    spatial = torch.exp(1j * phase).to(torch.complex64)
    a1 = torch.zeros(array.num_ant, dtype=torch.complex64, device=device)
    a2 = torch.zeros(array.num_ant, dtype=torch.complex64, device=device)
    a1[pol1] = spatial[pol1]
    a2[pol2] = spatial[pol2]
    return a1, a2


def project_mode(w: torch.Tensor, a: torch.Tensor, budget: float):
    leakage = torch.sum(torch.abs(a.conj() @ w) ** 2).real
    leakage_value = float(leakage.item())
    if leakage_value <= budget * (1.0 + 1e-10) + 1e-30:
        return w, 1.0, leakage_value
    u = a / torch.linalg.norm(a)
    parallel = u[:, None] * (u.conj() @ w)[None, :]
    scale = math.sqrt(max(budget, 0.0) / leakage_value)
    safe = w - (1.0 - scale) * parallel
    safe_leakage = float(torch.sum(torch.abs(a.conj() @ safe) ** 2).real.item())
    if safe_leakage > budget * (1.0 + 1e-7) + 1e-28:
        raise RuntimeError("Local polarization-mode projection failed")
    return safe, scale, safe_leakage


def main() -> int:
    start = time.perf_counter()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((ROOT / "pilot_config.json").read_text(encoding="utf-8"))
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is not visible")
    device = "cuda:0"
    props = torch.cuda.get_device_properties(0)
    if props.total_memory < 70 * 1024**3:
        raise RuntimeError(f"Expected an 80 GB-class GPU, found {props.total_memory/1024**3:.1f} GiB")
    reset_seed(cfg["channel_seed"])

    from sionna.phy.channel import cir_to_ofdm_channel
    from sionna.phy.channel.tr38901 import PanelArray, UMa

    bs, ut, bs_loc, bs_ori, ut_loc, ut_ori, ut_vel, in_state, serving, stream_index = build_topology(cfg, device)
    array = PanelArray(
        num_rows_per_panel=cfg["bs_array_rows"],
        num_cols_per_panel=cfg["bs_array_cols"],
        polarization=cfg["bs_array_polarization"],
        polarization_type=cfg["bs_array_polarization_type"],
        antenna_pattern="38.901",
        carrier_frequency=cfg["carrier_frequency_hz"],
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
        carrier_frequency=cfg["carrier_frequency_hz"],
        precision="single",
        device=device,
    )
    if array.num_ant != cfg["bs_port_count"]:
        raise ValueError("Unexpected BS port count")

    mapping_decision = json.loads(
        (INPUT / "TR38901_USED_SUBSET_MAPPING_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    if mapping_decision["status"] != (
        "USED_SUBSET_READY_FOR_NONPAPER_GPU_PILOT_WITH_RELEASE19_GAPS"
    ):
        raise ValueError("Used-subset mapping decision is not pilot-ready")
    port_reference = pd.read_csv(INPUT / "SIONNA_8X8_DUAL_PORT_ORDER.csv")
    if len(port_reference) != array.num_ant:
        raise ValueError("Port-reference row count mismatch")
    actual_positions = array.ant_pos.detach().cpu().numpy().astype(np.float64)
    reference_positions = port_reference[["x_m", "y_m", "z_m"]].to_numpy(float)
    port_position_error = float(np.max(np.abs(actual_positions - reference_positions)))
    if port_position_error > 2e-7:
        raise ValueError(
            f"Nibi Sionna port positions differ from the audited CPU order: "
            f"{port_position_error} m"
        )
    expected_pol1 = port_reference.loc[
        port_reference["polarization"] == "pol1", "port_index"
    ].to_numpy(np.int64)
    expected_pol2 = port_reference.loc[
        port_reference["polarization"] == "pol2", "port_index"
    ].to_numpy(np.int64)
    actual_pol1 = array.ant_ind_pol1.detach().cpu().numpy().astype(np.int64)
    actual_pol2 = array.ant_ind_pol2.detach().cpu().numpy().astype(np.int64)
    if not np.array_equal(actual_pol1, expected_pol1):
        raise ValueError("Nibi polarization-1 port order differs from the audit")
    if not np.array_equal(actual_pol2, expected_pol2):
        raise ValueError("Nibi polarization-2 port order differs from the audit")
    model = UMa(
        carrier_frequency=cfg["carrier_frequency_hz"],
        o2i_model="low",
        ut_array=ut_array,
        bs_array=array,
        direction="downlink",
        enable_pathloss=True,
        enable_shadow_fading=True,
        always_generate_lsp=False,
        precision="single",
        device=device,
    )
    model.set_topology(ut_loc, bs_loc, ut_ori, bs_ori, ut_vel, in_state)
    channel_start = time.perf_counter()
    coefficients, delays = model(num_time_samples=1, sampling_frequency=15_000.0)
    offsets = torch.tensor(cfg["frequency_offsets_hz"], dtype=delays.dtype, device=device)
    h_f = cir_to_ofdm_channel(offsets, coefficients, delays, normalize=False)
    torch.cuda.synchronize()
    channel_seconds = time.perf_counter() - channel_start
    h = h_f[0, :, 0, :, :, 0, :]  # [U,B,M,F]
    if tuple(h.shape) != (
        cfg["user_count"],
        cfg["sector_count"],
        cfg["bs_port_count"],
        len(cfg["frequency_offsets_hz"]),
    ):
        raise ValueError(f"Unexpected channel shape: {tuple(h.shape)}")

    weights = np.asarray(cfg["frequency_weights"], dtype=float)
    if not np.isclose(weights.sum(), 1.0):
        raise ValueError("Frequency weights do not sum to one")
    total_power_w = 10.0 ** ((cfg["conducted_power_dbm_per_100mhz"] - 30.0) / 10.0)
    noise_total_dbm = (
        cfg["thermal_noise_density_dbm_per_hz"]
        + 10.0 * math.log10(cfg["total_bandwidth_hz"])
        + cfg["noise_figure_db"]
    )
    noise_total_w = 10.0 ** ((noise_total_dbm - 30.0) / 10.0)
    power_by_frequency = total_power_w * weights
    noise_by_frequency = noise_total_w * weights

    nominal_w = []
    rzf_start = time.perf_counter()
    for b in range(cfg["sector_count"]):
        users = np.flatnonzero(serving == b)
        if len(users) != cfg["users_per_sector"]:
            raise ValueError(f"BS {b}: wrong local user count")
        per_f = []
        for f in range(len(weights)):
            per_f.append(local_rzf(h[users, b, :, f], power_by_frequency[f], noise_by_frequency[f]))
        nominal_w.append(torch.stack(per_f, dim=0))  # [F,M,K]
    nominal_w = torch.stack(nominal_w, dim=0)  # [B,F,M,K]
    torch.cuda.synchronize()
    rzf_seconds = time.perf_counter() - rzf_start

    # Nominal rates across all frequency samples.
    nominal_rate_per_user = torch.zeros(cfg["user_count"], dtype=torch.float64, device=device)
    nominal_amplitudes = []
    for f in range(len(weights)):
        amp = torch.einsum("ubm,bmk->ubk", h[:, :, :, f], nominal_w[:, f])
        nominal_amplitudes.append(amp)
        power = torch.abs(amp) ** 2
        total = torch.sum(power, dim=(1, 2))
        desired = power[
            torch.arange(cfg["user_count"], device=device),
            torch.as_tensor(serving, device=device),
            torch.as_tensor(stream_index, device=device),
        ]
        sinr = desired / (total - desired + noise_by_frequency[f])
        nominal_rate_per_user += weights[f] * torch.log2(1.0 + sinr).to(torch.float64)

    protected = cfg["protected_frequency_index"]
    static = pd.read_csv(INPUT / "sector_static_reference_accounting.csv")
    static = static.loc[
        np.isclose(static["p452_time_percentage"], cfg["p452_time_percentage"])
        & (static["polarization_label"] == cfg["p452_polarization"])
        & (static["bs_gain_case"] == "ELEMENT_PATTERN_REFERENCE")
    ].drop_duplicates("sector_id").set_index("sector_id")
    if len(static) != cfg["sector_count"]:
        raise ValueError("Static propagation table does not have 57 sectors")
    es = pd.read_csv(INPUT / "earth_station_site_gain_timeseries.csv.gz")
    es = es.loc[
        (es["earth_station_pattern_type"] == cfg["earth_station_pattern_type"])
        & np.isclose(es["aperture_efficiency"], cfg["aperture_efficiency"])
    ]
    es_pivot = es.pivot(index="time_s", columns="site_id", values="earth_station_gain_dbi").sort_index()
    if len(es_pivot) != 587:
        raise ValueError("Unexpected protected-pass sample count")

    modes = []
    nominal_pol_leakage = np.zeros((cfg["sector_count"], 2), dtype=float)
    for b, row in bs.iterrows():
        sector_id = row["sector_id"]
        srow = static.loc[sector_id]
        a1, a2 = steering_modes(
            array,
            float(srow["horizontal_offset_deg"]),
            float(srow["vertical_offset_deg"]),
            cfg["carrier_frequency_hz"],
            device,
        )
        w0 = nominal_w[b, protected]
        l1 = float(torch.sum(torch.abs(a1.conj() @ w0) ** 2).real.item())
        l2 = float(torch.sum(torch.abs(a2.conj() @ w0) ** 2).real.item())
        nominal_pol_leakage[b] = [l1, l2]
        modes.append((a1, a2))

    threshold_w = 10.0 ** (cfg["short_threshold_dbw_per_10mhz"] / 10.0)
    allowance_w = (1.0 - cfg["reserve_fraction"]) * threshold_w
    time_rows = []
    sector_rows = []
    safe_rate_matrix = np.zeros((len(es_pivot), cfg["user_count"]), dtype=np.float64)

    # Protected-frequency decomposition h W = h(W_perp+s1 P1+s2 P2).
    amp0, amp1, amp2 = [], [], []
    parallel_components = []
    for b in range(cfg["sector_count"]):
        w0 = nominal_w[b, protected]
        a1, a2 = modes[b]
        u1 = a1 / torch.linalg.norm(a1)
        u2 = a2 / torch.linalg.norm(a2)
        p1 = u1[:, None] * (u1.conj() @ w0)[None, :]
        p2 = u2[:, None] * (u2.conj() @ w0)[None, :]
        perp = w0 - p1 - p2
        parallel_components.append((perp, p1, p2))
        amp0.append(torch.einsum("um,mk->uk", h[:, b, :, protected], perp))
        amp1.append(torch.einsum("um,mk->uk", h[:, b, :, protected], p1))
        amp2.append(torch.einsum("um,mk->uk", h[:, b, :, protected], p2))
    amp0 = torch.stack(amp0, dim=1)  # [U,B,K]
    amp1 = torch.stack(amp1, dim=1)
    amp2 = torch.stack(amp2, dim=1)

    other_rate = nominal_rate_per_user - weights[protected] * torch.log2(
        1.0
        + (
            torch.abs(nominal_amplitudes[protected]) ** 2
        )[
            torch.arange(cfg["user_count"], device=device),
            torch.as_tensor(serving, device=device),
            torch.as_tensor(stream_index, device=device),
        ]
        / (
            torch.sum(torch.abs(nominal_amplitudes[protected]) ** 2, dim=(1, 2))
            - (
                torch.abs(nominal_amplitudes[protected]) ** 2
            )[
                torch.arange(cfg["user_count"], device=device),
                torch.as_tensor(serving, device=device),
                torch.as_tensor(stream_index, device=device),
            ]
            + noise_by_frequency[protected]
        )
    ).to(torch.float64)

    dlp_start = time.perf_counter()
    for t_index, (time_s, es_row) in enumerate(es_pivot.iterrows()):
        kappa = np.zeros(cfg["sector_count"], dtype=float)
        nominal_received = np.zeros(cfg["sector_count"], dtype=float)
        for b, row in bs.iterrows():
            srow = static.loc[row["sector_id"]]
            es_gain = float(es_row[row["site_id"]])
            kappa[b] = 10.0 ** (
                (
                    float(srow["element_pattern_gain_dbi"])
                    - float(srow["basic_transmission_loss_db"])
                    + es_gain
                )
                / 10.0
            )
            nominal_received[b] = kappa[b] * nominal_pol_leakage[b].sum()
        total_nominal = nominal_received.sum()
        budgets = (
            np.full(cfg["sector_count"], allowance_w / cfg["sector_count"])
            if total_nominal <= 0
            else allowance_w * nominal_received / total_nominal
        )
        budgets[-1] += allowance_w - budgets.sum()

        scales = np.ones((cfg["sector_count"], 2), dtype=float)
        safe_received = np.zeros(cfg["sector_count"], dtype=float)
        for b in range(cfg["sector_count"]):
            total_l = nominal_pol_leakage[b].sum()
            gamma_total = budgets[b] / max(kappa[b], 1e-300)
            mode_budget = (
                np.array([gamma_total / 2.0, gamma_total / 2.0])
                if total_l <= 0
                else gamma_total * nominal_pol_leakage[b] / total_l
            )
            safe_l = []
            for p, (a, budget) in enumerate(zip(modes[b], mode_budget)):
                w_input = nominal_w[b, protected] if p == 0 else w_safe
                w_safe, scale, leakage = project_mode(w_input, a, float(budget))
                scales[b, p] = scale
                safe_l.append(leakage)
            safe_received[b] = kappa[b] * sum(safe_l)
            sector_rows.append(
                {
                    "time_s": float(time_s),
                    "sector_id": row["sector_id"] if False else bs.iloc[b]["sector_id"],
                    "site_id": bs.iloc[b]["site_id"],
                    "nominal_received_w": nominal_received[b],
                    "budget_w": budgets[b],
                    "safe_received_w": safe_received[b],
                    "pol1_scale": scales[b, 0],
                    "pol2_scale": scales[b, 1],
                    "budget_satisfied": bool(safe_received[b] <= budgets[b] * (1.0 + 2e-6) + 1e-30),
                }
            )

        # Exact protected-tone user rates from precomputed amplitude components.
        s1 = torch.tensor(scales[:, 0], dtype=amp0.dtype, device=device)[None, :, None]
        s2 = torch.tensor(scales[:, 1], dtype=amp0.dtype, device=device)[None, :, None]
        safe_amp = amp0 + s1 * amp1 + s2 * amp2
        power = torch.abs(safe_amp) ** 2
        total = torch.sum(power, dim=(1, 2))
        desired = power[
            torch.arange(cfg["user_count"], device=device),
            torch.as_tensor(serving, device=device),
            torch.as_tensor(stream_index, device=device),
        ]
        sinr = desired / (total - desired + noise_by_frequency[protected])
        rate = other_rate + weights[protected] * torch.log2(1.0 + sinr).to(torch.float64)
        safe_rate_matrix[t_index] = rate.detach().cpu().numpy()
        time_rows.append(
            {
                "time_s": float(time_s),
                "aggregate_nominal_interference_w": float(total_nominal),
                "aggregate_safe_interference_w": float(safe_received.sum()),
                "aggregate_allowance_w": float(allowance_w),
                "budget_sum_w": float(budgets.sum()),
                "local_violation_count": int(np.sum(safe_received > budgets * (1.0 + 2e-6) + 1e-30)),
                "network_nominal_sum_se_bps_hz": float(nominal_rate_per_user.sum().item()),
                "network_safe_sum_se_bps_hz": float(rate.sum().item()),
                "rate_retention_fraction": float(rate.sum().item() / nominal_rate_per_user.sum().item()),
                "minimum_pol_scale": float(scales.min()),
                "median_pol_scale": float(np.median(scales)),
            }
        )
    torch.cuda.synchronize()
    dlp_seconds = time.perf_counter() - dlp_start

    time_frame = pd.DataFrame(time_rows)
    sector_frame = pd.DataFrame(sector_rows)
    time_frame.to_csv(OUTPUT / "PILOT_TIME_SUMMARY.csv", index=False)
    sector_frame.to_csv(OUTPUT / "PILOT_SECTOR_TIME_METRICS.csv.gz", index=False, compression="gzip")
    user_frame = pd.DataFrame(
        {
            "user_id": ut["user_id"],
            "serving_sector_id": ut["serving_sector_id"],
            "nominal_se_bps_hz": nominal_rate_per_user.detach().cpu().numpy(),
            "safe_se_min_bps_hz": safe_rate_matrix.min(axis=0),
            "safe_se_median_bps_hz": np.median(safe_rate_matrix, axis=0),
            "safe_se_max_bps_hz": safe_rate_matrix.max(axis=0),
        }
    )
    user_frame.to_csv(OUTPUT / "PILOT_USER_RATE_SUMMARY.csv", index=False)
    np.savez_compressed(
        OUTPUT / "PILOT_NUMERICAL_EVIDENCE.npz",
        safe_rate_matrix=safe_rate_matrix,
        nominal_rate_per_user=nominal_rate_per_user.detach().cpu().numpy(),
        time_s=time_frame["time_s"].to_numpy(),
        aggregate_safe_w=time_frame["aggregate_safe_interference_w"].to_numpy(),
        aggregate_allowance_w=time_frame["aggregate_allowance_w"].to_numpy(),
    )

    peak_memory = torch.cuda.max_memory_allocated(0)
    elapsed = time.perf_counter() - start
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
        "gpu_peak_allocated_bytes": peak_memory,
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    write_json(OUTPUT / "NIBI_GPU_ENVIRONMENT.json", environment)
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_ONE_SEED_GPU_DLP_RZF_PILOT_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"],
        "dimensions": {
            "sites": cfg["site_count"],
            "sectors": cfg["sector_count"],
            "users": cfg["user_count"],
            "users_per_sector": cfg["users_per_sector"],
            "ports_per_bs": cfg["bs_port_count"],
            "frequency_samples": len(weights),
            "protected_pass_samples": len(time_frame),
        },
        "safety": {
            "short_threshold_dbw_per_10mhz": cfg["short_threshold_dbw_per_10mhz"],
            "reserve_fraction": cfg["reserve_fraction"],
            "maximum_safe_minus_allowance_w": float(
                (time_frame["aggregate_safe_interference_w"] - time_frame["aggregate_allowance_w"]).max()
            ),
            "maximum_budget_sum_error_w": float(
                np.abs(time_frame["budget_sum_w"] - time_frame["aggregate_allowance_w"]).max()
            ),
            "local_violation_count": int(sector_frame["budget_satisfied"].eq(False).sum()),
        },
        "utility": {
            "nominal_network_sum_se_bps_hz": float(nominal_rate_per_user.sum().item()),
            "minimum_rate_retention_fraction": float(time_frame["rate_retention_fraction"].min()),
            "median_rate_retention_fraction": float(time_frame["rate_retention_fraction"].median()),
            "minimum_nominal_user_se_bps_hz": float(user_frame["nominal_se_bps_hz"].min()),
            "minimum_safe_user_se_bps_hz": float(user_frame["safe_se_min_bps_hz"].min()),
        },
        "runtime_seconds": {
            "channel_generation": channel_seconds,
            "local_rzf": rzf_seconds,
            "dlp_pass_sweep": dlp_seconds,
            "total": elapsed,
        },
        "environment": environment,
        "standards_and_port_gates": {
            "used_subset_mapping_status": mapping_decision["status"],
            "full_v19_4_certification": mapping_decision["full_v19_4_certification"],
            "sionna_port_order_verified": True,
            "maximum_port_position_error_m": port_position_error,
            "dual_polarization_mode_count": 2,
        },
        "limitations": [
            "One channel/topology seed.",
            "Finite 19-site network without wraparound.",
            "8x8 dual-polarized pilot array rather than the frozen 16x16 sensitivity.",
            "Nine frequency samples are a pilot quadrature, not the final OFDM grid.",
            "Instantaneous proportional budgets are an oracle pilot; static/myopic/queue/CBF controllers are not compared.",
            "No mobility, uncertainty, calibration, multi-pass, or confidence interval evidence.",
        ],
        "fingerprints": {
            "coefficients_sha256": digest_array(coefficients.detach().cpu().numpy()),
            "delays_sha256": digest_array(delays.detach().cpu().numpy()),
            "frequency_response_sha256": digest_array(h_f.detach().cpu().numpy()),
            "nominal_precoders_sha256": digest_array(nominal_w.detach().cpu().numpy()),
            "safe_rate_matrix_sha256": digest_array(safe_rate_matrix),
        },
        "next_gate": cfg["next_gate"],
    }
    write_json(OUTPUT / "NIBI_ONE_SEED_DLP_RZF_PILOT_AUDIT.json", audit)
    print("NIBI ONE-SEED 57-SECTOR 4-USER DLP-RZF PILOT: PASS")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
