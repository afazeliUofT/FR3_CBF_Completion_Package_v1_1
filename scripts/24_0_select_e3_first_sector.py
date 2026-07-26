#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pandas as pd
from pyproj import Geod


ROOT = Path(__file__).resolve().parents[1]
GEOD = Geod(ellps="WGS84")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_columns(
    frame: pd.DataFrame,
    required: set[str],
    label: str,
) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def unit_vector(
    azimuth_deg: float,
    elevation_deg: float,
) -> tuple[float, float, float]:
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
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def main() -> int:
    station_path = ROOT / "data/real/earth_station.csv"
    sites_path = ROOT / "data/real/bs_sites.csv"
    sectors_path = ROOT / "data/real/bs_sectors.csv"
    offaxis_path = (
        ROOT
        / "data/real/e3_pattern_layout_review"
        / "selected_pass_off_axis_summary.csv"
    )
    output_dir = ROOT / "data/real/e3_first_sector_audit"

    for path in [
        station_path,
        sites_path,
        sectors_path,
        offaxis_path,
    ]:
        if not path.is_file():
            raise FileNotFoundError(path)

    station_frame = pd.read_csv(station_path)
    sites = pd.read_csv(sites_path)
    sectors = pd.read_csv(sectors_path)
    offaxis = pd.read_csv(offaxis_path)

    if len(station_frame) != 1:
        raise ValueError("earth_station.csv must contain exactly one row")
    if len(sites) != 19 or sites["site_id"].nunique() != 19:
        raise ValueError("Expected exactly 19 unique sites")
    if len(sectors) != 57 or sectors["sector_id"].nunique() != 57:
        raise ValueError("Expected exactly 57 unique sectors")
    if len(offaxis) != 57 or offaxis["sector_id"].nunique() != 57:
        raise ValueError(
            "Expected exactly 57 unique off-axis summary rows"
        )

    require_columns(
        station_frame,
        {
            "station_id",
            "latitude_deg",
            "longitude_deg",
            "altitude_m_asl",
        },
        "earth_station.csv",
    )
    require_columns(
        sites,
        {
            "site_id",
            "latitude_deg",
            "longitude_deg",
            "antenna_altitude_m_asl",
        },
        "bs_sites.csv",
    )
    require_columns(
        sectors,
        {
            "sector_id",
            "site_id",
            "azimuth_deg",
            "downtilt_deg",
        },
        "bs_sectors.csv",
    )
    require_columns(
        offaxis,
        {
            "site_id",
            "sector_id",
            "station_to_site_distance_m",
            "minimum_off_axis_deg_during_selected_track",
            "maximum_reference_gain_dbi_during_selected_track",
        },
        "selected_pass_off_axis_summary.csv",
    )

    for column in [
        "station_to_site_distance_m",
        "minimum_off_axis_deg_during_selected_track",
        "maximum_reference_gain_dbi_during_selected_track",
    ]:
        values = pd.to_numeric(offaxis[column], errors="coerce")
        if values.isna().any():
            raise ValueError(f"Invalid off-axis column: {column}")

    site_consistency = offaxis.groupby("site_id").agg(
        distance_count=("station_to_site_distance_m", "nunique"),
        minimum_count=(
            "minimum_off_axis_deg_during_selected_track",
            "nunique",
        ),
        gain_count=(
            "maximum_reference_gain_dbi_during_selected_track",
            "nunique",
        ),
    )

    if (site_consistency > 1).any().any():
        raise ValueError(
            "Site-level off-axis values are inconsistent among sectors"
        )

    site_scores = (
        offaxis.groupby("site_id", as_index=False)
        .agg(
            minimum_off_axis_deg=(
                "minimum_off_axis_deg_during_selected_track",
                "first",
            ),
            maximum_reference_gain_dbi=(
                "maximum_reference_gain_dbi_during_selected_track",
                "first",
            ),
            station_to_site_distance_m=(
                "station_to_site_distance_m",
                "first",
            ),
        )
        .sort_values(
            [
                "minimum_off_axis_deg",
                "station_to_site_distance_m",
                "site_id",
            ],
            kind="mergesort",
        )
    )

    selected_site_id = str(site_scores.iloc[0]["site_id"])
    site_rows = sites.loc[
        sites["site_id"].astype(str) == selected_site_id
    ]

    if len(site_rows) != 1:
        raise ValueError(
            f"Selected site is not unique: {selected_site_id}"
        )

    site = site_rows.iloc[0]
    station = station_frame.iloc[0]

    site_lon = float(site["longitude_deg"])
    site_lat = float(site["latitude_deg"])
    station_lon = float(station["longitude_deg"])
    station_lat = float(station["latitude_deg"])

    azimuth_to_station, _, distance_m = GEOD.inv(
        site_lon,
        site_lat,
        station_lon,
        station_lat,
    )
    azimuth_to_station %= 360.0

    elevation_to_station_deg = math.degrees(
        math.atan2(
            float(station["altitude_m_asl"])
            - float(site["antenna_altitude_m_asl"]),
            distance_m,
        )
    )

    site_sectors = sectors.loc[
        sectors["site_id"].astype(str) == selected_site_id
    ]

    if len(site_sectors) != 3:
        raise ValueError(
            f"Expected three sectors at {selected_site_id}; "
            f"found {len(site_sectors)}"
        )

    candidate_rows: list[dict[str, object]] = []

    for _, sector in site_sectors.iterrows():
        sector_azimuth = float(sector["azimuth_deg"])
        boresight_elevation = -float(sector["downtilt_deg"])

        candidate_rows.append(
            {
                "sector_id": str(sector["sector_id"]),
                "site_id": selected_site_id,
                "site_to_station_azimuth_deg":
                    azimuth_to_station,
                "site_to_station_elevation_deg":
                    elevation_to_station_deg,
                "sector_azimuth_deg": sector_azimuth,
                "sector_boresight_elevation_deg":
                    boresight_elevation,
                "boresight_to_station_angle_deg":
                    separation_deg(
                        sector_azimuth,
                        boresight_elevation,
                        azimuth_to_station,
                        elevation_to_station_deg,
                    ),
            }
        )

    candidates = pd.DataFrame(candidate_rows).sort_values(
        ["boresight_to_station_angle_deg", "sector_id"],
        kind="mergesort",
    )

    selected = candidates.iloc[0].to_dict()
    selected.update(
        {
            "station_id": str(station["station_id"]),
            "selection_rule": (
                "Select the site with the minimum earth-station "
                "off-axis angle during the frozen pass; break ties "
                "by shorter station distance and site_id. At that "
                "site, select the sector with minimum 3-D "
                "boresight-to-station angle."
            ),
            "claim_boundary": (
                "Pipeline-audit sector only. It is not yet called "
                "the globally worst-coupled sector because P.452 "
                "loss and final composite BS gain have not yet "
                "been evaluated."
            ),
            "minimum_earth_station_off_axis_deg":
                float(
                    site_scores.iloc[0][
                        "minimum_off_axis_deg"
                    ]
                ),
            "maximum_reference_earth_station_gain_dbi":
                float(
                    site_scores.iloc[0][
                        "maximum_reference_gain_dbi"
                    ]
                ),
            "distance_m": float(distance_m),
            "input_sha256": {
                str(station_path.relative_to(ROOT)):
                    sha256_file(station_path),
                str(sites_path.relative_to(ROOT)):
                    sha256_file(sites_path),
                str(sectors_path.relative_to(ROOT)):
                    sha256_file(sectors_path),
                str(offaxis_path.relative_to(ROOT)):
                    sha256_file(offaxis_path),
            },
        }
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    candidates.to_csv(
        output_dir / "sector_candidates.csv",
        index=False,
    )

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
        "tx_antenna_alt_m_asl":
            float(site["antenna_altitude_m_asl"]),
        "rx_antenna_alt_m_asl":
            float(station["altitude_m_asl"]),
        "mean_terrain_elevation_m_asl": float("nan"),
        "provenance_note": (
            "Modelled E3 first-sector P.452 pipeline audit; "
            "uses frozen E3 station, pattern, pass, and layout; "
            "not a paper result."
        ),
    }

    pd.DataFrame([link_row]).to_csv(
        output_dir / "first_sector_link_input.csv",
        index=False,
    )

    print("E3 FIRST-SECTOR SELECTION: PASS")
    print("Selected site:", selected_site_id)
    print("Selected sector:", selected["sector_id"])
    print("Distance (m):", f"{distance_m:.6f}")
    print(
        "Boresight-to-station angle (deg):",
        f"{selected['boresight_to_station_angle_deg']:.6f}",
    )
    print(
        "Minimum ES off-axis during pass (deg):",
        f"{selected['minimum_earth_station_off_axis_deg']:.6f}",
    )
    print("Output directory:", output_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
