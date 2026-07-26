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
REQUIRED_RESULTS = [
    "polarization_code", "polarization_label", "time_percentage",
    "basic_transmission_loss_db", "path_gain_linear",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalized_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


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

    tafl_tx_pol = str(parameters["tafl_tx_polarization_code"]).strip().upper()
    tafl_rx_pol = str(parameters["tafl_rx_polarization_code"]).strip().upper()
    if tafl_tx_pol != tafl_rx_pol:
        raise ValueError("Frozen TAFL endpoint polarization codes do not match")
    expected_pol_codes = np.asarray(parameters["p452_polarization_codes"], dtype=int)
    expected_pol_labels = np.asarray(parameters["p452_polarization_labels"], dtype=str)
    if len(expected_pol_codes) == 0 or len(expected_pol_codes) != len(expected_pol_labels):
        raise ValueError("Invalid frozen P.452 polarization plan")
    if not set(expected_pol_codes.tolist()).issubset({1, 2}):
        raise ValueError("P.452 polarization codes must be 1 or 2")
    if len(set(expected_pol_codes.tolist())) != len(expected_pol_codes):
        raise ValueError("P.452 polarization codes are duplicated")
    expected_label_by_code = dict(zip(expected_pol_codes.tolist(), expected_pol_labels.tolist()))
    if expected_label_by_code.get(1, "H") != "H" or expected_label_by_code.get(2, "V") != "V":
        raise ValueError("P.452 polarization labels do not match codes")
    if tafl_tx_pol == "G":
        if set(expected_pol_codes.tolist()) != {1, 2}:
            raise ValueError("TAFL G requires both P.452 H and V branches")
        if parameters["polarization_aggregation"] != "none_pipeline_exports_each_branch":
            raise ValueError("TAFL G pilot must export branches without hidden aggregation")

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

    missing_results = [column for column in REQUIRED_RESULTS if column not in results]
    if missing_results:
        raise ValueError(f"Results are missing columns: {missing_results}")

    expected_p = np.asarray(parameters["time_percentages"], dtype=float)
    expected_pairs = {
        (int(code), float(p))
        for code in expected_pol_codes
        for p in expected_p
    }
    observed_pairs = {
        (int(row.polarization_code), float(row.time_percentage))
        for row in results.itertuples(index=False)
    }
    if len(results) != len(expected_pairs) or observed_pairs != expected_pairs:
        raise ValueError(
            f"Result polarization/time grid mismatch: expected={sorted(expected_pairs)}, "
            f"observed={sorted(observed_pairs)}"
        )
    for code, label in expected_label_by_code.items():
        labels = set(
            results.loc[results["polarization_code"].astype(int) == code, "polarization_label"]
            .astype(str)
            .str.upper()
        )
        if labels != {label}:
            raise ValueError(f"Unexpected result labels for pol={code}: {labels}")

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
    if len(coupling) != len(expected_pol_codes):
        raise ValueError(
            f"Pilot coupling export must contain one row per polarization branch; "
            f"expected {len(expected_pol_codes)}, found {len(coupling)}"
        )
    export_p = float(parameters["export_time_percentage"])
    export_results = results.loc[
        np.isclose(results["time_percentage"].to_numpy(float), export_p, rtol=0, atol=1e-12)
    ].copy()
    if len(export_results) != len(expected_pol_codes):
        raise ValueError("Export time percentage does not have one row per polarization")
    export_results["polarization_code"] = export_results["polarization_code"].astype(int)
    export_results = export_results.set_index("polarization_code")

    coupling_codes: dict[int, pd.Series] = {}
    for _, row in coupling.iterrows():
        sector_id = str(row["sector_id"])
        tone_group = str(row["tone_group"])
        if sector_id.endswith("_H") and tone_group == "PILOT_H":
            code = 1
        elif sector_id.endswith("_V") and tone_group == "PILOT_V":
            code = 2
        else:
            raise ValueError(
                f"Could not identify polarization branch from sector_id/tone_group: "
                f"{sector_id!r}, {tone_group!r}"
            )
        if code in coupling_codes:
            raise ValueError(f"Duplicate coupling row for polarization code {code}")
        coupling_codes[code] = row

    if set(coupling_codes) != set(expected_pol_codes.tolist()):
        raise ValueError("Coupling export polarization branches do not match frozen plan")

    export_gains: dict[str, float] = {}
    for code in expected_pol_codes.tolist():
        row = coupling_codes[code]
        expected_export_gain = float(export_results.loc[code, "path_gain_linear"])
        if not math.isclose(
            float(row["path_gain_linear"]),
            expected_export_gain,
            rel_tol=1e-12,
            abs_tol=0,
        ):
            raise ValueError(f"Coupling path gain mismatch for polarization code {code}")
        if float(row["receiver_gain_linear"]) != 1.0:
            raise ValueError("Pilot receiver_gain_linear must be 1.0")
        if str(row["clutter_treatment"]) != "none_documented":
            raise ValueError("Unexpected clutter_treatment")
        if normalized_bool(row["element_gain_accounted"]):
            raise ValueError("Pilot element_gain_accounted must be false")
        provenance = str(row["provenance_note"])
        if "PIPELINE_PILOT_ONLY_NOT_PAPER_EVIDENCE" not in provenance:
            raise ValueError("Pilot claim-boundary marker is missing")
        if "dual_branch_power_aggregation=none" not in provenance:
            raise ValueError("Dual-branch no-aggregation marker is missing")
        if parameters["p452_reference_commit"] not in str(row["implementation_version"]):
            raise ValueError("P.452 commit is missing from implementation_version")
        export_gains[expected_label_by_code[code]] = expected_export_gain

    matlab_codes = {int(v) for v in np.atleast_1d(matlab["p452_polarization_codes"]).tolist()}
    if matlab_codes != set(expected_pol_codes.tolist()):
        raise ValueError("MATLAB audit polarization branches do not match frozen parameters")
    if matlab["polarization_aggregation"] != parameters["polarization_aggregation"]:
        raise ValueError("MATLAB audit polarization aggregation does not match parameters")

    monotonicity_by_pol: dict[str, bool] = {}
    for code, label in expected_label_by_code.items():
        subset = results.loc[results["polarization_code"].astype(int) == code].sort_values(
            "time_percentage"
        )
        monotonicity_by_pol[label] = bool(
            np.all(np.diff(subset["basic_transmission_loss_db"].to_numpy(float)) >= -1e-9)
        )

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "claim_boundary": (
            "Pipeline audit only; not paper evidence. Dual-polarization branches "
            "are exported separately and are not power-aggregated."
        ),
        "link_id": parameters["link_id"],
        "matlab_release": matlab["matlab_release"],
        "p452_reference_commit": parameters["p452_reference_commit"],
        "profile_point_count": int(len(profile)),
        "path_distance_km": float(profile["distance_km"].iloc[-1]),
        "tafl_polarization_code": tafl_tx_pol,
        "tafl_polarization_description": parameters["tafl_polarization_description"],
        "p452_polarization_codes": expected_pol_codes.tolist(),
        "p452_polarization_labels": expected_pol_labels.tolist(),
        "polarization_aggregation": parameters["polarization_aggregation"],
        "time_percentages": expected_p.tolist(),
        "export_time_percentage": export_p,
        "export_path_gain_linear_by_polarization": export_gains,
        "diagnostic_lb_non_decreasing_with_p_by_polarization": monotonicity_by_pol,
        "sha256": {name: sha256_file(path) for name, path in paths.items()},
    }
    report_path = root / "P452_PILOT_VALIDATION.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    gains_text = "\n".join(
        f"- Export path gain {label}: {value:.12e}"
        for label, value in sorted(export_gains.items())
    )
    monotone_text = "\n".join(
        f"- Diagnostic Lb non-decreasing with p ({label}): {value}"
        for label, value in sorted(monotonicity_by_pol.items())
    )
    md = f"""# P.452 Pilot Validation

- Status: **PASS**
- Link: `{parameters['link_id']}`
- MATLAB release: `{matlab['matlab_release']}`
- P.452 reference commit: `{parameters['p452_reference_commit']}`
- Profile points: {len(profile)}
- Distance: {profile['distance_km'].iloc[-1]:.6f} km
- TAFL polarization: `{tafl_tx_pol}` ({parameters['tafl_polarization_description']})
- P.452 branches: {expected_pol_labels.tolist()}
- Export time percentage: {export_p:g}%
{gains_text}
{monotone_text}

The two polarization branches are exported separately. No dual-polarization power aggregation is performed in this pipeline audit.

This is a pipeline audit only. It is not a cellular-to-incumbent propagation result and must not be used as paper evidence.
"""
    (root / "P452_PILOT_VALIDATION.md").write_text(md, encoding="utf-8")

    print("P.452 PILOT VALIDATION: PASS")
    print(f"Link: {parameters['link_id']}")
    print(f"Profile points: {len(profile)}")
    print(f"Distance: {profile['distance_km'].iloc[-1]:.6f} km")
    print(
        f"TAFL polarization: {tafl_tx_pol} "
        f"({parameters['tafl_polarization_description']})"
    )
    print(f"P.452 branches: {expected_pol_labels.tolist()}")
    print(f"Export p: {export_p:g} %")
    for label, value in sorted(export_gains.items()):
        print(f"Export path gain {label}: {value:.12e}")
    print("Dual-branch power aggregation: NONE (pipeline audit)")
    print("Claim boundary: pipeline audit only; not paper evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
