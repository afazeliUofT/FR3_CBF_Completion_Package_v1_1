#!/usr/bin/env python3
"""Run a deterministic 57-sector distributed local-precoding audit.

This is deliberately a software/architecture audit, not a standards-aligned
paper channel experiment.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from _bootstrap import ROOT
from fr3_cbf.distributed_precoding import (
    leakage_power_w,
    local_rzf_precoder,
    local_sum_rate_bps_hz,
    project_precoder_to_leakage_budget,
    proportional_received_interference_budgets,
    upa_steering_vector,
)


def db_to_linear(value_db: np.ndarray | float) -> np.ndarray | float:
    return 10.0 ** (np.asarray(value_db) / 10.0)


def w_to_dbw(value_w: np.ndarray | float) -> np.ndarray | float:
    return 10.0 * np.log10(np.maximum(np.asarray(value_w), 1e-300))


def complex_gaussian(rng: np.random.Generator, size: int) -> np.ndarray:
    return (
        rng.normal(size=size) + 1j * rng.normal(size=size)
    ) / np.sqrt(2.0)


def local_channel_matrix(
    rng: np.random.Generator,
    rows: int,
    cols: int,
    users: int,
    spacing: float,
    rician_k_db: float,
    azimuth_span_deg: float,
    elevation_span_deg: float,
) -> tuple[np.ndarray, list[dict[str, float]]]:
    k_linear = 10.0 ** (rician_k_db / 10.0)
    channels = []
    metadata = []
    for user in range(users):
        az = float(rng.uniform(-azimuth_span_deg / 2.0, azimuth_span_deg / 2.0))
        el = float(rng.uniform(-elevation_span_deg / 2.0, elevation_span_deg / 2.0))
        los = upa_steering_vector(
            rows, cols, az, el, spacing_lambda=spacing, normalize=True
        )
        scatter = complex_gaussian(rng, rows * cols)
        scatter = scatter / np.linalg.norm(scatter)
        channel = (
            np.sqrt(k_linear / (k_linear + 1.0)) * los
            + np.sqrt(1.0 / (k_linear + 1.0)) * scatter
        )
        channel = channel / np.linalg.norm(channel)
        channels.append(channel)
        metadata.append(
            {
                "user_index": user,
                "local_azimuth_offset_deg": az,
                "local_elevation_offset_deg": el,
            }
        )
    return np.column_stack(channels), metadata


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/distributed_ia_rzf_architecture.yaml"
    )
    args = parser.parse_args()
    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    inp = {key: ROOT / value for key, value in cfg["inputs"].items()}
    out = ROOT / cfg["outputs"]["work_dir"]
    review = ROOT / cfg["outputs"]["review_dir"]
    out.mkdir(parents=True, exist_ok=True)
    review.mkdir(parents=True, exist_ok=True)

    architecture = json.loads(
        (out / "DISTRIBUTED_IA_RZF_ARCHITECTURE_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    if architecture["status"] != "FROZEN_DISTRIBUTED_ARCHITECTURE_NOT_PAPER_RESULT":
        raise ValueError("Distributed architecture is not frozen")

    static = pd.read_csv(inp["sector_static_csv"])
    es = pd.read_csv(inp["earth_station_gain_csv_gz"])
    sectors = pd.read_csv(inp["bs_sectors_csv"])
    expected = cfg["expected"]
    assert sectors["sector_id"].nunique() == int(expected["sector_count"])
    assert sectors["site_id"].nunique() == int(expected["site_count"])

    proto = cfg["prototype"]
    selected = static.loc[
        np.isclose(
            static["p452_time_percentage"],
            float(proto["p452_time_percentage"]),
        )
        & (static["polarization_label"] == str(proto["polarization_label"]))
        & (
            static["bs_gain_case"]
            == str(proto["bs_reference_case_for_path_and_geometry"])
        )
    ].copy()
    assert len(selected) == int(expected["sector_count"])
    selected = selected.drop_duplicates("sector_id").set_index("sector_id")

    es_selected = es.loc[
        (es["earth_station_pattern_type"] == str(proto["earth_station_pattern_type"]))
        & np.isclose(es["aperture_efficiency"], float(proto["aperture_efficiency"]))
    ].copy()
    assert es_selected["time_s"].nunique() == int(
        expected["protected_sample_count"]
    )
    assert len(es_selected) == int(expected["site_count"]) * int(
        expected["protected_sample_count"]
    )

    rng = np.random.default_rng(int(cfg["local_precoder"]["random_seed"]))
    users = int(cfg["local_precoder"]["users_per_sector_prototype"])
    spacing = float(cfg["local_precoder"]["array_spacing_lambda"])
    regularization = float(cfg["local_precoder"]["rzf_regularization"])
    target_snr_db = float(
        cfg["local_precoder"]["prototype_target_single_user_snr_db"]
    )

    sector_models: dict[str, dict[str, object]] = {}
    static_rows = []

    for _, sector in sectors.sort_values("sector_id").iterrows():
        sector_id = str(sector["sector_id"])
        row = selected.loc[sector_id]
        array_rows = int(sector["array_rows"])
        array_cols = int(sector["array_cols"])
        channels, user_meta = local_channel_matrix(
            rng=rng,
            rows=array_rows,
            cols=array_cols,
            users=users,
            spacing=spacing,
            rician_k_db=float(cfg["local_precoder"]["prototype_rician_k_db"]),
            azimuth_span_deg=float(
                cfg["local_precoder"]["prototype_user_azimuth_span_deg"]
            ),
            elevation_span_deg=float(
                cfg["local_precoder"]["prototype_user_elevation_span_deg"]
            ),
        )
        protected_power_dbw = (
            float(row["conducted_power_dbw_per_100mhz"])
            + float(row["bandwidth_adjustment_db"])
            + float(row["activity_adjustment_db"])
        )
        power_w = float(10.0 ** (protected_power_dbw / 10.0))
        nominal = local_rzf_precoder(channels, power_w, regularization)
        incumbent = upa_steering_vector(
            array_rows,
            array_cols,
            float(row["horizontal_offset_deg"]),
            float(row["vertical_offset_deg"]),
            spacing_lambda=spacing,
            normalize=False,
        )
        leakage = leakage_power_w(nominal, incumbent)
        noise_w = power_w / users / (10.0 ** (target_snr_db / 10.0))
        nominal_rate = local_sum_rate_bps_hz(channels, nominal, noise_w)
        path_element_factor = float(
            10.0
            ** (
                (
                    float(row["element_pattern_gain_dbi"])
                    - float(row["basic_transmission_loss_db"])
                )
                / 10.0
            )
        )
        sector_models[sector_id] = {
            "site_id": str(sector["site_id"]),
            "channels": channels,
            "nominal": nominal,
            "incumbent": incumbent,
            "nominal_leakage_w": leakage,
            "noise_w": noise_w,
            "nominal_rate": nominal_rate,
            "path_element_factor": path_element_factor,
            "power_w": power_w,
        }
        static_rows.append(
            {
                "sector_id": sector_id,
                "site_id": str(sector["site_id"]),
                "array_rows": array_rows,
                "array_cols": array_cols,
                "users": users,
                "protected_band_power_w": power_w,
                "nominal_precoder_power_w": float(np.vdot(nominal, nominal).real),
                "nominal_transmit_domain_leakage_w": leakage,
                "nominal_local_sum_rate_bps_hz": nominal_rate,
                "horizontal_offset_deg": float(row["horizontal_offset_deg"]),
                "vertical_offset_deg": float(row["vertical_offset_deg"]),
                "element_pattern_gain_dbi": float(row["element_pattern_gain_dbi"]),
                "basic_transmission_loss_db": float(
                    row["basic_transmission_loss_db"]
                ),
                "prototype_user_metadata_json": json.dumps(user_meta),
            }
        )

    static_frame = pd.DataFrame(static_rows)
    static_frame.to_csv(out / "prototype_static_sector_models.csv", index=False)

    short_threshold_w = float(
        10.0 ** (float(cfg["budget"]["short_threshold_dbw_per_10mhz"]) / 10.0)
    )
    reserve = float(cfg["budget"]["reserve_fraction"])
    allowance = (1.0 - reserve) * short_threshold_w

    sector_order = sectors.sort_values("sector_id")["sector_id"].astype(str).tolist()
    es_pivot = es_selected.pivot(
        index="time_s", columns="site_id", values="earth_station_gain_dbi"
    ).sort_index()

    metric_rows = []
    time_rows = []

    for time_s, es_row in es_pivot.iterrows():
        nominal_received = []
        kappa_values = []
        for sector_id in sector_order:
            model = sector_models[sector_id]
            es_gain_db = float(es_row[str(model["site_id"])])
            kappa = float(model["path_element_factor"]) * float(
                10.0 ** (es_gain_db / 10.0)
            )
            received = kappa * float(model["nominal_leakage_w"])
            kappa_values.append(kappa)
            nominal_received.append(received)

        nominal_received_array = np.asarray(nominal_received, dtype=float)
        budgets = proportional_received_interference_budgets(
            nominal_received_array,
            short_threshold_w,
            reserve,
        )

        safe_received = []
        safe_rates = []
        nominal_rates = []
        scales = []
        local_violations = 0

        for index, sector_id in enumerate(sector_order):
            model = sector_models[sector_id]
            kappa = float(kappa_values[index])
            budget = float(budgets[index])
            maximum_transmit_leakage = budget / max(kappa, 1e-300)
            result = project_precoder_to_leakage_budget(
                model["nominal"],
                model["incumbent"],
                maximum_transmit_leakage,
            )
            received_safe = kappa * result.safe_leakage_w
            if received_safe > budget * (1.0 + 1e-9) + 1e-30:
                local_violations += 1
            safe_rate = local_sum_rate_bps_hz(
                model["channels"], result.precoder, float(model["noise_w"])
            )
            safe_received.append(received_safe)
            safe_rates.append(safe_rate)
            nominal_rates.append(float(model["nominal_rate"]))
            scales.append(result.projection_scale)
            metric_rows.append(
                {
                    "time_s": float(time_s),
                    "sector_id": sector_id,
                    "site_id": str(model["site_id"]),
                    "nominal_received_interference_w": float(
                        nominal_received_array[index]
                    ),
                    "local_budget_w": budget,
                    "safe_received_interference_w": received_safe,
                    "nominal_transmit_leakage_w": float(
                        model["nominal_leakage_w"]
                    ),
                    "safe_transmit_leakage_w": result.safe_leakage_w,
                    "projection_scale": result.projection_scale,
                    "projection_active": result.active,
                    "precoder_power_before_w": result.power_before_w,
                    "precoder_power_after_w": result.power_after_w,
                    "nominal_local_sum_rate_bps_hz": float(model["nominal_rate"]),
                    "safe_local_sum_rate_bps_hz": safe_rate,
                    "local_budget_satisfied": received_safe
                    <= budget * (1.0 + 1e-9) + 1e-30,
                }
            )

        aggregate_nominal = float(nominal_received_array.sum())
        aggregate_safe = float(np.sum(safe_received))
        if aggregate_safe > allowance * (1.0 + 1e-9) + 1e-30:
            raise RuntimeError("aggregate certificate failed")

        time_rows.append(
            {
                "time_s": float(time_s),
                "aggregate_nominal_interference_w": aggregate_nominal,
                "aggregate_nominal_interference_dbw": float(
                    w_to_dbw(aggregate_nominal)
                ),
                "aggregate_safe_interference_w": aggregate_safe,
                "aggregate_safe_interference_dbw": float(w_to_dbw(aggregate_safe)),
                "aggregate_allowance_w": allowance,
                "aggregate_allowance_dbw": float(w_to_dbw(allowance)),
                "short_threshold_w": short_threshold_w,
                "short_threshold_dbw": float(
                    cfg["budget"]["short_threshold_dbw_per_10mhz"]
                ),
                "budget_sum_w": float(budgets.sum()),
                "nominal_network_sum_rate_proxy_bps_hz": float(
                    np.sum(nominal_rates)
                ),
                "safe_network_sum_rate_proxy_bps_hz": float(np.sum(safe_rates)),
                "rate_retention_fraction": float(
                    np.sum(safe_rates) / max(np.sum(nominal_rates), 1e-300)
                ),
                "minimum_projection_scale": float(np.min(scales)),
                "median_projection_scale": float(np.median(scales)),
                "maximum_projection_scale": float(np.max(scales)),
                "local_budget_violation_count": int(local_violations),
            }
        )

    metrics = pd.DataFrame(metric_rows)
    summary = pd.DataFrame(time_rows).sort_values("time_s")
    metrics.to_csv(
        out / "prototype_sector_time_metrics.csv.gz",
        index=False,
        compression="gzip",
    )
    summary.to_csv(out / "prototype_time_summary.csv", index=False)

    assert len(summary) == int(expected["protected_sample_count"])
    assert len(metrics) == int(expected["protected_sample_count"]) * int(
        expected["sector_count"]
    )
    assert metrics["local_budget_satisfied"].all()
    assert (metrics["precoder_power_after_w"] <= metrics["precoder_power_before_w"] + 1e-10).all()
    assert summary["local_budget_violation_count"].eq(0).all()
    assert (
        summary["aggregate_safe_interference_w"]
        <= summary["aggregate_allowance_w"] * (1.0 + 1e-9) + 1e-30
    ).all()

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(
        summary["time_s"],
        summary["aggregate_nominal_interference_dbw"],
        label="nominal local RZF",
    )
    ax.plot(
        summary["time_s"],
        summary["aggregate_safe_interference_dbw"],
        label="certified local projection",
    )
    ax.axhline(
        float(cfg["budget"]["short_threshold_dbw_per_10mhz"]),
        linestyle="--",
        label="short threshold",
    )
    ax.set_xlabel("Protected-pass time (s)")
    ax.set_ylabel("Aggregate interference (dBW/10 MHz)")
    ax.set_title("Distributed local-RZF leakage-projection prototype")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(review / "prototype_aggregate_interference.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(
        summary["time_s"],
        summary["rate_retention_fraction"],
        label="local sum-rate proxy retention",
    )
    ax.set_xlabel("Protected-pass time (s)")
    ax.set_ylabel("Safe / nominal local-rate proxy")
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_title("Prototype utility cost of certified local leakage projection")
    fig.tight_layout()
    fig.savefig(review / "prototype_rate_retention.png", dpi=180)
    plt.close(fig)

    peak_time = float(
        summary.sort_values("aggregate_nominal_interference_w").iloc[-1]["time_s"]
    )
    peak = metrics.loc[np.isclose(metrics["time_s"], peak_time)].sort_values(
        "nominal_received_interference_w", ascending=False
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(peak["sector_id"], peak["projection_scale"])
    ax.tick_params(axis="x", rotation=75, labelsize=6)
    ax.set_ylabel("Incumbent-direction component scale")
    ax.set_title("Local projection scales at peak nominal leakage")
    fig.tight_layout()
    fig.savefig(review / "prototype_peak_projection_scales.png", dpi=180)
    plt.close(fig)

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_PROTOTYPE_ONLY",
        "claim_boundary": cfg["claim_boundary"]["prototype"],
        "sector_count": int(expected["sector_count"]),
        "protected_sample_count": int(expected["protected_sample_count"]),
        "sector_time_row_count": len(metrics),
        "budget_rule": cfg["budget"]["allocation_rule"],
        "aggregate_short_threshold_dbw_per_10mhz": float(
            cfg["budget"]["short_threshold_dbw_per_10mhz"]
        ),
        "reserve_fraction": reserve,
        "maximum_aggregate_safe_minus_allowance_w": float(
            (
                summary["aggregate_safe_interference_w"]
                - summary["aggregate_allowance_w"]
            ).max()
        ),
        "local_budget_violation_count": int(
            (~metrics["local_budget_satisfied"]).sum()
        ),
        "maximum_power_increase_w": float(
            (
                metrics["precoder_power_after_w"]
                - metrics["precoder_power_before_w"]
            ).max()
        ),
        "minimum_rate_retention_fraction": float(
            summary["rate_retention_fraction"].min()
        ),
        "median_rate_retention_fraction": float(
            summary["rate_retention_fraction"].median()
        ),
        "central_instantaneous_ue_csi_used": False,
        "joint_network_beamformer_used": False,
        "synthetic_channel_warning": (
            "The local channels are deterministic seeded Rician audit channels, "
            "not the standards-aligned paper channel experiment."
        ),
        "next_gate": cfg["next_gate"]["name"],
    }
    write_json(out / "DISTRIBUTED_IA_RZF_PROTOTYPE_AUDIT.json", audit)

    print("DISTRIBUTED IA-RZF PROTOTYPE AUDIT: PASS")
    print(json.dumps(audit, indent=2))
    print("\nTIME SUMMARY")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
