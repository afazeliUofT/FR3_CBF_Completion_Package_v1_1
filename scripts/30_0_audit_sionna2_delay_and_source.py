#!/usr/bin/env python3
"""Harden the Sionna qualification with energy-weighted delay and source audits."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import importlib.util
import inspect
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reset_seed(seed: int) -> None:
    import torch

    torch.manual_seed(seed)
    np.random.seed(seed)
    from sionna.phy import config as sionna_config

    sionna_config.seed = seed


def generate(name: str, seed: int, carrier: float):
    from sionna.phy.channel.tr38901 import PanelArray, UMa, UMi
    from sionna.sys import gen_hexgrid_topology

    reset_seed(seed)
    bs_array = PanelArray(
        num_rows_per_panel=2,
        num_cols_per_panel=2,
        polarization="dual",
        polarization_type="cross",
        antenna_pattern="38.901",
        carrier_frequency=carrier,
        precision="single",
        device="cpu",
    )
    ut_array = PanelArray(
        num_rows_per_panel=1,
        num_cols_per_panel=1,
        polarization="single",
        polarization_type="V",
        antenna_pattern="omni",
        carrier_frequency=carrier,
        precision="single",
        device="cpu",
    )
    model_cls = UMa if name == "uma" else UMi
    height = 25.0 if name == "uma" else 10.0
    isd = 500.0 if name == "uma" else 200.0
    minimum = 35.0 if name == "uma" else 10.0
    model = model_cls(
        carrier_frequency=carrier,
        o2i_model="low",
        ut_array=ut_array,
        bs_array=bs_array,
        direction="downlink",
        enable_pathloss=True,
        enable_shadow_fading=True,
        always_generate_lsp=False,
        precision="single",
        device="cpu",
    )
    topology = gen_hexgrid_topology(
        batch_size=1,
        num_rings=1,
        num_ut_per_sector=1,
        scenario=name,
        min_bs_ut_dist=minimum,
        isd=isd,
        bs_height=height,
        min_ut_height=1.5,
        max_ut_height=1.5,
        indoor_probability=0.8,
        min_ut_velocity=0.0,
        max_ut_velocity=0.0,
        return_grid=False,
        precision="single",
        device="cpu",
    )
    model.set_topology(*topology)
    coefficients, delays = model(
        num_time_samples=1,
        sampling_frequency=15_000.0,
    )
    return model, topology, coefficients, delays


def delay_metrics(
    scenario: str,
    coefficients,
    delays,
    relative_floor: float,
    cumulative_fraction: float,
    raw_outlier_threshold: float,
):
    coefficient_array = (
        coefficients.detach().cpu().numpy()
        if hasattr(coefficients, "detach")
        else np.asarray(coefficients)
    )
    tau = (
        delays.detach().cpu().numpy()
        if hasattr(delays, "detach")
        else np.asarray(delays)
    )
    energy = np.abs(coefficient_array) ** 2
    energy = energy.sum(axis=(2, 4, 6))
    if energy.shape != tau.shape:
        raise ValueError(f"Energy/delay shape mismatch: {energy.shape} vs {tau.shape}")

    link_rows = []
    outlier_rows = []
    max_active = 0.0
    max_support = 0.0
    max_rms = 0.0
    raw_max = float(np.max(tau))

    batch, users, base_stations, paths = energy.shape
    for b in range(batch):
        for u in range(users):
            for bs in range(base_stations):
                p = energy[b, u, bs].astype(np.float64)
                d = tau[b, u, bs].astype(np.float64)
                total = float(p.sum())
                if total <= 0 or not np.isfinite(total):
                    raise ValueError(f"{scenario}: nonpositive link energy b={b},u={u},bs={bs}")
                maximum = float(p.max())
                relative = p / maximum
                active = relative >= relative_floor
                active_max = float(d[active].max())
                weights = p / total
                mean = float(np.sum(weights * d))
                rms = float(np.sqrt(np.sum(weights * np.square(d - mean))))
                order = np.argsort(d)
                cumulative = np.cumsum(weights[order])
                support_index = min(
                    int(np.searchsorted(cumulative, cumulative_fraction, side="left")),
                    paths - 1,
                )
                support_delay = float(d[order[support_index]])
                max_active = max(max_active, active_max)
                max_support = max(max_support, support_delay)
                max_rms = max(max_rms, rms)
                link_rows.append(
                    {
                        "scenario": scenario,
                        "batch_index": b,
                        "user_index": u,
                        "bs_index": bs,
                        "total_energy": total,
                        "maximum_path_energy": maximum,
                        "raw_max_delay_s": float(d.max()),
                        "active_max_delay_s": active_max,
                        "energy_support_delay_s": support_delay,
                        "rms_delay_spread_s": rms,
                        "active_path_count": int(active.sum()),
                    }
                )
                for path_index in np.flatnonzero(d > raw_outlier_threshold):
                    outlier_rows.append(
                        {
                            "scenario": scenario,
                            "batch_index": b,
                            "user_index": u,
                            "bs_index": bs,
                            "path_index": int(path_index),
                            "delay_s": float(d[path_index]),
                            "path_energy": float(p[path_index]),
                            "relative_to_link_max_energy": float(relative[path_index]),
                            "fraction_of_link_energy": float(weights[path_index]),
                        }
                    )
    return {
        "scenario": scenario,
        "raw_max_delay_s": raw_max,
        "maximum_relative_floor_active_delay_s": max_active,
        "maximum_energy_support_delay_s": max_support,
        "maximum_rms_delay_spread_s": max_rms,
        "link_count": len(link_rows),
        "raw_delay_outlier_count": len(outlier_rows),
    }, link_rows, outlier_rows


def source_provenance() -> dict[str, object]:
    from sionna.phy.channel import cir_to_ofdm_channel
    from sionna.phy.channel.tr38901 import UMa, UMi

    module_names = [
        "sionna.phy.channel.tr38901.uma",
        "sionna.phy.channel.tr38901.umi",
        "sionna.phy.channel.tr38901.system_level_channel",
        "sionna.phy.channel.tr38901.system_level_scenario",
        "sionna.phy.channel.tr38901.channel_coefficients",
        "sionna.phy.channel.tr38901.rays",
        "sionna.phy.channel.utils",
        "sionna.sys.topology",
    ]
    records = []
    for name in module_names:
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None:
            raise RuntimeError(f"Cannot resolve installed module: {name}")
        path = Path(spec.origin)
        records.append(
            {
                "module": name,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "torch_version": importlib.metadata.version("torch"),
        "sionna_no_rt_version": importlib.metadata.version("sionna-no-rt"),
        "uma_call_signature": str(inspect.signature(UMa.__call__)),
        "uma_set_topology_signature": str(inspect.signature(UMa.set_topology)),
        "umi_call_signature": str(inspect.signature(UMi.__call__)),
        "cir_to_ofdm_channel_signature": str(inspect.signature(cir_to_ofdm_channel)),
        "module_files": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/sionna2_topology_readiness.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    settings = cfg["delay_audit"]
    work = ROOT / cfg["environment"]["work_dir"]
    work.mkdir(parents=True, exist_ok=True)

    if importlib.metadata.version("sionna-no-rt") != expected["sionna_version"]:
        raise ValueError("Unexpected Sionna version")
    if importlib.metadata.version("torch").split("+", 1)[0] != expected[
        "torch_base_version"
    ]:
        raise ValueError("Unexpected PyTorch base version")

    all_link_rows = []
    all_outliers = []
    scenario_summaries = []
    for scenario, seed in [
        ("uma", int(settings["qualification_seed_uma"])),
        ("umi", int(settings["qualification_seed_umi"])),
    ]:
        _model, _topology, coefficients, delays = generate(
            scenario,
            seed,
            float(expected["carrier_frequency_hz"]),
        )
        summary, links, outliers = delay_metrics(
            scenario,
            coefficients,
            delays,
            float(settings["relative_path_energy_floor"]),
            float(settings["cumulative_energy_fraction"]),
            float(settings["raw_delay_outlier_threshold_s"]),
        )
        summary["coefficient_shape"] = list(coefficients.shape)
        summary["delay_shape"] = list(delays.shape)
        scenario_summaries.append(summary)
        all_link_rows.extend(links)
        all_outliers.extend(outliers)

    maximum_supported = max(
        item["maximum_energy_support_delay_s"] for item in scenario_summaries
    )
    maximum_rms = max(
        item["maximum_rms_delay_spread_s"] for item in scenario_summaries
    )
    passed = (
        maximum_supported
        <= float(settings["maximum_energy_supported_delay_s"])
        and maximum_rms <= float(settings["maximum_rms_delay_spread_s"])
    )
    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_ENERGY_WEIGHTED_DELAY_SANITY"
            if passed
            else "SCIENTIFIC_STOP_ACTIVE_DELAY_SANITY_FAILED"
        ),
        "claim_boundary": cfg["claim_boundary"]["delay_audit"],
        "raw_delay_interpretation": (
            "The raw maximum is retained but is not accepted as a physical "
            "delay metric without considering path energy."
        ),
        "settings": settings,
        "scenario_summaries": scenario_summaries,
        "maximum_energy_supported_delay_s": maximum_supported,
        "maximum_rms_delay_spread_s": maximum_rms,
        "source_provenance": source_provenance(),
        "next_gate": (
            "CUSTOM_57_SECTOR_TOPOLOGY_ADAPTER_AUDIT"
            if passed
            else "DIAGNOSE_ACTIVE_MULTI_SECOND_SIONNA_PATHS"
        ),
    }
    write_json(work / "SIONNA2_DELAY_AND_SOURCE_AUDIT.json", decision)

    with (work / "SIONNA2_DELAY_LINK_METRICS.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_link_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_link_rows)

    fields = [
        "scenario",
        "batch_index",
        "user_index",
        "bs_index",
        "path_index",
        "delay_s",
        "path_energy",
        "relative_to_link_max_energy",
        "fraction_of_link_energy",
    ]
    with (work / "SIONNA2_RAW_DELAY_OUTLIERS.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(all_outliers, key=lambda row: row["delay_s"], reverse=True))

    print("SIONNA 2.0.1 DELAY/SOURCE AUDIT:", "PASS" if passed else "SCIENTIFIC STOP")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
