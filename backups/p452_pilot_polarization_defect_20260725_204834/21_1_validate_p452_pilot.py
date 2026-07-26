#!/usr/bin/env python3
"""Validate the outputs of the project-specific P.452 pilot run."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COUPLING = [
    "time_index", "incumbent_id", "sector_id", "tone_group", "frequency_ghz",
    "spectral_overlap_fraction", "path_gain_linear", "receiver_gain_linear",
    "element_gain_accounted", "clutter_treatment", "implementation_version", "provenance_note",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-dir", default="data/real/p452_pilot")
    parser.add_argument("--expected-matlab-release", default="2026a")
    args = parser.parse_args()

    root = Path(args.pilot_dir).expanduser().resolve()
    paths = {
        "profile": root / "p452_pilot_profile.csv",
        "parameters": root / "p452_pilot_parameters.json",
        "prep_audit": root / "P452_PILOT_PREP_AUDIT.json",
        "results": root / "p452_pilot_results.csv",
        "coupling": root / "p452_pilot_coupling.csv",
        "matlab_audit": root / "P452_PILOT_MATLAB_AUDIT.json",
        "plot": root / "p452_pilot_profile_review.png",
        "geojson": root / "p452_pilot_path.geojson",
    }
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing {name}: {path}")

    parameters = json.loads(paths["parameters"].read_text(encoding="utf-8"))
    prep = json.loads(paths["prep_audit"].read_text(encoding="utf-8"))
    matlab = json.loads(paths["matlab_audit"].read_text(encoding="utf-8"))
    if prep["status"] != "MATLAB_READY_FROZEN":
        raise ValueError(f"Preparation status is not frozen: {prep['status']}")
    if str(matlab["matlab_release"]).lower() != args.expected_matlab_release.lower():
        raise ValueError(
            f"Unexpected MATLAB release {matlab['matlab_release']}; expected {args.expected_matlab_release}"
        )
    if matlab["p452_reference_commit"] != parameters["p452_reference_commit"]:
        raise ValueError("MATLAB audit commit does not match frozen parameters")
    if matlab["link_id"] != parameters["link_id"]:
        raise ValueError("MATLAB audit link_id does not match frozen parameters")

    profile = pd.read_csv(paths["profile"])
    results = pd.read_csv(paths["results"])
    coupling = pd.read_csv(paths["coupling"])
    if len(profile) < 4:
        raise ValueError("Profile has fewer than four points")
    if abs(float(profile["distance_km"].iloc[0])) > 1e-12:
        raise ValueError("Profile does not start at zero")
    if not np.all(np.diff(profile["distance_km"].to_numpy(float)) > 0):
        raise ValueError("Profile distance is not strictly increasing")
    if not (profile["radio_climatic_zone"].astype(int) == 2).all():
        raise ValueError("Pilot profile contains a non-inland zone")
    if not np.allclose(
        profile["terrain_m_asl"].to_numpy(float),
        profile["clutter_plus_terrain_m_asl"].to_numpy(float),
        rtol=0,
        atol=1e-12,
    ):
        raise ValueError("Pilot profile does not satisfy g=h")

    expected_p = np.asarray(parameters["time_percentages"], dtype=float)
    observed_p = results["time_percentage"].to_numpy(float)
    if len(results) != len(expected_p) or not np.allclose(observed_p, expected_p, rtol=0, atol=1e-12):
        raise ValueError(f"Result p-grid mismatch: expected={expected_p}, observed={observed_p}")
    lb = results["basic_transmission_loss_db"].to_numpy(float)
    gain = results["path_gain_linear"].to_numpy(float)
    if not np.all(np.isfinite(lb)) or not np.all(np.isfinite(gain)):
        raise ValueError("P.452 results contain non-finite values")
    if not np.all(lb > 0) or not np.all((gain > 0) & (gain < 1)):
        raise ValueError("P.452 results are outside basic physical ranges")
    expected_gain = np.power(10.0, -lb / 10.0)
    if not np.allclose(gain, expected_gain, rtol=1e-12, atol=0):
        raise ValueError("path_gain_linear is inconsistent with basic transmission loss")

    missing = [column for column in REQUIRED_COUPLING if column not in coupling]
    if missing:
        raise ValueError(f"Coupling export is missing columns: {missing}")
    if len(coupling) != 1:
        raise ValueError(f"Pilot coupling export must contain one row; found {len(coupling)}")
    row = coupling.iloc[0]
    export_p = float(parameters["export_time_percentage"])
    index = np.flatnonzero(np.isclose(observed_p, export_p, rtol=0, atol=1e-12))
    if len(index) != 1:
        raise ValueError("Export time percentage is absent or duplicated")
    expected_export_gain = float(gain[index[0]])
    if not math.isclose(float(row["path_gain_linear"]), expected_export_gain, rel_tol=1e-12, abs_tol=0):
        raise ValueError("Coupling path gain does not match p-grid result")
    if float(row["receiver_gain_linear"]) != 1.0:
        raise ValueError("Pilot receiver_gain_linear must be 1.0")
    if str(row["clutter_treatment"]) != "none_documented":
        raise ValueError("Unexpected clutter_treatment")
    if "PIPELINE_PILOT_ONLY_NOT_PAPER_EVIDENCE" not in str(row["provenance_note"]):
        raise ValueError("Pilot claim-boundary marker is missing")
    if parameters["p452_reference_commit"] not in str(row["implementation_version"]):
        raise ValueError("P.452 commit is missing from implementation_version")

    # Do not enforce monotonicity as a theorem; report it as a diagnostic only.
    order = np.argsort(observed_p)
    monotone_non_decreasing = bool(np.all(np.diff(lb[order]) >= -1e-9))

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "claim_boundary": "Pipeline audit only; not paper evidence.",
        "link_id": parameters["link_id"],
        "matlab_release": matlab["matlab_release"],
        "p452_reference_commit": parameters["p452_reference_commit"],
        "profile_point_count": int(len(profile)),
        "path_distance_km": float(profile["distance_km"].iloc[-1]),
        "time_percentages": observed_p.tolist(),
        "basic_transmission_loss_db": lb.tolist(),
        "export_time_percentage": export_p,
        "export_path_gain_linear": expected_export_gain,
        "diagnostic_lb_non_decreasing_with_p": monotone_non_decreasing,
        "sha256": {name: sha256_file(path) for name, path in paths.items()},
    }
    report_path = root / "P452_PILOT_VALIDATION.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = f"""# P.452 Pilot Validation

- Status: **PASS**
- Link: `{parameters['link_id']}`
- MATLAB release: `{matlab['matlab_release']}`
- P.452 reference commit: `{parameters['p452_reference_commit']}`
- Profile points: {len(profile)}
- Distance: {profile['distance_km'].iloc[-1]:.6f} km
- Export time percentage: {export_p:g}%
- Export path gain: {expected_export_gain:.12e}
- Diagnostic Lb non-decreasing with p: {monotone_non_decreasing}

This is a pipeline audit only. It is not a cellular-to-incumbent propagation result and must not be used as paper evidence.
"""
    (root / "P452_PILOT_VALIDATION.md").write_text(md, encoding="utf-8")

    print("P.452 PILOT VALIDATION: PASS")
    print(f"Link: {parameters['link_id']}")
    print(f"Profile points: {len(profile)}")
    print(f"Distance: {profile['distance_km'].iloc[-1]:.6f} km")
    print(f"Export p: {export_p:g} %")
    print(f"Export path gain: {expected_export_gain:.12e}")
    print(f"Diagnostic Lb non-decreasing with p: {monotone_non_decreasing}")
    print("Claim boundary: pipeline audit only; not paper evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
