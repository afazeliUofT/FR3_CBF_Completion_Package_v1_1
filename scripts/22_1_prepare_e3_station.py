#!/usr/bin/env python3
"""Prepare an explicitly labelled public/model E3 earth-station reference record."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_reference_intake.yaml")
    parser.add_argument("--force-mrdem", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config_path = root / args.config
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    station = cfg["station"]
    lat = float(station["public_coordinate_latitude_deg"])
    lon = float(station["public_coordinate_longitude_deg"])
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("Invalid signed WGS84 station coordinate")
    if station["coordinate_source_status"] != "PUBLIC_OSM_BUILDING_CENTROID_NOT_OFFICIAL_SURVEY":
        raise ValueError("Coordinate status must preserve the non-survey claim boundary")
    agl = float(station["phase_center_height_agl_m_nominal"])
    low, high = map(float, station["phase_center_height_agl_m_sensitivity"])
    if not (0.0 < low <= agl <= high):
        raise ValueError("Invalid phase-centre model/sensitivity interval")
    out_dir = root / "data/real/e3_reference_case"
    external_dir = root / "data/external/mrdem_e3_reference"
    out_dir.mkdir(parents=True, exist_ok=True)
    external_dir.mkdir(parents=True, exist_ok=True)
    extent = out_dir / "station_extent.csv"
    pd.DataFrame(
        [{"tx_lat_deg": lat, "tx_lon_deg": lon, "rx_lat_deg": lat, "rx_lon_deg": lon}]
    ).to_csv(extent, index=False)
    subset = external_dir / "mrdem_dtm_study_subset.tif"
    if args.force_mrdem or not subset.is_file():
        command = [
            sys.executable,
            str(root / "scripts/03_3_fetch_mrdem_dtm.py"),
            "--links",
            str(extent),
            "--out-dir",
            str(external_dir),
            "--padding-deg",
            str(float(station["mrdem_padding_deg"])),
        ]
        if subset.exists() or args.force_mrdem:
            command.append("--force")
        subprocess.run(command, cwd=root, check=True)
    if not subset.is_file():
        raise FileNotFoundError(subset)
    try:
        import rasterio
        from rasterio.warp import transform
    except ImportError as exc:
        raise SystemExit("Install requirements-terrain.txt or requirements-full.txt") from exc
    with rasterio.open(subset) as src:
        if src.crs is None:
            raise RuntimeError("MRDEM E3 subset has no CRS")
        xs, ys = transform("EPSG:4326", src.crs, [lon], [lat])
        sample = next(src.sample([(xs[0], ys[0])], masked=True))[0]
        if getattr(sample, "mask", False):
            raise RuntimeError("Station coordinate samples a masked MRDEM cell")
        ground_m_asl = float(sample)
        if not (-500.0 < ground_m_asl < 9000.0):
            raise RuntimeError(f"Implausible station ground elevation: {ground_m_asl}")
    phase_center_m_asl = ground_m_asl + agl
    staging = pd.DataFrame(
        [
            {
                "station_id": station["station_id"],
                "latitude_deg": lat,
                "longitude_deg": lon,
                "ground_elevation_m_asl": ground_m_asl,
                "phase_center_height_m_agl_nominal": agl,
                "altitude_m_asl": phase_center_m_asl,
                "dish_diameter_m": float(station["dish_diameter_m"]),
                "dish_gain_dbi": "",
                "minimum_elevation_deg": float(station["minimum_elevation_deg"]),
                "antenna_pattern_source": "OPEN_NOT_SELECTED_IN_THIS_STAGE",
                "target_mission": cfg["mission"]["mission_label"],
                "field_status": "PUBLIC_SITE_AND_DISH_DIAMETER__MODELED_COORDINATE_PHASE_CENTER_AND_PATTERN",
                "source_url": station["official_facility_url"],
                "provenance_note": (
                    "Address and 13 m S/X dish are public NRCan facts; coordinate is an OSM-derived "
                    "building centroid, not an official survey; phase-centre AGL is a declared model decision."
                ),
            }
        ]
    )
    station_csv = out_dir / "earth_station_staging.csv"
    staging.to_csv(station_csv, index=False)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "station_id": station["station_id"],
                    "coordinate_status": station["coordinate_source_status"],
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        ],
    }
    write_json(out_dir / "earth_station_reference.geojson", geojson)
    source_record = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "station": station,
        "mission": cfg["mission"],
        "paper_model_decisions": cfg["paper_model_decisions"],
        "ground_elevation_m_asl_mrdem": ground_m_asl,
        "phase_center_altitude_m_asl_nominal": phase_center_m_asl,
        "mrdem_subset": str(subset.relative_to(root)),
        "mrdem_subset_sha256": sha256_file(subset),
        "config_sha256": sha256_file(config_path),
        "claim_boundary": (
            "This is a reproducible reference case. It is not a surveyed dish phase-centre coordinate, "
            "not an operator deployment, and not evidence that the selected mission used 8.15 GHz during the pass."
        ),
        "next_open_items": [
            "Select and justify the earth-station antenna pattern and efficiency envelope.",
            "Freeze the modelled 19-site/57-sector cellular layout.",
            "Generate validated P.452 sector-to-station couplings.",
        ],
    }
    write_json(out_dir / "E3_STATION_SOURCE_RECORD.json", source_record)
    print("E3 REFERENCE STATION PREPARATION: PASS")
    print(f"Station coordinate: {lat:.8f}, {lon:.8f}")
    print(f"MRDEM ground elevation: {ground_m_asl:.3f} m ASL")
    print(f"Modelled phase-centre altitude: {phase_center_m_asl:.3f} m ASL")
    print("Antenna pattern: OPEN — not selected in this stage")
    print(f"Output: {station_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
