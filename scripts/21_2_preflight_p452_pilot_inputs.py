#!/usr/bin/env python3
"""Strict pre-MATLAB validation of frozen P.452 pilot inputs.

This gate exists to catch coordinate-convention, endpoint, polarization-plan,
and stale-output defects before Windows MATLAB is launched.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

COORDINATE_CONVENTION = (
    "longitude_degrees_east_signed_-180_to_180;"
    "latitude_degrees_north_-90_to_90"
)
COORDINATE_ARGUMENT_ORDER = [
    "tx_longitude_deg",
    "tx_latitude_deg",
    "rx_longitude_deg",
    "rx_latitude_deg",
]
STALE_OUTPUT_NAMES = [
    "p452_pilot_results.csv",
    "p452_pilot_coupling.csv",
    "P452_PILOT_MATLAB_AUDIT.json",
]


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-dir", default="data/real/p452_pilot")
    parser.add_argument(
        "--allow-existing-matlab-outputs",
        action="store_true",
        help="Allow output files from a completed MATLAB run; default is to reject stale outputs.",
    )
    args = parser.parse_args()

    root = Path(args.pilot_dir).expanduser().resolve()
    parameters_path = root / "p452_pilot_parameters.json"
    profile_path = root / "p452_pilot_profile.csv"
    audit_path = root / "P452_PILOT_PREP_AUDIT.json"
    for path in (parameters_path, profile_path, audit_path):
        require_file(path)

    parameters = json.loads(parameters_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    profile = pd.read_csv(profile_path)

    if audit.get("status") != "MATLAB_READY_FROZEN":
        raise ValueError(
            f"Pilot preparation is not frozen: status={audit.get('status')!r}"
        )
    if not all(bool(value) for value in audit.get("manual_confirmations", {}).values()):
        raise ValueError("Not all manual confirmations are true")

    if parameters.get("coordinate_convention") != COORDINATE_CONVENTION:
        raise ValueError("Incorrect or missing signed-longitude coordinate convention")
    if parameters.get("tl_p452_coordinate_argument_order") != COORDINATE_ARGUMENT_ORDER:
        raise ValueError("Incorrect tl_p452 coordinate argument order")

    coordinates = {
        "tx_longitude_deg": float(parameters["tx_longitude_deg"]),
        "tx_latitude_deg": float(parameters["tx_latitude_deg"]),
        "rx_longitude_deg": float(parameters["rx_longitude_deg"]),
        "rx_latitude_deg": float(parameters["rx_latitude_deg"]),
    }
    for name in ("tx_longitude_deg", "rx_longitude_deg"):
        value = coordinates[name]
        if not math.isfinite(value) or not (-180.0 <= value <= 180.0):
            raise ValueError(f"{name} is outside [-180, 180]: {value}")
    for name in ("tx_latitude_deg", "rx_latitude_deg"):
        value = coordinates[name]
        if not math.isfinite(value) or not (-90.0 <= value <= 90.0):
            raise ValueError(f"{name} is outside [-90, 90]: {value}")

    required_profile_columns = {
        "distance_km",
        "terrain_m_asl",
        "clutter_plus_terrain_m_asl",
        "radio_climatic_zone",
        "longitude_deg",
        "latitude_deg",
    }
    missing = sorted(required_profile_columns - set(profile.columns))
    if missing:
        raise ValueError(f"Pilot profile is missing columns: {missing}")
    if len(profile) < 4:
        raise ValueError("P.452 profile must contain at least four points")
    distances = profile["distance_km"].to_numpy(float)
    if abs(distances[0]) > 1e-12 or not np.all(np.diff(distances) > 0):
        raise ValueError("Profile distance must start at zero and increase strictly")
    longitudes = profile["longitude_deg"].to_numpy(float)
    latitudes = profile["latitude_deg"].to_numpy(float)
    if not np.all(np.isfinite(longitudes)) or not np.all(
        (-180.0 <= longitudes) & (longitudes <= 180.0)
    ):
        raise ValueError("Profile contains longitude outside [-180, 180]")
    if not np.all(np.isfinite(latitudes)) or not np.all(
        (-90.0 <= latitudes) & (latitudes <= 90.0)
    ):
        raise ValueError("Profile contains latitude outside [-90, 90]")

    tolerance = float(parameters["coordinate_tolerance_deg"])
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("coordinate_tolerance_deg must be finite and positive")
    endpoint_pairs = [
        ("tx_longitude_deg", coordinates["tx_longitude_deg"], longitudes[0]),
        ("tx_latitude_deg", coordinates["tx_latitude_deg"], latitudes[0]),
        ("rx_longitude_deg", coordinates["rx_longitude_deg"], longitudes[-1]),
        ("rx_latitude_deg", coordinates["rx_latitude_deg"], latitudes[-1]),
    ]
    for name, expected, observed in endpoint_pairs:
        if abs(expected - float(observed)) > tolerance:
            raise ValueError(
                f"Endpoint mismatch for {name}: parameter={expected}, "
                f"profile={observed}, tolerance={tolerance}"
            )

    pol_codes = [int(value) for value in parameters["p452_polarization_codes"]]
    pol_labels = [str(value).upper() for value in parameters["p452_polarization_labels"]]
    if len(pol_codes) == 0 or len(pol_codes) != len(pol_labels):
        raise ValueError("Invalid polarization plan")
    if set(pol_codes) - {1, 2}:
        raise ValueError(f"Unsupported P.452 polarization codes: {pol_codes}")
    if dict(zip(pol_codes, pol_labels)) != {
        code: ("H" if code == 1 else "V") for code in pol_codes
    }:
        raise ValueError("P.452 polarization labels do not match their codes")

    existing_outputs = [name for name in STALE_OUTPUT_NAMES if (root / name).exists()]
    if existing_outputs and not args.allow_existing_matlab_outputs:
        raise ValueError(
            "Stale MATLAB outputs are present before the new run: "
            f"{existing_outputs}. Archive or delete them first."
        )

    print("P.452 PILOT INPUT PREFLIGHT: PASS")
    print(f"Pilot directory: {root}")
    print(f"Profile points: {len(profile)}")
    print(f"Distance: {distances[-1]:.6f} km")
    print(
        "Tx longitude/latitude: "
        f"{coordinates['tx_longitude_deg']:.10f}, "
        f"{coordinates['tx_latitude_deg']:.10f}"
    )
    print(
        "Rx longitude/latitude: "
        f"{coordinates['rx_longitude_deg']:.10f}, "
        f"{coordinates['rx_latitude_deg']:.10f}"
    )
    print(f"P.452 polarization branches: {list(zip(pol_labels, pol_codes))}")
    print("Coordinate convention: signed longitude in [-180, 180]")
    print("Stale MATLAB outputs: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
