#!/usr/bin/env python3
"""Prepare combined 19-site P.452 profiles and parameters."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_all_site_p452.yaml")
    args = parser.parse_args()

    cfg_path = ROOT / args.config
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    inp = {key: ROOT / value for key, value in cfg["inputs"].items()}
    work = ROOT / cfg["outputs"]["work_dir"]
    work.mkdir(parents=True, exist_ok=True)

    decision_path = work / "ALL_SITE_TERRAIN_DECISION.json"
    if not decision_path.is_file():
        raise FileNotFoundError(decision_path)
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if decision.get("status") != "FROZEN_FOR_19_SITE_P452_BASIC_LOSS_AUDIT":
        raise ValueError("All-site terrain is not frozen")

    summary = pd.read_csv(inp["terrain_summary_csv"])
    profiles = pd.read_csv(inp["terrain_profiles_csv_gz"])
    sites = pd.read_csv(inp["bs_sites_csv"])
    station = pd.read_csv(inp["earth_station_csv"])
    if len(station) != 1:
        raise ValueError("Expected one station")
    station_row = station.iloc[0]

    # Remove stale propagation outputs before writing new frozen inputs.
    stale = [
        "p452_all_site_basic_loss.csv",
        "p452_all_site_coupling_export.csv",
        "P452_ALL_SITE_MATLAB_AUDIT.json",
        "ALL_SITE_P452_VALIDATION.json",
        "ALL_SITE_P452_VALIDATION.md",
        "all_site_loss_summary.csv",
    ]
    for name in stale:
        path = work / name
        if path.exists():
            path.unlink()

    profile_out = profiles[
        [
            "link_id",
            "sample_index",
            "distance_from_tx_m",
            "elevation_m_asl",
            "longitude_deg",
            "latitude_deg",
        ]
    ].copy()
    profile_out = profile_out.rename(
        columns={
            "link_id": "site_id",
            "distance_from_tx_m": "distance_m",
            "elevation_m_asl": "terrain_m_asl",
        }
    )
    profile_out["distance_km"] = profile_out["distance_m"].astype(float) / 1000.0
    profile_out["clutter_plus_terrain_m_asl"] = profile_out["terrain_m_asl"]
    profile_out["radio_climatic_zone"] = int(
        cfg["propagation"]["climatic_zone_code"]
    )
    profile_out = profile_out[
        [
            "site_id",
            "sample_index",
            "distance_km",
            "terrain_m_asl",
            "clutter_plus_terrain_m_asl",
            "radio_climatic_zone",
            "longitude_deg",
            "latitude_deg",
        ]
    ].sort_values(["site_id", "sample_index"])
    profiles_output_path = work / "p452_all_site_profiles.csv"
    profile_out.to_csv(profiles_output_path, index=False)

    summary_index = summary.set_index("link_id")
    site_rows = []
    for _, site in sites.sort_values("site_id").iterrows():
        site_id = str(site["site_id"])
        row = summary_index.loc[site_id]
        group = profile_out.loc[profile_out["site_id"] == site_id]
        site_rows.append(
            {
                "site_id": site_id,
                "distance_km": float(row["distance_km_wgs84"]),
                "profile_sample_count": int(len(group)),
                "htg_m": float(row["tx_implied_antenna_height_agl_m"]),
                "hrg_m": float(row["rx_implied_antenna_height_agl_m"]),
                "tx_longitude_deg": float(group.iloc[0]["longitude_deg"]),
                "tx_latitude_deg": float(group.iloc[0]["latitude_deg"]),
                "rx_longitude_deg": float(group.iloc[-1]["longitude_deg"]),
                "rx_latitude_deg": float(group.iloc[-1]["latitude_deg"]),
                "station_id": str(station_row["station_id"]),
            }
        )
    site_parameters = pd.DataFrame(site_rows)
    site_parameters_path = work / "p452_all_site_site_parameters.csv"
    site_parameters.to_csv(site_parameters_path, index=False)

    commit = inp["p452_reference_commit_file"].read_text(encoding="utf-8").strip()
    if commit != str(cfg["expected"]["p452_reference_commit"]):
        raise ValueError(f"Unexpected P.452 reference commit: {commit}")
    provenance = inp["p452_reference_provenance_file"].read_text(
        encoding="utf-8", errors="replace"
    )
    if "17 out of 17" not in provenance and "17/17" not in provenance:
        raise ValueError("P.452 provenance does not record 17/17 validation")
    if "R2026a" not in provenance and "2026a" not in provenance:
        raise ValueError("P.452 provenance does not identify MATLAB R2026a")

    params = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": cfg["claim_boundary"]["p452"],
        "station_id": str(station_row["station_id"]),
        "frequency_ghz": float(cfg["propagation"]["frequency_ghz"]),
        "time_percentages": [
            float(value) for value in cfg["propagation"]["time_percentages"]
        ],
        "polarization_codes": [
            int(value) for value in cfg["propagation"]["polarization_codes"]
        ],
        "polarization_labels": [
            str(value) for value in cfg["propagation"]["polarization_labels"]
        ],
        "coast_distance_scenarios_km": [
            float(value)
            for value in cfg["propagation"]["coast_distance_scenarios_km"]
        ],
        "pressure_hpa": float(cfg["propagation"]["pressure_hpa"]),
        "temperature_c": float(cfg["propagation"]["temperature_c"]),
        "terminal_horizon_gain_tx_dbi": float(
            cfg["propagation"]["terminal_horizon_gain_tx_dbi"]
        ),
        "terminal_horizon_gain_rx_dbi": float(
            cfg["propagation"]["terminal_horizon_gain_rx_dbi"]
        ),
        "clutter_mode": cfg["propagation"]["clutter_mode"],
        "separate_p2108_loss_db": float(
            cfg["propagation"]["p2108_separate_loss_db"]
        ),
        "coordinate_convention": cfg["propagation"]["coordinate_convention"],
        "p452_reference_commit": commit,
        "expected_matlab_release": str(cfg["expected"]["matlab_release"]),
        "site_count": int(len(site_parameters)),
        "expected_output_row_count": (
            len(site_parameters)
            * len(cfg["propagation"]["time_percentages"])
            * len(cfg["propagation"]["polarization_codes"])
            * len(cfg["propagation"]["coast_distance_scenarios_km"])
        ),
        "profiles_sha256": sha256_file(profiles_output_path),
        "site_parameters_sha256": sha256_file(site_parameters_path),
        "terrain_decision_sha256": sha256_file(decision_path),
        "config_sha256": sha256_file(cfg_path),
        "zero_terminal_horizon_gains_inside_p452": True,
        "no_separate_p2108_baseline": True,
        "coast_distance_status": cfg["propagation"]["coast_distance_status"],
    }
    params_path = work / "p452_all_site_parameters.json"
    write_json(params_path, params)

    prep = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "MATLAB_READY_FROZEN",
        "claim_boundary": cfg["claim_boundary"]["p452"],
        "site_count": len(site_parameters),
        "profile_sample_count": len(profile_out),
        "expected_output_row_count": params["expected_output_row_count"],
        "generated_sha256": {
            profiles_output_path.name: sha256_file(profiles_output_path),
            site_parameters_path.name: sha256_file(site_parameters_path),
            params_path.name: sha256_file(params_path),
        },
        "next_gate": "MATLAB_ALL_SITE_P452_BASIC_LOSS",
    }
    write_json(work / "ALL_SITE_P452_PREP_AUDIT.json", prep)

    print("E3 ALL-SITE P.452 INPUT PREPARATION: PASS")
    print("Sites:", len(site_parameters))
    print("Profile samples:", len(profile_out))
    print("Expected MATLAB rows:", params["expected_output_row_count"])
    print("Output directory:", work)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
