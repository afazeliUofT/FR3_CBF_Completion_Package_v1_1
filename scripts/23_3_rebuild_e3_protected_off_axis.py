#!/usr/bin/env python3
"""Rebuild the E3 off-axis summary using only the protected tracking window.

The original summary used every sample in the detailed track, including margins
below the declared 5-degree minimum elevation.  This script preserves that
historical file and writes a separate protected-window summary plus an audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
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


def angular_separation_deg(
    azimuth_1_deg: np.ndarray,
    elevation_1_deg: np.ndarray,
    azimuth_2_deg: float,
    elevation_2_deg: float,
) -> np.ndarray:
    az1 = np.radians(np.asarray(azimuth_1_deg, dtype=float))
    el1 = np.radians(np.asarray(elevation_1_deg, dtype=float))
    az2 = math.radians(float(azimuth_2_deg))
    el2 = math.radians(float(elevation_2_deg))
    dot = (
        np.cos(el1) * math.cos(el2) * np.cos(az1 - az2)
        + np.sin(el1) * math.sin(el2)
    )
    return np.degrees(np.arccos(np.clip(dot, -1.0, 1.0)))


def sa509_gain(
    off_axis_deg: np.ndarray,
    params: pd.Series,
    *,
    multiple_entry: bool,
) -> np.ndarray:
    phi = np.asarray(off_axis_deg, dtype=float)
    if np.any(~np.isfinite(phi)) or np.any((phi < 0) | (phi > 180)):
        raise ValueError("Off-axis angles must be finite and in [0, 180] degrees")
    g0 = float(params["g0_dbi"])
    phi0 = float(params["phi0_deg"])
    phi1 = float(params["phi1_deg"])
    phi2 = float(params["phi2_deg"])
    result = np.empty_like(phi)
    first = phi < phi1
    second = (phi >= phi1) & (phi < phi2)
    third = (phi >= phi2) & (phi < 48.0)
    fourth = (phi >= 48.0) & (phi < 80.0)
    fifth = (phi >= 80.0) & (phi < 120.0)
    sixth = phi >= 120.0
    result[first] = g0 - 3.0 * (phi[first] / phi0) ** 2
    result[second] = g0 - (20.0 if multiple_entry else 17.0)
    result[third] = (29.0 if multiple_entry else 32.0) - 25.0 * np.log10(phi[third])
    if multiple_entry:
        result[fourth] = -13.0
        result[fifth] = -8.0
        result[sixth] = -13.0
    else:
        result[fourth] = -10.0
        result[fifth] = -5.0
        result[sixth] = -10.0
    return result


def require_columns(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_protected_window_correction.yaml")
    parser.add_argument("--root")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    config_path = root / args.config
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    inputs = {key: root / value for key, value in cfg["inputs"].items()}
    outputs = {key: root / value for key, value in cfg["outputs"].items()}

    for path in inputs.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    station_frame = pd.read_csv(inputs["station_csv"])
    sites = pd.read_csv(inputs["sites_csv"])
    sectors = pd.read_csv(inputs["sectors_csv"])
    track = pd.read_csv(inputs["selected_track_csv"])
    pattern_params = pd.read_csv(inputs["pattern_parameters_csv"])
    old_summary = pd.read_csv(inputs["old_off_axis_summary_csv"])
    old_selection = json.loads(inputs["old_selected_sector_json"].read_text(encoding="utf-8"))
    layout_decision = json.loads(inputs["layout_decision_json"].read_text(encoding="utf-8"))

    if len(station_frame) != 1:
        raise ValueError("Station table must contain exactly one row")
    if len(sites) != int(cfg["expected"]["site_count"]) or sites["site_id"].nunique() != len(sites):
        raise ValueError("Site population is not the expected unique 19-site layout")
    if len(sectors) != int(cfg["expected"]["sector_count"]) or sectors["sector_id"].nunique() != len(sectors):
        raise ValueError("Sector population is not the expected unique 57-sector layout")
    if layout_decision.get("status") != "FROZEN":
        raise ValueError("E3 pattern/layout decision is not frozen")

    require_columns(
        track,
        {"time_utc", "time_s", "azimuth_deg", "elevation_deg", "slant_range_km"},
        "selected pass track",
    )
    require_columns(
        sites,
        {
            "site_id", "latitude_deg", "longitude_deg",
            "antenna_altitude_m_asl", "station_to_site_distance_m",
            "station_to_site_bearing_deg",
        },
        "site table",
    )
    require_columns(sectors, {"sector_id", "site_id"}, "sector table")
    require_columns(
        pattern_params,
        {
            "aperture_efficiency", "pattern_type", "g0_dbi",
            "phi0_deg", "phi1_deg", "phi2_deg",
        },
        "pattern parameter table",
    )

    numeric_track = track[["time_s", "azimuth_deg", "elevation_deg", "slant_range_km"]].apply(
        pd.to_numeric, errors="coerce"
    )
    if numeric_track.isna().any().any() or not np.isfinite(numeric_track.to_numpy()).all():
        raise ValueError("Selected pass track contains invalid numeric values")
    if not np.all(np.diff(numeric_track["time_s"].to_numpy(float)) > 0):
        raise ValueError("Selected pass times must increase strictly")

    station = station_frame.iloc[0]
    minimum_elevation_deg = float(station["minimum_elevation_deg"])
    protected_mask = numeric_track["elevation_deg"].to_numpy(float) >= minimum_elevation_deg
    protected_indices = np.flatnonzero(protected_mask)
    if protected_indices.size < 2:
        raise ValueError("Protected tracking window has fewer than two samples")
    if np.any(np.diff(protected_indices) != 1):
        raise ValueError("Protected tracking window is not one contiguous segment")

    protected = track.loc[protected_mask].copy().reset_index(drop=True)
    protected_numeric = numeric_track.loc[protected_mask].reset_index(drop=True)

    nominal_efficiency = float(cfg["pattern"]["nominal_aperture_efficiency"])
    pattern_type = str(cfg["pattern"]["nominal_pattern_type"])
    nominal_rows = pattern_params.loc[
        np.isclose(
            pd.to_numeric(pattern_params["aperture_efficiency"], errors="coerce"),
            nominal_efficiency,
            rtol=0.0,
            atol=1e-12,
        )
        & (pattern_params["pattern_type"].astype(str) == pattern_type)
    ]
    if len(nominal_rows) != 1:
        raise ValueError("Nominal SA.509 parameter row is not unique")
    nominal_params = nominal_rows.iloc[0]
    multiple_entry = pattern_type == "multiple_entry_section_1_2"

    station_lon = float(station["longitude_deg"])
    station_lat = float(station["latitude_deg"])
    station_alt = float(station["altitude_m_asl"])

    rows: list[dict[str, object]] = []
    for _, site in sites.sort_values("site_id").iterrows():
        site_lon = float(site["longitude_deg"])
        site_lat = float(site["latitude_deg"])
        site_alt = float(site["antenna_altitude_m_asl"])
        azimuth_deg, _, distance_m = GEOD.inv(
            station_lon, station_lat, site_lon, site_lat
        )
        azimuth_deg %= 360.0
        elevation_deg = math.degrees(math.atan2(site_alt - station_alt, distance_m))
        off_axis = angular_separation_deg(
            protected_numeric["azimuth_deg"].to_numpy(float),
            protected_numeric["elevation_deg"].to_numpy(float),
            azimuth_deg,
            elevation_deg,
        )
        gains = sa509_gain(off_axis, nominal_params, multiple_entry=multiple_entry)
        min_index = int(np.argmin(off_axis))
        max_gain_index = int(np.argmax(gains))

        site_sectors = sectors.loc[sectors["site_id"].astype(str) == str(site["site_id"])]
        if len(site_sectors) != int(cfg["expected"]["sectors_per_site"]):
            raise ValueError(f"{site['site_id']}: unexpected sector count")

        for _, sector in site_sectors.sort_values("sector_id").iterrows():
            rows.append(
                {
                    "site_id": str(site["site_id"]),
                    "sector_id": str(sector["sector_id"]),
                    "station_to_site_bearing_deg": float(azimuth_deg),
                    "station_to_site_distance_m": float(distance_m),
                    "station_to_site_elevation_deg": float(elevation_deg),
                    "protected_minimum_elevation_deg": minimum_elevation_deg,
                    "protected_window_sample_count": int(len(protected)),
                    "protected_window_start_utc": str(protected.iloc[0]["time_utc"]),
                    "protected_window_end_utc": str(protected.iloc[-1]["time_utc"]),
                    "minimum_off_axis_deg_during_protected_window": float(np.min(off_axis)),
                    "minimum_off_axis_time_utc": str(protected.iloc[min_index]["time_utc"]),
                    "median_off_axis_deg_during_protected_window": float(np.median(off_axis)),
                    "maximum_reference_gain_dbi_during_protected_window": float(np.max(gains)),
                    "maximum_reference_gain_time_utc": str(protected.iloc[max_gain_index]["time_utc"]),
                    "antenna_pattern_type": pattern_type,
                    "aperture_efficiency": nominal_efficiency,
                    "selection_window": "earth_station_elevation_ge_minimum_elevation",
                }
            )

    summary = pd.DataFrame(rows).sort_values(["site_id", "sector_id"], kind="mergesort")
    if len(summary) != int(cfg["expected"]["sector_count"]):
        raise RuntimeError("Protected-window summary does not contain 57 rows")

    # Determine old and corrected site winners using the same deterministic tie-break.
    old_site_scores = (
        old_summary.groupby("site_id", as_index=False)
        .agg(
            minimum_off_axis_deg=("minimum_off_axis_deg_during_selected_track", "first"),
            station_to_site_distance_m=("station_to_site_distance_m", "first"),
        )
        .sort_values(
            ["minimum_off_axis_deg", "station_to_site_distance_m", "site_id"],
            kind="mergesort",
        )
    )
    new_site_scores = (
        summary.groupby("site_id", as_index=False)
        .agg(
            minimum_off_axis_deg=("minimum_off_axis_deg_during_protected_window", "first"),
            station_to_site_distance_m=("station_to_site_distance_m", "first"),
        )
        .sort_values(
            ["minimum_off_axis_deg", "station_to_site_distance_m", "site_id"],
            kind="mergesort",
        )
    )

    old_site_id = str(old_site_scores.iloc[0]["site_id"])
    new_site_id = str(new_site_scores.iloc[0]["site_id"])

    expected_new_site = str(cfg["expected"]["corrected_selected_site_id"])
    if new_site_id != expected_new_site:
        raise ValueError(
            f"Corrected protected-window site is {new_site_id}; expected {expected_new_site}"
        )
    expected_old_sector = str(cfg["expected"]["superseded_sector_id"])
    if str(old_selection.get("sector_id")) != expected_old_sector:
        raise ValueError("The historical selection does not match the expected superseded sector")

    outputs["protected_summary_csv"].parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(outputs["protected_summary_csv"], index=False)

    correction = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "CORRECTED_PROTECTED_WINDOW_SUMMARY_READY",
        "reason": (
            "The historical off-axis summary included detailed-track margins below the "
            "declared earth-station minimum elevation.  Site/sector selection for the "
            "protected E3 case must use only samples with earth-station elevation at or "
            "above the minimum elevation."
        ),
        "minimum_elevation_deg": minimum_elevation_deg,
        "detailed_track_sample_count": int(len(track)),
        "protected_window_sample_count": int(len(protected)),
        "protected_window_start_utc": str(protected.iloc[0]["time_utc"]),
        "protected_window_end_utc": str(protected.iloc[-1]["time_utc"]),
        "historical_summary_status": "SUPERSEDED_FOR_PROTECTED_WINDOW_SELECTION_ONLY",
        "historical_selected_sector": str(old_selection.get("sector_id")),
        "historical_selected_site": str(old_selection.get("site_id")),
        "historical_site_winner_from_summary": old_site_id,
        "corrected_site_winner": new_site_id,
        "corrected_summary_sha256": sha256_file(outputs["protected_summary_csv"]),
        "inputs_sha256": {str(path.relative_to(root)): sha256_file(path) for path in inputs.values()},
        "claim_boundary": (
            "This correction changes the deterministic audit-sector selection only. "
            "It does not invalidate the frozen station, pass, antenna-pattern model, "
            "cellular layout, or the terrain quality of the historical site-11 path."
        ),
        "next_gate": "RESELECT_FIRST_SECTOR_USING_PROTECTED_WINDOW",
    }
    outputs["correction_json"].write_text(
        json.dumps(correction, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outputs["correction_md"].write_text(
        f"""# E3 Protected-Window Off-Axis Correction

- Status: `{correction['status']}`
- Minimum earth-station elevation: `{minimum_elevation_deg:g} deg`
- Detailed-track samples: `{len(track)}`
- Protected-window samples: `{len(protected)}`
- Protected interval: `{protected.iloc[0]['time_utc']}` to `{protected.iloc[-1]['time_utc']}`
- Historical selected sector: `{old_selection.get('sector_id')}`
- Corrected site winner: `{new_site_id}`
- Next gate: `{correction['next_gate']}`

The historical summary used the detailed-track margins below the declared
minimum elevation.  It is retained for provenance but must not be used to
select the protected-window audit sector.
""",
        encoding="utf-8",
    )

    print("E3 PROTECTED-WINDOW OFF-AXIS REBUILD: PASS")
    print("Detailed samples:", len(track))
    print("Protected samples:", len(protected))
    print("Protected start:", protected.iloc[0]["time_utc"])
    print("Protected end:", protected.iloc[-1]["time_utc"])
    print("Historical selected sector:", old_selection.get("sector_id"))
    print("Corrected selected site:", new_site_id)
    print("Output:", outputs["protected_summary_csv"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
