#!/usr/bin/env python3
"""Prepare a deterministic finite 57-sector/57-user Sionna topology adapter."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]


def natural_key(value: str):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def wrap_deg(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/sionna2_topology_readiness.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    adapter = cfg["adapter"]
    work = ROOT / cfg["environment"]["work_dir"]
    work.mkdir(parents=True, exist_ok=True)

    delay_decision = json.loads(
        (work / "SIONNA2_DELAY_AND_SOURCE_AUDIT.json").read_text(encoding="utf-8")
    )
    if delay_decision["status"] != "PASS_ENERGY_WEIGHTED_DELAY_SANITY":
        skipped = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "SKIPPED_DUE_TO_DELAY_SANITY_STOP",
            "next_gate": delay_decision["next_gate"],
        }
        write_json(work / "CUSTOM_TOPOLOGY_ADAPTER_SKIPPED.json", skipped)
        print("CUSTOM TOPOLOGY ADAPTER: SCIENTIFIC STOP PROPAGATED")
        return 0

    sites_path = ROOT / "data/real/bs_sites.csv"
    sectors_path = ROOT / "data/real/bs_sectors.csv"
    for path in [sites_path, sectors_path]:
        if not path.is_file():
            raise FileNotFoundError(path)
    sites = pd.read_csv(sites_path)
    sectors = pd.read_csv(sectors_path)

    required_sites = {"site_id", "latitude_deg", "longitude_deg"}
    required_sectors = {
        "sector_id",
        "site_id",
        "azimuth_deg",
        "downtilt_deg",
    }
    if not required_sites.issubset(sites.columns):
        raise ValueError(f"bs_sites.csv missing {sorted(required_sites - set(sites.columns))}")
    if not required_sectors.issubset(sectors.columns):
        raise ValueError(
            f"bs_sectors.csv missing {sorted(required_sectors - set(sectors.columns))}"
        )
    if len(sites) != int(expected["site_count"]) or sites["site_id"].nunique() != len(sites):
        raise ValueError("Expected exactly 19 unique sites")
    if len(sectors) != int(expected["sector_count"]) or sectors["sector_id"].nunique() != len(sectors):
        raise ValueError("Expected exactly 57 unique sectors")
    if set(sectors["site_id"].astype(str)) != set(sites["site_id"].astype(str)):
        raise ValueError("Sector/site identifier sets differ")

    sites = sites.copy()
    sites["site_id"] = sites["site_id"].astype(str)
    sectors = sectors.copy()
    sectors["site_id"] = sectors["site_id"].astype(str)
    sectors["sector_id"] = sectors["sector_id"].astype(str)
    sites = sites.sort_values("site_id", key=lambda s: s.map(natural_key)).reset_index(drop=True)
    sectors = sectors.sort_values("sector_id", key=lambda s: s.map(natural_key)).reset_index(drop=True)

    lat0 = float(sites["latitude_deg"].mean())
    lon0 = float(sites["longitude_deg"].mean())
    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat0:.12f} +lon_0={lon0:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)
    site_x, site_y = transformer.transform(
        sites["longitude_deg"].to_numpy(float),
        sites["latitude_deg"].to_numpy(float),
    )
    sites["x_m"] = site_x
    sites["y_m"] = site_y
    site_index = sites.set_index("site_id")

    rng = np.random.default_rng(int(adapter["random_seed"]))
    bs_rows = []
    ut_rows = []
    serving_indices = []

    for bs_index, sector in sectors.iterrows():
        site = site_index.loc[str(sector["site_id"])]
        geographic_azimuth = float(sector["azimuth_deg"]) % 360.0
        yaw_rad = math.radians((90.0 - geographic_azimuth) % 360.0)
        pitch_rad = math.radians(float(sector["downtilt_deg"]))
        bs_rows.append(
            {
                "bs_index": int(bs_index),
                "sector_id": str(sector["sector_id"]),
                "site_id": str(sector["site_id"]),
                "x_m": float(site["x_m"]),
                "y_m": float(site["y_m"]),
                "z_m": float(adapter["bs_height_m"]),
                "geographic_azimuth_deg": geographic_azimuth,
                "sionna_yaw_rad": yaw_rad,
                "sionna_pitch_rad": pitch_rad,
                "sionna_roll_rad": 0.0,
            }
        )
        radius2 = rng.uniform(
            float(adapter["minimum_user_radius_m"]) ** 2,
            float(adapter["maximum_user_radius_m"]) ** 2,
        )
        radius = math.sqrt(radius2)
        offset = float(
            rng.uniform(
                -float(adapter["sector_half_width_deg"]),
                float(adapter["sector_half_width_deg"]),
            )
        )
        user_azimuth = (geographic_azimuth + offset) % 360.0
        az_rad = math.radians(user_azimuth)
        x = float(site["x_m"]) + radius * math.sin(az_rad)
        y = float(site["y_m"]) + radius * math.cos(az_rad)
        indoor = bool(rng.random() < float(adapter["indoor_probability"]))
        ut_index = len(ut_rows)
        ut_rows.append(
            {
                "ut_index": ut_index,
                "user_id": f"{sector['sector_id']}_UE_1",
                "serving_sector_id": str(sector["sector_id"]),
                "serving_bs_index": int(bs_index),
                "x_m": x,
                "y_m": y,
                "z_m": float(adapter["ut_height_m"]),
                "radius_from_serving_bs_m": radius,
                "geographic_azimuth_from_bs_deg": user_azimuth,
                "offset_from_sector_boresight_deg": wrap_deg(
                    user_azimuth - geographic_azimuth
                ),
                "indoor": indoor,
            }
        )
        serving_indices.append(int(bs_index))

    bs_frame = pd.DataFrame(bs_rows)
    ut_frame = pd.DataFrame(ut_rows)
    if len(bs_frame) != int(expected["sector_count"]):
        raise ValueError("Unexpected BS-sector count")
    if len(ut_frame) != int(expected["adapter_user_count"]):
        raise ValueError("Unexpected adapter user count")
    if not ut_frame["offset_from_sector_boresight_deg"].abs().le(
        float(adapter["sector_half_width_deg"]) + 1e-10
    ).all():
        raise ValueError("A user lies outside its serving sector")
    if not ut_frame["radius_from_serving_bs_m"].between(
        float(adapter["minimum_user_radius_m"]),
        float(adapter["maximum_user_radius_m"]),
    ).all():
        raise ValueError("A user lies outside the configured radius range")

    bs_csv = work / "CUSTOM_57_SECTOR_BS_TOPOLOGY.csv"
    ut_csv = work / "CUSTOM_57_SECTOR_UT_TOPOLOGY.csv"
    bs_frame.to_csv(bs_csv, index=False)
    ut_frame.to_csv(ut_csv, index=False)

    bs_loc = bs_frame[["x_m", "y_m", "z_m"]].to_numpy(np.float32)[None, ...]
    bs_orientations = bs_frame[
        ["sionna_yaw_rad", "sionna_pitch_rad", "sionna_roll_rad"]
    ].to_numpy(np.float32)[None, ...]
    ut_loc = ut_frame[["x_m", "y_m", "z_m"]].to_numpy(np.float32)[None, ...]
    ut_orientations = np.zeros_like(ut_loc, dtype=np.float32)
    ut_velocities = np.zeros_like(ut_loc, dtype=np.float32)
    in_state = ut_frame["indoor"].to_numpy(bool)[None, ...]
    serving = np.asarray(serving_indices, dtype=np.int64)

    npz_path = work / "CUSTOM_57_SECTOR_TOPOLOGY.npz"
    np.savez_compressed(
        npz_path,
        bs_loc=bs_loc,
        bs_orientations=bs_orientations,
        ut_loc=ut_loc,
        ut_orientations=ut_orientations,
        ut_velocities=ut_velocities,
        in_state=in_state,
        serving_bs_index=serving,
        sector_ids=bs_frame["sector_id"].to_numpy(dtype="U64"),
        user_ids=ut_frame["user_id"].to_numpy(dtype="U96"),
    )

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_CUSTOM_TOPOLOGY_GEOMETRY_READY",
        "claim_boundary": cfg["claim_boundary"]["topology_adapter"],
        "origin_latitude_deg": lat0,
        "origin_longitude_deg": lon0,
        "local_crs_wkt": local_crs.to_wkt(),
        "site_count": int(expected["site_count"]),
        "sector_count": len(bs_frame),
        "user_count": len(ut_frame),
        "users_per_sector": int(expected["adapter_users_per_sector"]),
        "finite_network_no_wraparound": bool(
            adapter["finite_network_no_wraparound"]
        ),
        "edge_effect_boundary": (
            "The adapter pilot is a finite 19-site network without wraparound. "
            "Paper-scale edge sensitivity remains required."
        ),
        "orientation_mapping": (
            "Local x=east, y=north; Sionna yaw=90deg-geographic azimuth; "
            "positive pitch equals declared mechanical downtilt."
        ),
        "radius_range_m": [
            float(ut_frame["radius_from_serving_bs_m"].min()),
            float(ut_frame["radius_from_serving_bs_m"].max()),
        ],
        "indoor_fraction": float(ut_frame["indoor"].mean()),
        "next_gate": "CUSTOM_57_SECTOR_SIONNA_CPU_API_AND_RATE_AUDIT",
    }
    write_json(work / "CUSTOM_57_SECTOR_TOPOLOGY_AUDIT.json", audit)
    print("CUSTOM 57-SECTOR TOPOLOGY PREPARATION: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
