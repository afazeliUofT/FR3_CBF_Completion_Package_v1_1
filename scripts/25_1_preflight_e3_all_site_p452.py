#!/usr/bin/env python3
"""Strict pre-MATLAB validation for the 19-site P.452 inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_all_site_p452.yaml")
    args = parser.parse_args()
    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["outputs"]["work_dir"]

    profiles = pd.read_csv(work / "p452_all_site_profiles.csv")
    sites = pd.read_csv(work / "p452_all_site_site_parameters.csv")
    params = json.loads(
        (work / "p452_all_site_parameters.json").read_text(encoding="utf-8")
    )
    prep = json.loads(
        (work / "ALL_SITE_P452_PREP_AUDIT.json").read_text(encoding="utf-8")
    )

    expected_sites = int(cfg["expected"]["site_count"])
    expected_samples = int(cfg["expected"]["terrain_profile_sample_count"])
    if prep.get("status") != "MATLAB_READY_FROZEN":
        raise ValueError("Preparation audit is not frozen")
    if len(sites) != expected_sites or sites["site_id"].nunique() != expected_sites:
        raise ValueError("Expected 19 unique site parameter rows")
    if len(profiles) != expected_samples:
        raise ValueError("Unexpected combined profile sample count")
    if params["expected_output_row_count"] != 798:
        raise ValueError("Expected 798 P.452 output rows")

    if not np.allclose(sites["htg_m"], 25.0, atol=1e-8, rtol=0):
        raise ValueError("A site height is not 25 m AGL")
    if not np.allclose(sites["hrg_m"], 20.0, atol=1e-8, rtol=0):
        raise ValueError("Station height is not 20 m AGL")

    for site_id, group in profiles.groupby("site_id", sort=True):
        group = group.sort_values("sample_index")
        distance = group["distance_km"].to_numpy(float)
        if abs(distance[0]) > 1e-12 or np.any(np.diff(distance) <= 0):
            raise ValueError(f"{site_id}: invalid distance vector")
        if not np.allclose(
            group["clutter_plus_terrain_m_asl"],
            group["terrain_m_asl"],
            atol=1e-12,
            rtol=0,
        ):
            raise ValueError(f"{site_id}: baseline is not g=h")
        if not (group["radio_climatic_zone"] == 2).all():
            raise ValueError(f"{site_id}: non-inland climatic zone")
        if not group["longitude_deg"].between(-180, 180).all():
            raise ValueError(f"{site_id}: invalid longitude")
        if not group["latitude_deg"].between(-90, 90).all():
            raise ValueError(f"{site_id}: invalid latitude")
        row = sites.loc[sites["site_id"] == site_id]
        if len(row) != 1:
            raise ValueError(f"{site_id}: missing/nonunique parameter row")
        row = row.iloc[0]
        if abs(distance[-1] - float(row["distance_km"])) > 1e-9:
            raise ValueError(f"{site_id}: distance mismatch")
        endpoint = [
            (group.iloc[0]["longitude_deg"], row["tx_longitude_deg"]),
            (group.iloc[0]["latitude_deg"], row["tx_latitude_deg"]),
            (group.iloc[-1]["longitude_deg"], row["rx_longitude_deg"]),
            (group.iloc[-1]["latitude_deg"], row["rx_latitude_deg"]),
        ]
        if any(abs(float(a) - float(b)) > 1e-9 for a, b in endpoint):
            raise ValueError(f"{site_id}: endpoint mismatch")

    print("E3 ALL-SITE P.452 INPUT PREFLIGHT: PASS")
    print("Sites:", len(sites))
    print("Profile samples:", len(profiles))
    print("Expected MATLAB rows:", params["expected_output_row_count"])
    print("Time percentages:", params["time_percentages"])
    print("Polarizations:", params["polarization_labels"])
    print("Coast scenarios:", params["coast_distance_scenarios_km"])
    print("Terminal horizon gains inside P.452: 0 dBi / 0 dBi")
    print("Baseline clutter: g=h; separate P.2108: 0 dB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
