#!/usr/bin/env python3
"""Strictly validate the corrected E3 protected-window summary and first-sector selection."""
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_protected_window_correction.yaml")
    parser.add_argument("--root")
    parser.add_argument("--selection-dir", default="data/real/e3_first_sector_audit")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / args.config).read_text(encoding="utf-8"))
    inputs = cfg["inputs"]
    outputs = cfg["outputs"]
    expected = cfg["expected"]

    station_path = root / inputs["station_csv"]
    sites_path = root / inputs["sites_csv"]
    sectors_path = root / inputs["sectors_csv"]
    track_path = root / inputs["selected_track_csv"]
    old_summary_path = root / inputs["old_off_axis_summary_csv"]
    old_selection_path = root / inputs["old_selected_sector_json"]
    protected_summary_path = root / outputs["protected_summary_csv"]
    correction_path = root / outputs["correction_json"]
    selection_dir = root / args.selection_dir
    selected_path = selection_dir / "selected_sector.json"
    candidates_path = selection_dir / "sector_candidates.csv"
    link_path = selection_dir / "first_sector_link_input.csv"

    required = [
        station_path, sites_path, sectors_path, track_path, old_summary_path,
        old_selection_path, protected_summary_path, correction_path,
        selected_path, candidates_path, link_path,
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    station_frame = pd.read_csv(station_path)
    sites = pd.read_csv(sites_path)
    sectors = pd.read_csv(sectors_path)
    track = pd.read_csv(track_path)
    old_summary = pd.read_csv(old_summary_path)
    protected_summary = pd.read_csv(protected_summary_path)
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    candidates = pd.read_csv(candidates_path)
    link = pd.read_csv(link_path)

    if len(station_frame) != 1:
        raise ValueError("Station table is not one row")
    station = station_frame.iloc[0]
    minimum_elevation = float(station["minimum_elevation_deg"])

    protected = track.loc[
        pd.to_numeric(track["elevation_deg"], errors="coerce") >= minimum_elevation
    ].copy()
    if len(protected) < 2:
        raise ValueError("Protected track window is empty")
    protected_positions = np.flatnonzero(
        pd.to_numeric(track["elevation_deg"], errors="coerce").to_numpy(float)
        >= minimum_elevation
    )
    if np.any(np.diff(protected_positions) != 1):
        raise ValueError("Protected track window is not contiguous")

    if correction.get("status") != "CORRECTED_PROTECTED_WINDOW_SUMMARY_READY":
        raise ValueError("Correction status is not ready")
    if correction.get("protected_window_sample_count") != len(protected):
        raise ValueError("Correction record has the wrong protected sample count")
    if correction.get("protected_window_start_utc") != str(protected.iloc[0]["time_utc"]):
        raise ValueError("Correction record has the wrong protected start")
    if correction.get("protected_window_end_utc") != str(protected.iloc[-1]["time_utc"]):
        raise ValueError("Correction record has the wrong protected end")

    if len(protected_summary) != int(expected["sector_count"]):
        raise ValueError("Protected summary does not have 57 rows")
    if protected_summary["sector_id"].nunique() != int(expected["sector_count"]):
        raise ValueError("Protected summary sector IDs are not unique")
    if set(protected_summary["selection_window"].astype(str)) != {
        "earth_station_elevation_ge_minimum_elevation"
    }:
        raise ValueError("Protected summary is not explicitly protected-window only")

    # Independent site-level geometry recomputation for the corrected winner.
    site_scores = (
        protected_summary.groupby("site_id", as_index=False)
        .agg(
            minimum_off_axis_deg=(
                "minimum_off_axis_deg_during_protected_window",
                "first",
            ),
            distance_m=("station_to_site_distance_m", "first"),
        )
        .sort_values(
            ["minimum_off_axis_deg", "distance_m", "site_id"],
            kind="mergesort",
        )
    )
    winning_site_id = str(site_scores.iloc[0]["site_id"])
    if winning_site_id != str(expected["corrected_selected_site_id"]):
        raise ValueError(
            f"Protected-window winner is {winning_site_id}; "
            f"expected {expected['corrected_selected_site_id']}"
        )

    winner_site = sites.loc[sites["site_id"].astype(str) == winning_site_id]
    if len(winner_site) != 1:
        raise ValueError("Winning site is not unique")
    site = winner_site.iloc[0]

    station_lon = float(station["longitude_deg"])
    station_lat = float(station["latitude_deg"])
    site_lon = float(site["longitude_deg"])
    site_lat = float(site["latitude_deg"])
    station_to_site_azimuth, _, station_to_site_distance = GEOD.inv(
        station_lon, station_lat, site_lon, site_lat
    )
    station_to_site_azimuth %= 360.0
    station_to_site_elevation = math.degrees(
        math.atan2(
            float(site["antenna_altitude_m_asl"]) - float(station["altitude_m_asl"]),
            station_to_site_distance,
        )
    )
    recomputed_off_axis = angular_separation_deg(
        protected["azimuth_deg"].to_numpy(float),
        protected["elevation_deg"].to_numpy(float),
        station_to_site_azimuth,
        station_to_site_elevation,
    )
    summary_site_row = protected_summary.loc[
        protected_summary["site_id"].astype(str) == winning_site_id
    ].iloc[0]
    if abs(
        float(summary_site_row["minimum_off_axis_deg_during_protected_window"])
        - float(np.min(recomputed_off_axis))
    ) > 1e-9:
        raise ValueError("Protected summary minimum off-axis fails independent recomputation")

    if str(selected.get("selection_window")) != "earth_station_elevation_ge_minimum_elevation":
        raise ValueError("Selected sector does not identify the protected selection window")
    if str(selected.get("site_id")) != winning_site_id:
        raise ValueError("Selected site does not match the protected-window winner")
    if str(selected.get("sector_id")) != str(expected["corrected_selected_sector_id"]):
        raise ValueError("Selected sector does not match the expected corrected sector")
    if str(selected.get("supersedes_sector_id")) != str(expected["superseded_sector_id"]):
        raise ValueError("Selected sector does not record the superseded historical sector")

    if len(candidates) != int(expected["sectors_per_site"]):
        raise ValueError("Corrected site candidate table does not have three sectors")
    if str(candidates.iloc[0]["sector_id"]) != str(expected["corrected_selected_sector_id"]):
        raise ValueError("Candidate sorting does not place the corrected sector first")

    if len(link) != 1 or str(link.iloc[0]["link_id"]) != str(expected["corrected_selected_sector_id"]):
        raise ValueError("First-sector link input does not match corrected selection")
    if not pd.isna(link.iloc[0]["mean_terrain_elevation_m_asl"]):
        raise ValueError("Corrected link input must remain unfinished before terrain processing")

    old_minimum = float(
        old_summary["minimum_off_axis_deg_during_selected_track"].min()
    )
    new_minimum = float(
        protected_summary["minimum_off_axis_deg_during_protected_window"].min()
    )
    if not new_minimum > old_minimum:
        raise ValueError("Correction did not remove the below-minimum-elevation alignment")

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "historical_sector_status": "SUPERSEDED_UNPROTECTED_TRACK_WINDOW_SELECTION",
        "historical_sector_id": str(expected["superseded_sector_id"]),
        "corrected_sector_id": str(expected["corrected_selected_sector_id"]),
        "corrected_site_id": winning_site_id,
        "minimum_elevation_deg": minimum_elevation,
        "detailed_track_sample_count": int(len(track)),
        "protected_window_sample_count": int(len(protected)),
        "protected_window_start_utc": str(protected.iloc[0]["time_utc"]),
        "protected_window_end_utc": str(protected.iloc[-1]["time_utc"]),
        "old_global_minimum_off_axis_deg": old_minimum,
        "corrected_global_minimum_off_axis_deg": new_minimum,
        "input_sha256": {
            str(path.relative_to(root)): sha256_file(path)
            for path in required
        },
        "next_gate": "BUILD_CORRECTED_FIRST_SECTOR_TERRAIN_PROFILE",
        "claim_boundary": (
            "This validates corrected selection only. It does not produce P.452 "
            "loss or a paper-grade E3 interference result."
        ),
    }
    audit_path = root / "data/real/E3_PROTECTED_WINDOW_SELECTION_AUDIT.json"
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("E3 PROTECTED-WINDOW SELECTION VALIDATION: PASS")
    print("Historical sector:", audit["historical_sector_id"])
    print("Corrected sector:", audit["corrected_sector_id"])
    print("Detailed samples:", audit["detailed_track_sample_count"])
    print("Protected samples:", audit["protected_window_sample_count"])
    print("Old minimum off-axis (deg):", f"{old_minimum:.9f}")
    print("Corrected minimum off-axis (deg):", f"{new_minimum:.9f}")
    print("Next gate:", audit["next_gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
