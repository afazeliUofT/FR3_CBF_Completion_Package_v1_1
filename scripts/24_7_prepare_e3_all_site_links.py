#!/usr/bin/env python3
"""Create one propagation-link input per unique E3 modelled BS site."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml
from pyproj import Geod

ROOT = Path(__file__).resolve().parents[1]
GEOD = Geod(ellps="WGS84")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/e3_all_site_terrain_review.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    inp = cfg["inputs"]
    out_path = ROOT / cfg["outputs"]["all_site_links_input_csv"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    station = pd.read_csv(ROOT / inp["earth_station_csv"])
    sites = pd.read_csv(ROOT / inp["bs_sites_csv"])

    if len(station) != 1:
        raise ValueError("Expected exactly one earth-station row")
    if len(sites) != int(cfg["expected"]["site_count"]):
        raise ValueError(f"Expected {cfg['expected']['site_count']} site rows")
    if sites["site_id"].astype(str).duplicated().any():
        raise ValueError("Duplicate site_id values")

    st = station.iloc[0]
    rows = []
    for _, site in sites.sort_values("site_id").iterrows():
        _, _, distance_m = GEOD.inv(
            float(site["longitude_deg"]),
            float(site["latitude_deg"]),
            float(st["longitude_deg"]),
            float(st["latitude_deg"]),
        )
        rows.append(
            {
                "link_id": str(site["site_id"]),
                "tx_lat_deg": float(site["latitude_deg"]),
                "tx_lon_deg": float(site["longitude_deg"]),
                "rx_lat_deg": float(st["latitude_deg"]),
                "rx_lon_deg": float(st["longitude_deg"]),
                "tx_antenna_alt_m_asl": float(site["antenna_altitude_m_asl"]),
                "rx_antenna_alt_m_asl": float(st["altitude_m_asl"]),
                "mean_terrain_elevation_m_asl": float("nan"),
                "provenance_note": (
                    "Modelled E3 unique-site terrain/P.452 preparation; "
                    "one propagation path per site shared by its three co-located sectors; "
                    "not a paper result."
                ),
                "expected_geodesic_distance_m": float(distance_m),
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(out_path, index=False)

    print("E3 ALL-SITE LINK-INPUT PREPARATION: PASS")
    print("Unique sites:", len(frame))
    print("Minimum site distance (m):", frame["expected_geodesic_distance_m"].min())
    print("Maximum site distance (m):", frame["expected_geodesic_distance_m"].max())
    print("Output:", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
