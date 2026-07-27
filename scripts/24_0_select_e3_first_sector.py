#!/usr/bin/env python3
"""Select the first E3 audit sector using the protected tracking window only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import yaml
from pyproj import Geod

GEOD = Geod(ellps="WGS84")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def unit_vector(azimuth_deg: float, elevation_deg: float) -> tuple[float, float, float]:
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    return (
        math.cos(elevation) * math.sin(azimuth),
        math.cos(elevation) * math.cos(azimuth),
        math.sin(elevation),
    )


def separation_deg(
    azimuth_1_deg: float,
    elevation_1_deg: float,
    azimuth_2_deg: float,
    elevation_2_deg: float,
) -> float:
    first = unit_vector(azimuth_1_deg, elevation_1_deg)
    second = unit_vector(azimuth_2_deg, elevation_2_deg)
    dot = sum(a * b for a, b in zip(first, second))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_protected_window_correction.yaml")
    parser.add_argument("--root")
    parser.add_argument("--output-dir", default="data/real/e3_first_sector_audit")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / args.config).read_text(encoding="utf-8"))
    inputs = cfg["inputs"]
    outputs = cfg["outputs"]
    expected = cfg["expected"]

    station_path = root / inputs["station_csv"]
    sites_path = root / inputs["sites_csv"]
    sectors_path = root / inputs["sectors_csv"]
    protected_summary_path = root / outputs["protected_summary_csv"]
    correction_path = root / outputs["correction_json"]
    output_dir = root / args.output_dir

    for path in [station_path, sites_path, sectors_path, protected_summary_path, correction_path]:
        if not path.is_file():
            raise FileNotFoundError(path)

    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    if correction.get("status") != "CORRECTED_PROTECTED_WINDOW_SUMMARY_READY":
        raise ValueError("Protected-window correction is not in the expected ready state")
    if correction.get("next_gate") != "RESELECT_FIRST_SECTOR_USING_PROTECTED_WINDOW":
        raise ValueError("Protected-window correction has an unexpected next gate")

    station_frame = pd.read_csv(station_path)
    sites = pd.read_csv(sites_path)
    sectors = pd.read_csv(sectors_path)
    summary = pd.read_csv(protected_summary_path)

    if len(station_frame) != 1:
        raise ValueError("Earth-station table must contain exactly one row")
    if len(sites) != int(expected["site_count"]) or sites["site_id"].nunique() != len(sites):
        raise ValueError("Unexpected site population")
    if len(sectors) != int(expected["sector_count"]) or sectors["sector_id"].nunique() != len(sectors):
        raise ValueError("Unexpected sector population")
    if len(summary) != int(expected["sector_count"]) or summary["sector_id"].nunique() != len(summary):
        raise ValueError("Protected-window summary is not a unique 57-sector table")

    require_columns(
        summary,
        {
            "site_id", "sector_id", "station_to_site_distance_m",
            "minimum_off_axis_deg_during_protected_window",
            "maximum_reference_gain_dbi_during_protected_window",
            "protected_minimum_elevation_deg", "protected_window_sample_count",
            "protected_window_start_utc", "protected_window_end_utc",
            "selection_window",
        },
        "protected-window summary",
    )
    if set(summary["selection_window"].astype(str)) != {
        "earth_station_elevation_ge_minimum_elevation"
    }:
        raise ValueError("Summary selection_window is not protected-window only")

    station = station_frame.iloc[0]
    minimum_elevation = float(station["minimum_elevation_deg"])
    if not (
        pd.to_numeric(summary["protected_minimum_elevation_deg"], errors="coerce")
        .sub(minimum_elevation)
        .abs()
        .le(1e-12)
        .all()
    ):
        raise ValueError("Protected summary uses an inconsistent minimum elevation")

    site_consistency = summary.groupby("site_id").agg(
        distance_count=("station_to_site_distance_m", "nunique"),
        off_axis_count=("minimum_off_axis_deg_during_protected_window", "nunique"),
        gain_count=("maximum_reference_gain_dbi_during_protected_window", "nunique"),
        start_count=("protected_window_start_utc", "nunique"),
        end_count=("protected_window_end_utc", "nunique"),
        sample_count=("protected_window_sample_count", "nunique"),
    )
    if (site_consistency > 1).any().any():
        raise ValueError("Site-level protected-window values differ among co-located sectors")

    site_scores = (
        summary.groupby("site_id", as_index=False)
        .agg(
            minimum_off_axis_deg=(
                "minimum_off_axis_deg_during_protected_window",
                "first",
            ),
            maximum_reference_gain_dbi=(
                "maximum_reference_gain_dbi_during_protected_window",
                "first",
            ),
            station_to_site_distance_m=("station_to_site_distance_m", "first"),
            protected_window_sample_count=("protected_window_sample_count", "first"),
            protected_window_start_utc=("protected_window_start_utc", "first"),
            protected_window_end_utc=("protected_window_end_utc", "first"),
        )
        .sort_values(
            ["minimum_off_axis_deg", "station_to_site_distance_m", "site_id"],
            kind="mergesort",
        )
    )
    selected_site_id = str(site_scores.iloc[0]["site_id"])
    if selected_site_id != str(expected["corrected_selected_site_id"]):
        raise ValueError(
            f"Protected-window site selection is {selected_site_id}; "
            f"expected {expected['corrected_selected_site_id']}"
        )

    site_rows = sites.loc[sites["site_id"].astype(str) == selected_site_id]
    if len(site_rows) != 1:
        raise ValueError("Selected site is not unique")
    site = site_rows.iloc[0]

    station_lon = float(station["longitude_deg"])
    station_lat = float(station["latitude_deg"])
    site_lon = float(site["longitude_deg"])
    site_lat = float(site["latitude_deg"])
    azimuth_to_station, _, distance_m = GEOD.inv(
        site_lon, site_lat, station_lon, station_lat
    )
    azimuth_to_station %= 360.0
    elevation_to_station = math.degrees(
        math.atan2(
            float(station["altitude_m_asl"]) - float(site["antenna_altitude_m_asl"]),
            distance_m,
        )
    )

    site_sectors = sectors.loc[sectors["site_id"].astype(str) == selected_site_id]
    if len(site_sectors) != int(expected["sectors_per_site"]):
        raise ValueError("Selected site does not have the expected three sectors")

    candidates: list[dict[str, object]] = []
    for _, sector in site_sectors.iterrows():
        boresight_elevation = -float(sector["downtilt_deg"])
        candidates.append(
            {
                "sector_id": str(sector["sector_id"]),
                "site_id": selected_site_id,
                "site_to_station_azimuth_deg": float(azimuth_to_station),
                "site_to_station_elevation_deg": float(elevation_to_station),
                "sector_azimuth_deg": float(sector["azimuth_deg"]),
                "sector_boresight_elevation_deg": float(boresight_elevation),
                "boresight_to_station_angle_deg": separation_deg(
                    float(sector["azimuth_deg"]),
                    boresight_elevation,
                    azimuth_to_station,
                    elevation_to_station,
                ),
            }
        )
    candidate_frame = pd.DataFrame(candidates).sort_values(
        ["boresight_to_station_angle_deg", "sector_id"],
        kind="mergesort",
    )
    selected = candidate_frame.iloc[0].to_dict()

    if str(selected["sector_id"]) != str(expected["corrected_selected_sector_id"]):
        raise ValueError(
            f"Protected-window sector selection is {selected['sector_id']}; "
            f"expected {expected['corrected_selected_sector_id']}"
        )

    winning_site = site_scores.iloc[0]
    selected.update(
        {
            "station_id": str(station["station_id"]),
            "selection_rule": (
                "Within samples where earth-station elevation is at or above the "
                "declared minimum elevation, select the site with the minimum "
                "earth-station off-axis angle; tie-break by shorter distance and "
                "site_id. At that site select the sector with minimum 3-D "
                "boresight-to-station angle."
            ),
            "selection_window": "earth_station_elevation_ge_minimum_elevation",
            "minimum_elevation_deg": minimum_elevation,
            "protected_window_sample_count": int(winning_site["protected_window_sample_count"]),
            "protected_window_start_utc": str(winning_site["protected_window_start_utc"]),
            "protected_window_end_utc": str(winning_site["protected_window_end_utc"]),
            "minimum_earth_station_off_axis_deg": float(winning_site["minimum_off_axis_deg"]),
            "maximum_reference_earth_station_gain_dbi": float(
                winning_site["maximum_reference_gain_dbi"]
            ),
            "distance_m": float(distance_m),
            "supersedes_sector_id": str(expected["superseded_sector_id"]),
            "claim_boundary": (
                "Corrected protected-window pipeline-audit sector only. It is not "
                "yet called the globally worst-coupled sector because P.452 loss "
                "and the final composite BS beam gain have not yet been evaluated."
            ),
            "input_sha256": {
                str(path.relative_to(root)): sha256_file(path)
                for path in [
                    station_path, sites_path, sectors_path,
                    protected_summary_path, correction_path,
                ]
            },
        }
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_frame.to_csv(output_dir / "sector_candidates.csv", index=False)
    (output_dir / "selected_sector.json").write_text(
        json.dumps(selected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    link_row = {
        "link_id": str(selected["sector_id"]),
        "tx_lat_deg": site_lat,
        "tx_lon_deg": site_lon,
        "rx_lat_deg": station_lat,
        "rx_lon_deg": station_lon,
        "tx_antenna_alt_m_asl": float(site["antenna_altitude_m_asl"]),
        "rx_antenna_alt_m_asl": float(station["altitude_m_asl"]),
        "mean_terrain_elevation_m_asl": float("nan"),
        "provenance_note": (
            "Corrected protected-window E3 first-sector P.452 pipeline audit; "
            "uses the frozen station, protected pass, pattern, and layout; "
            "not a paper result."
        ),
    }
    pd.DataFrame([link_row]).to_csv(
        output_dir / "first_sector_link_input.csv",
        index=False,
    )

    print("E3 PROTECTED-WINDOW FIRST-SECTOR SELECTION: PASS")
    print("Selected site:", selected_site_id)
    print("Selected sector:", selected["sector_id"])
    print("Superseded sector:", expected["superseded_sector_id"])
    print("Protected start:", selected["protected_window_start_utc"])
    print("Protected end:", selected["protected_window_end_utc"])
    print("Protected samples:", selected["protected_window_sample_count"])
    print("Minimum protected ES off-axis (deg):", f"{selected['minimum_earth_station_off_axis_deg']:.9f}")
    print("Maximum protected ES gain (dBi):", f"{selected['maximum_reference_earth_station_gain_dbi']:.9f}")
    print("Distance (m):", f"{distance_m:.6f}")
    print("Output directory:", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
