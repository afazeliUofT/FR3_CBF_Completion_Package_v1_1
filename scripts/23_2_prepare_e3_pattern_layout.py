#!/usr/bin/env python3
"""Prepare and optionally freeze the E3 antenna pattern and 19-site/57-sector layout."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from pyproj import CRS, Geod, Transformer

C_M_S = 299_792_458.0
GEOD = Geod(ellps="WGS84")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sa509_parameters(diameter_m: float, frequency_ghz: float, efficiency: float, multiple: bool) -> dict[str, float]:
    if diameter_m <= 0 or frequency_ghz <= 0 or not (0 < efficiency <= 1):
        raise ValueError("Invalid SA.509 physical parameter")
    wavelength_m = C_M_S / (frequency_ghz * 1e9)
    d_over_lambda = diameter_m / wavelength_m
    g0 = 10.0 * math.log10(efficiency * (math.pi * d_over_lambda) ** 2)
    phi0 = 20.0 * math.sqrt(3.0) / d_over_lambda
    drop = 20.0 if multiple else 17.0
    phi1 = phi0 * math.sqrt(drop / 3.0)
    phi2 = 10.0 ** ((49.0 - g0) / 25.0)
    if not (0 < phi0 < phi1 < phi2 < 48.0):
        raise ValueError(f"Unexpected SA.509 breakpoints: phi0={phi0}, phi1={phi1}, phi2={phi2}")
    return {
        "wavelength_m": wavelength_m,
        "d_over_lambda": d_over_lambda,
        "g0_dbi": g0,
        "phi0_deg": phi0,
        "phi1_deg": phi1,
        "phi2_deg": phi2,
    }


def sa509_gain(off_axis_deg: np.ndarray | float, params: dict[str, float], multiple: bool) -> np.ndarray:
    phi = np.asarray(off_axis_deg, dtype=float)
    if np.any(~np.isfinite(phi)) or np.any((phi < 0) | (phi > 180)):
        raise ValueError("Off-axis angles must be finite and within [0, 180] degrees")
    g0 = params["g0_dbi"]
    phi0 = params["phi0_deg"]
    phi1 = params["phi1_deg"]
    phi2 = params["phi2_deg"]
    result = np.empty_like(phi)
    first = phi < phi1
    second = (phi >= phi1) & (phi < phi2)
    third = (phi >= phi2) & (phi < 48.0)
    fourth = (phi >= 48.0) & (phi < 80.0)
    fifth = (phi >= 80.0) & (phi < 120.0)
    sixth = phi >= 120.0
    result[first] = g0 - 3.0 * (phi[first] / phi0) ** 2
    result[second] = g0 - (20.0 if multiple else 17.0)
    result[third] = (29.0 if multiple else 32.0) - 25.0 * np.log10(phi[third])
    if multiple:
        result[fourth] = -13.0
        result[fifth] = -8.0
        result[sixth] = -13.0
    else:
        result[fourth] = -10.0
        result[fifth] = -5.0
        result[sixth] = -10.0
    return result


def axial_hex_coordinates(radius: int = 2) -> list[tuple[int, int]]:
    coords = [
        (q, r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(q + r)) <= radius
    ]
    coords.sort(key=lambda qr: (max(abs(qr[0]), abs(qr[1]), abs(qr[0] + qr[1])), qr[1], qr[0]))
    return coords


def rotate_xy(x: float, y: float, angle_deg: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def local_layout(isd_m: float, center_distance_m: float, center_bearing_deg: float, rotation_deg: float) -> list[dict]:
    bearing = math.radians(center_bearing_deg)
    center_x = center_distance_m * math.sin(bearing)  # east
    center_y = center_distance_m * math.cos(bearing)  # north
    rows: list[dict] = []
    for index, (q, r) in enumerate(axial_hex_coordinates(2), start=1):
        x = isd_m * (q + 0.5 * r)
        y = isd_m * (math.sqrt(3.0) / 2.0 * r)
        x, y = rotate_xy(x, y, rotation_deg)
        x += center_x
        y += center_y
        ring = max(abs(q), abs(r), abs(q + r))
        rows.append({"site_index": index, "q": q, "r": r, "ring": ring, "east_m": x, "north_m": y})
    return rows


def angular_separation_deg(az1_deg: np.ndarray, el1_deg: np.ndarray, az2_deg: float, el2_deg: float) -> np.ndarray:
    az1 = np.radians(np.asarray(az1_deg, dtype=float))
    el1 = np.radians(np.asarray(el1_deg, dtype=float))
    az2 = math.radians(float(az2_deg))
    el2 = math.radians(float(el2_deg))
    u1 = np.column_stack((np.cos(el1) * np.sin(az1), np.cos(el1) * np.cos(az1), np.sin(el1)))
    u2 = np.array([math.cos(el2) * math.sin(az2), math.cos(el2) * math.cos(az2), math.sin(el2)])
    dots = np.clip(u1 @ u2, -1.0, 1.0)
    return np.degrees(np.arccos(dots))


def sample_raster(path: Path, points_lon_lat: Iterable[tuple[float, float]]) -> list[float]:
    try:
        import rasterio
        from rasterio.warp import transform
    except ImportError as exc:
        raise SystemExit("Install requirements-full.txt") from exc
    points = list(points_lon_lat)
    with rasterio.open(path) as src:
        if src.crs is None:
            raise RuntimeError("Layout MRDEM raster has no CRS")
        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        xs, ys = transform("EPSG:4326", src.crs, lons, lats)
        values: list[float] = []
        for sample in src.sample(list(zip(xs, ys)), masked=True):
            value = sample[0]
            if bool(getattr(value, "mask", False)):
                raise RuntimeError("A layout site samples a masked/out-of-coverage MRDEM cell; rerun with --force-mrdem")
            number = float(value)
            if not (-500.0 < number < 9000.0):
                raise RuntimeError(f"Implausible layout ground elevation: {number}")
            values.append(number)
    return values


def build_pattern_tables(diameter_m: float, frequency_ghz: float, efficiencies: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    fine = np.unique(np.concatenate((np.array([0.0]), np.linspace(0.001, 1.0, 1000), np.linspace(1.01, 10.0, 900), np.linspace(10.1, 180.0, 1700))))
    param_rows: list[dict] = []
    sample_rows: list[pd.DataFrame] = []
    for efficiency, multiple in itertools.product(efficiencies, [False, True]):
        params = sa509_parameters(diameter_m, frequency_ghz, efficiency, multiple)
        pattern_type = "multiple_entry_section_1_2" if multiple else "single_entry_section_1_1"
        param_rows.append({"aperture_efficiency": efficiency, "pattern_type": pattern_type, **params})
        sample_rows.append(pd.DataFrame({
            "off_axis_deg": fine,
            "gain_dbi": sa509_gain(fine, params, multiple),
            "aperture_efficiency": efficiency,
            "pattern_type": pattern_type,
        }))
    return pd.DataFrame(param_rows), pd.concat(sample_rows, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_pattern_layout.yaml")
    parser.add_argument("--root")
    parser.add_argument("--force-mrdem", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    config_path = root / args.config
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    inputs = {key: root / value for key, value in cfg["inputs"].items()}
    outputs = {key: root / value for key, value in cfg["outputs"].items()}
    for key in ["station_staging_csv", "station_source_record_json", "pass_selection_json", "selected_pass_track_csv", "sa509_pdf", "sa509_source_record_json"]:
        if not inputs[key].is_file():
            raise FileNotFoundError(inputs[key])
    station_df = pd.read_csv(inputs["station_staging_csv"])
    if len(station_df) != 1:
        raise ValueError("Earth-station staging CSV must contain exactly one row")
    station = station_df.iloc[0]
    station_lat = float(station["latitude_deg"])
    station_lon = float(station["longitude_deg"])
    station_alt = float(station["altitude_m_asl"])
    diameter = float(station["dish_diameter_m"])
    if not (-90 <= station_lat <= 90 and -180 <= station_lon <= 180):
        raise ValueError("Invalid station coordinate")
    pass_selection = json.loads(inputs["pass_selection_json"].read_text(encoding="utf-8"))
    if pass_selection.get("next_gate") != "EARTH_STATION_PATTERN_AND_CELLULAR_LAYOUT_FREEZE":
        raise ValueError("E3 intake did not finish at the expected next gate")
    track = pd.read_csv(inputs["selected_pass_track_csv"])
    required_track = {"time_utc", "time_s", "azimuth_deg", "elevation_deg", "slant_range_km"}
    if not required_track.issubset(track.columns) or track[list(required_track)].isna().any().any():
        raise ValueError("Selected pass track is incomplete")
    pattern_cfg = cfg["antenna_pattern"]
    layout_cfg = cfg["layout"]
    frequency_ghz = float(pattern_cfg["carrier_ghz"])
    efficiencies = [float(x) for x in pattern_cfg["aperture_efficiency_sensitivity"]]
    nominal_eff = float(pattern_cfg["aperture_efficiency_nominal"])
    if nominal_eff not in efficiencies:
        raise ValueError("Nominal efficiency must be in the sensitivity set")
    parameter_table, pattern_samples = build_pattern_tables(diameter, frequency_ghz, efficiencies)
    if parameter_table["d_over_lambda"].min() < float(pattern_cfg["require_d_over_lambda_at_least"]):
        raise ValueError("Dish does not meet SA.509 D/lambda applicability gate")
    layout_rows = local_layout(
        float(layout_cfg["inter_site_distance_m"]),
        float(layout_cfg["cluster_center_offset_from_station_m"]),
        float(layout_cfg["cluster_center_bearing_deg"]),
        float(layout_cfg["lattice_rotation_deg"]),
    )
    if len(layout_rows) != int(layout_cfg["site_count"]):
        raise ValueError("Layout does not contain the configured 19 sites")
    local_crs = CRS.from_proj4(f"+proj=aeqd +lat_0={station_lat} +lon_0={station_lon} +datum=WGS84 +units=m +no_defs")
    to_wgs = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True)
    for row in layout_rows:
        lon, lat = to_wgs.transform(row["east_m"], row["north_m"])
        row["longitude_deg"] = float(lon)
        row["latitude_deg"] = float(lat)
        row["site_id"] = f"E3_SITE_{row['site_index']:02d}"
        az12, _, distance = GEOD.inv(station_lon, station_lat, lon, lat)
        row["station_to_site_bearing_deg"] = float(az12 % 360.0)
        row["station_to_site_distance_m"] = float(distance)
    sites_pre = pd.DataFrame(layout_rows)
    min_distance = float(sites_pre["station_to_site_distance_m"].min())
    if min_distance < float(layout_cfg["minimum_baseline_site_to_station_m"]):
        raise ValueError(f"Nearest baseline site is too close to the station: {min_distance:.3f} m")
    review_dir = outputs["review_dir"]
    review_dir.mkdir(parents=True, exist_ok=True)
    extent_path = review_dir / "layout_extent.csv"
    pd.DataFrame([
        {"tx_lat_deg": row["latitude_deg"], "tx_lon_deg": row["longitude_deg"], "rx_lat_deg": station_lat, "rx_lon_deg": station_lon}
        for row in layout_rows
    ]).to_csv(extent_path, index=False)
    dem_path = inputs["layout_dem_subset"]
    dem_record = inputs["layout_dem_source_record"]
    if args.force_mrdem and dem_path.parent.exists():
        for path in dem_path.parent.iterdir():
            if path.is_file():
                path.unlink()
    if not dem_path.is_file():
        command = [
            sys.executable,
            str(root / "scripts/03_3_fetch_mrdem_dtm.py"),
            "--links", str(extent_path),
            "--out-dir", str(dem_path.parent),
            "--padding-deg", str(float(layout_cfg["mrdem_padding_deg"])),
        ]
        if args.force_mrdem:
            command.append("--force")
        subprocess.run(command, cwd=root, check=True)
    if not dem_path.is_file() or not dem_record.is_file():
        raise FileNotFoundError("MRDEM layout subset/source record is incomplete")
    elevations = sample_raster(dem_path, [(row["longitude_deg"], row["latitude_deg"]) for row in layout_rows])
    sites_pre["ground_elevation_m_asl"] = elevations
    sites_pre["antenna_height_m_agl"] = float(layout_cfg["bs_height_m_agl"])
    sites_pre["antenna_altitude_m_asl"] = sites_pre["ground_elevation_m_asl"] + sites_pre["antenna_height_m_agl"]
    sites_pre["source_or_model_status"] = str(layout_cfg["deployment_label"])
    sites_pre["provenance_note"] = "Deterministic two-tier hexagonal reference layout; ground elevation sampled from archived NRCan MRDEM DTM."
    site_columns = [
        "site_id", "site_index", "q", "r", "ring", "latitude_deg", "longitude_deg",
        "ground_elevation_m_asl", "antenna_height_m_agl", "antenna_altitude_m_asl",
        "east_m", "north_m", "station_to_site_distance_m", "station_to_site_bearing_deg",
        "source_or_model_status", "provenance_note",
    ]
    sites_pre = sites_pre[site_columns]
    sectors: list[dict] = []
    for site in sites_pre.to_dict(orient="records"):
        for sector_index, azimuth in enumerate(layout_cfg["sector_azimuths_deg"], start=1):
            sectors.append({
                "sector_id": f"{site['site_id']}_SEC_{sector_index}",
                "site_id": site["site_id"],
                "latitude_deg": site["latitude_deg"],
                "longitude_deg": site["longitude_deg"],
                "ground_elevation_m_asl": site["ground_elevation_m_asl"],
                "antenna_height_m_agl": site["antenna_height_m_agl"],
                "azimuth_deg": float(azimuth),
                "downtilt_deg": float(layout_cfg["downtilt_deg_nominal"]),
                "array_rows": int(layout_cfg["array_rows"]),
                "array_cols": int(layout_cfg["array_cols"]),
                "element_gain_dbi": float(layout_cfg["element_gain_dbi"]),
                "conducted_power_dbm_per_100mhz": float(layout_cfg["conducted_power_dbm_per_100mhz"]),
                "activity_factor": float(layout_cfg["activity_factor_full_scale"]),
                "source_or_model_status": str(layout_cfg["deployment_label"]),
                "provenance_note": "Sector orientation/power/array values are declared study parameters, not operator deployment facts.",
            })
    sectors_df = pd.DataFrame(sectors)
    if len(sectors_df) != int(layout_cfg["site_count"]) * int(layout_cfg["sectors_per_site"]):
        raise ValueError("Sector count is not 57")
    parameter_table.to_csv(review_dir / "earth_station_pattern_parameters.csv", index=False)
    pattern_samples.to_csv(review_dir / "earth_station_pattern_samples.csv", index=False)
    sites_pre.to_csv(review_dir / "bs_sites_review.csv", index=False)
    sectors_df.to_csv(review_dir / "bs_sectors_review.csv", index=False)
    sensitivity_rows = [
        {"cluster_center_offset_from_station_m": d, "cluster_center_bearing_deg": b, "lattice_rotation_deg": r, "phase_center_height_m_agl": h}
        for d, b, r, h in itertools.product(
            layout_cfg["sensitivity_grid"]["cluster_center_offset_from_station_m"],
            layout_cfg["sensitivity_grid"]["cluster_center_bearing_deg"],
            layout_cfg["sensitivity_grid"]["lattice_rotation_deg"],
            layout_cfg["sensitivity_grid"]["phase_center_height_m_agl"],
        )
    ]
    pd.DataFrame(sensitivity_rows).to_csv(review_dir / "layout_sensitivity_grid.csv", index=False)
    nominal_params = parameter_table[(parameter_table["aperture_efficiency"] == nominal_eff) & (parameter_table["pattern_type"] == "multiple_entry_section_1_2")].iloc[0]
    station_final = station_df.copy()
    station_final.loc[0, "dish_gain_dbi"] = float(nominal_params["g0_dbi"])
    station_final.loc[0, "antenna_pattern_source"] = "ITU-R SA.509-3 section 1.2 reference aggregate pattern; model efficiency 0.65"
    station_final.loc[0, "field_status"] = "PUBLIC_SITE_AND_DISH_DIAMETER__MODELLED_COORDINATE_PHASE_CENTER_PATTERN_AND_EFFICIENCY"
    station_final.loc[0, "provenance_note"] = (
        str(station_final.loc[0, "provenance_note"]) + " SA.509 is used as a reference model in the absence of measured pattern data, not as an EESS-specific mandate."
    )
    station_final.to_csv(review_dir / "earth_station_model_review.csv", index=False)
    # Pattern plot
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for pattern_type, style in [("multiple_entry_section_1_2", "-"), ("single_entry_section_1_1", "--")]:
        part = pattern_samples[(pattern_samples["aperture_efficiency"] == nominal_eff) & (pattern_samples["pattern_type"] == pattern_type)]
        label = "aggregate/multiple-entry" if "multiple" in pattern_type else "single-entry sensitivity"
        axes[0].plot(part["off_axis_deg"], part["gain_dbi"], linestyle=style, label=label)
        axes[1].semilogx(part.loc[part["off_axis_deg"] > 0, "off_axis_deg"], part.loc[part["off_axis_deg"] > 0, "gain_dbi"], linestyle=style, label=label)
    axes[0].set_xlim(0, 2)
    axes[0].set_xlabel("Off-axis angle (deg)")
    axes[0].set_ylabel("Reference receive gain (dBi)")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()
    axes[1].set_xlim(0.01, 180)
    axes[1].set_xlabel("Off-axis angle (deg, log scale)")
    axes[1].set_ylabel("Reference receive gain (dBi)")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()
    fig.suptitle("E3 reference earth-station pattern: ITU-R SA.509-3, nominal efficiency 0.65")
    fig.tight_layout()
    fig.savefig(review_dir / "earth_station_pattern_review.png", dpi=180)
    plt.close(fig)
    # Layout plot
    fig, ax = plt.subplots(figsize=(7.2, 7.2))
    ax.scatter([0], [0], marker="*", s=180, label="reference earth station")
    ax.scatter(sites_pre["east_m"], sites_pre["north_m"], label="modelled sites")
    for _, row in sites_pre.iterrows():
        ax.text(row["east_m"] + 30, row["north_m"] + 30, row["site_id"], fontsize=6)
    arrow_length = 170.0
    for _, row in sectors_df.iterrows():
        site = sites_pre[sites_pre["site_id"] == row["site_id"]].iloc[0]
        a = math.radians(float(row["azimuth_deg"]))
        ax.arrow(site["east_m"], site["north_m"], arrow_length * math.sin(a), arrow_length * math.cos(a), width=3, head_width=30, length_includes_head=True, alpha=0.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("East from reference station (m)")
    ax.set_ylabel("North from reference station (m)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_title("Modelled 19-site / 57-sector E3 reference layout")
    fig.tight_layout()
    fig.savefig(review_dir / "e3_layout_review.png", dpi=180)
    plt.close(fig)
    # GeoJSON
    features = [{"type": "Feature", "properties": {"kind": "earth_station", "station_id": str(station["station_id"])}, "geometry": {"type": "Point", "coordinates": [station_lon, station_lat]}}]
    for row in sites_pre.to_dict(orient="records"):
        features.append({"type": "Feature", "properties": {"kind": "modelled_bs_site", "site_id": row["site_id"], "distance_m": row["station_to_site_distance_m"]}, "geometry": {"type": "Point", "coordinates": [row["longitude_deg"], row["latitude_deg"]]}})
    write_json(review_dir / "e3_layout.geojson", {"type": "FeatureCollection", "features": features})
    # Dynamic off-axis summary restricted to the protected tracking window.
    minimum_elevation_deg = float(station["minimum_elevation_deg"])
    protected_mask = track["elevation_deg"].to_numpy(float) >= minimum_elevation_deg
    protected_indices = np.flatnonzero(protected_mask)
    if protected_indices.size < 2:
        raise ValueError("Protected tracking window has fewer than two samples")
    if np.any(np.diff(protected_indices) != 1):
        raise ValueError("Protected tracking window is not one contiguous segment")
    protected_track = track.loc[protected_mask].copy().reset_index(drop=True)
    summaries: list[dict] = []
    for site in sites_pre.to_dict(orient="records"):
        horizontal = float(site["station_to_site_distance_m"])
        elevation_to_site = math.degrees(math.atan2(float(site["antenna_altitude_m_asl"]) - station_alt, horizontal))
        off_axis = angular_separation_deg(
            protected_track["azimuth_deg"].to_numpy(float),
            protected_track["elevation_deg"].to_numpy(float),
            float(site["station_to_site_bearing_deg"]),
            elevation_to_site,
        )
        nominal_gain = sa509_gain(off_axis, dict(nominal_params), multiple=True)
        min_index = int(np.argmin(off_axis))
        max_gain_index = int(np.argmax(nominal_gain))
        for sector_index in range(1, int(layout_cfg["sectors_per_site"]) + 1):
            summaries.append({
                "site_id": site["site_id"],
                "sector_id": f"{site['site_id']}_SEC_{sector_index}",
                "station_to_site_bearing_deg": site["station_to_site_bearing_deg"],
                "station_to_site_distance_m": horizontal,
                "station_to_site_elevation_deg": elevation_to_site,
                "protected_minimum_elevation_deg": minimum_elevation_deg,
                "protected_window_sample_count": int(len(protected_track)),
                "protected_window_start_utc": str(protected_track.iloc[0]["time_utc"]),
                "protected_window_end_utc": str(protected_track.iloc[-1]["time_utc"]),
                "minimum_off_axis_deg_during_protected_window": float(np.min(off_axis)),
                "minimum_off_axis_time_utc": str(protected_track.iloc[min_index]["time_utc"]),
                "median_off_axis_deg_during_protected_window": float(np.median(off_axis)),
                "maximum_reference_gain_dbi_during_protected_window": float(np.max(nominal_gain)),
                "maximum_reference_gain_time_utc": str(protected_track.iloc[max_gain_index]["time_utc"]),
                "selection_window": "earth_station_elevation_ge_minimum_elevation",
                # Backward-compatible aliases now explicitly represent the protected window.
                "minimum_off_axis_deg_during_selected_track": float(np.min(off_axis)),
                "median_off_axis_deg_during_selected_track": float(np.median(off_axis)),
                "maximum_reference_gain_dbi_during_selected_track": float(np.max(nominal_gain)),
            })
    summary_frame = pd.DataFrame(summaries)
    summary_frame.to_csv(review_dir / "selected_pass_off_axis_summary.csv", index=False)
    summary_frame.to_csv(review_dir / "selected_pass_off_axis_summary_protected.csv", index=False)
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN" if args.confirm else "REVIEW_REQUIRED",
        "config_sha256": sha256_file(config_path),
        "station_staging_sha256": sha256_file(inputs["station_staging_csv"]),
        "pass_selection_sha256": sha256_file(inputs["pass_selection_json"]),
        "selected_track_sha256": sha256_file(inputs["selected_pass_track_csv"]),
        "sa509_pdf_sha256": sha256_file(inputs["sa509_pdf"]),
        "sa509_source_record_sha256": sha256_file(inputs["sa509_source_record_json"]),
        "layout_dem_sha256": sha256_file(dem_path),
        "layout_dem_source_record_sha256": sha256_file(dem_record),
        "pattern": {
            "recommendation": pattern_cfg["recommendation"],
            "use_status": pattern_cfg["use_status"],
            "diameter_m": diameter,
            "carrier_ghz": frequency_ghz,
            "nominal_efficiency": nominal_eff,
            "sensitivity_efficiencies": efficiencies,
            "nominal_g0_dbi": float(nominal_params["g0_dbi"]),
            "nominal_phi0_deg": float(nominal_params["phi0_deg"]),
            "d_over_lambda": float(nominal_params["d_over_lambda"]),
        },
        "layout": {
            "site_count": int(len(sites_pre)),
            "sector_count": int(len(sectors_df)),
            "minimum_site_to_station_m": min_distance,
            "maximum_site_to_station_m": float(sites_pre["station_to_site_distance_m"].max()),
            "cluster_center_offset_from_station_m": float(layout_cfg["cluster_center_offset_from_station_m"]),
            "cluster_center_bearing_deg": float(layout_cfg["cluster_center_bearing_deg"]),
            "lattice_rotation_deg": float(layout_cfg["lattice_rotation_deg"]),
            "deployment_status": layout_cfg["deployment_label"],
        },
        "manual_confirmations": cfg["manual_confirmations"],
        "open_items": [
            "Independent external spot-check of selected pass geometry before paper use.",
            "First cellular-sector-to-earth-station P.452 path and gain-accounting audit.",
            "Final BS composite antenna/beam model for the paper-grade controller.",
        ],
        "claim_boundary": (
            "The station coordinate, phase centre, aperture efficiency, antenna pattern, and cellular layout include explicit model decisions. "
            "The layout is not an operator deployment, and SA.509 is a reference pattern rather than an EESS-specific mandate."
        ),
        "next_gate": "FIRST_CELLULAR_SECTOR_TO_EARTH_STATION_P452_PATH",
    }
    confirmations = cfg["manual_confirmations"]
    if args.confirm:
        false_items = [key for key, value in confirmations.items() if value is not True]
        if false_items:
            raise ValueError(f"Cannot freeze; manual confirmations remain false: {false_items}")
        outputs["final_station_csv"].parent.mkdir(parents=True, exist_ok=True)
        station_final.to_csv(outputs["final_station_csv"], index=False)
        sites_pre.to_csv(outputs["final_sites_csv"], index=False)
        sectors_df.to_csv(outputs["final_sectors_csv"], index=False)
        write_json(outputs["decision_json"], audit)
        outputs["decision_md"].write_text(
            "# E3 Pattern and Layout Decision\n\n"
            "Status: FROZEN\n\n"
            f"- Sites: {len(sites_pre)}\n- Sectors: {len(sectors_df)}\n"
            f"- Nearest modelled site: {min_distance:.3f} m\n"
            f"- Nominal SA.509 aggregate-pattern boresight gain: {float(nominal_params['g0_dbi']):.6f} dBi\n"
            "- Pattern status: reference model in the absence of measured data; not an EESS-specific mandate.\n"
            "- Layout status: deterministic modelled UMa reference; not an operator deployment.\n"
            "- Next gate: first cellular-sector-to-earth-station P.452 path.\n",
            encoding="utf-8",
        )
    write_json(review_dir / "E3_PATTERN_LAYOUT_AUDIT.json", audit)
    checklist = review_dir / "E3_PATTERN_LAYOUT_REVIEW_CHECKLIST.md"
    checklist.write_text(
        "# E3 Pattern/Layout Review Checklist\n\n"
        "Before setting manual confirmations to true, review:\n\n"
        "- the previously selected pass-elevation plot;\n"
        "- the public/non-survey station-coordinate limitation;\n"
        "- the SA.509 reference-model scope and the fact that it is not an EESS-specific mandate;\n"
        "- the unmeasured aperture-efficiency sensitivity grid;\n"
        "- the modelled 19-site layout and its nearest-site distance;\n"
        "- all site ground elevations and phase-centre altitudes;\n"
        "- the pattern and layout plots and GeoJSON;\n"
        "- that no operator deployment claim is being made.\n",
        encoding="utf-8",
    )
    print("E3 PATTERN/LAYOUT PREPARATION: PASS")
    print(f"Sites: {len(sites_pre)}")
    print(f"Sectors: {len(sectors_df)}")
    print(f"Nearest site: {min_distance:.3f} m")
    print(f"Farthest site: {float(sites_pre['station_to_site_distance_m'].max()):.3f} m")
    print(f"D/lambda: {float(nominal_params['d_over_lambda']):.3f}")
    print(f"Nominal aggregate-pattern G0: {float(nominal_params['g0_dbi']):.6f} dBi")
    if args.confirm:
        print("E3 PATTERN/LAYOUT FREEZE: PASS")
        print("Next gate: first cellular-sector-to-earth-station P.452 path")
    else:
        print("REVIEW REQUIRED: no final station/layout files were frozen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
