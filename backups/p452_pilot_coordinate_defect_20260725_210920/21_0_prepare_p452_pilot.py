#!/usr/bin/env python3
"""Prepare and freeze one audited project-specific P.452 pilot path.

The pilot deliberately reuses one frozen fixed-service wanted-link path. Its
purpose is to verify profile formatting, terminal-height accounting, MATLAB
interchange, units, and provenance before any cellular-to-incumbent coupling
campaign is generated. It is not a paper experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

TAFL_COLUMNS = [
    "txrx", "freq_mhz", "freq_rec_id", "reg_service", "comm_type", "conformity",
    "alloc_name", "channel", "intl_coord", "analog_digital", "occ_bw_khz",
    "emission_desig", "modulation", "filtration", "tx_erp_dbw", "tx_power_w",
    "total_losses_db", "analog_cap", "digital_cap", "rx_unfaded_dbw",
    "rx_thresh_ber1e3_dbw", "ant_manufacturer", "ant_model", "ant_gain_dbi",
    "ant_pattern", "hpbw_deg", "f2b_db", "polarization", "height_agl_m",
    "azimuth_deg", "elev_angle_deg", "station_loc", "licensee_ref", "call_sign",
    "station_type", "itu_class", "cost_cat", "n_identical", "ref_id", "province",
    "lat", "lon", "ground_elev_m", "struct_height_m", "congestion", "radius_km",
    "satellite_name", "auth_number", "service", "subservice", "licence_type",
    "auth_status", "in_service_date", "account", "licensee_name", "licensee_addr",
    "op_status", "stn_class", "h_pow_w", "v_pow_w", "standby",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text in {"", "-", "nan", "NaN", "NAN"} else text


def normalize_numeric_identifier(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.fullmatch(r"([0-9]+)(?:\.0+)?", text)
    if match is None:
        return None
    digits = match.group(1)
    return digits.lstrip("0") or "0"


def resolve_id(input_id: str, resolution: pd.DataFrame, canonical: pd.DataFrame) -> str:
    mapping = resolution.set_index("input_source_record_id")["canonical_freq_rec_id"].astype(str)
    if input_id in mapping.index:
        return str(mapping.loc[input_id])
    canonical_ids = canonical["freq_rec_id"].fillna("").astype(str).str.strip()
    exact = canonical_ids[canonical_ids == input_id]
    if len(exact) == 1:
        return input_id
    target = normalize_numeric_identifier(input_id)
    candidates = sorted({v for v in canonical_ids if normalize_numeric_identifier(v) == target})
    if len(candidates) != 1:
        raise ValueError(
            f"Could not uniquely resolve source ID {input_id!r}; candidates={candidates[:10]}"
        )
    return candidates[0]


def validate_tafl_endpoint_roles(
    tx: pd.Series,
    rx: pd.Series,
    tx_id: str,
    rx_id: str,
) -> tuple[str, str]:
    """Validate the canonical TAFL endpoint-role codes for the frozen source.

    The ISED TAFL Fixed Service extract used by this project stores endpoint
    roles as the full strings ``TX`` and ``RX``.  Earlier project audit and
    allocation-evidence scripts use those same codes.  This helper deliberately
    rejects shortened ``T``/``R`` values so a schema mismatch cannot pass
    silently.
    """
    tx_role = clean_text(tx["txrx"]).upper()
    rx_role = clean_text(rx["txrx"]).upper()
    if tx_role != "TX" or rx_role != "RX":
        raise ValueError(
            "Resolved TAFL records do not have expected TX/RX roles: "
            f"tx_id={tx_id!r}, tx_role={tx_role!r}, "
            f"rx_id={rx_id!r}, rx_role={rx_role!r}"
        )
    return tx_role, rx_role


TAFL_POLARIZATION_DESCRIPTIONS = {
    "A": "Horizontal",
    "B": "Vertical",
    "L": "Dual",
    "D": "Circular, right",
    "E": "Circular, left",
    "J": "Linear (orientation unspecified)",
    "M": "Mixed",
    "N": "Slant, right",
    "P": "Slant, left",
    "H": "Elliptical",
    "C": "Horizontal or vertical selectable",
    "G": "Co-channel dual polarization",
}


def parse_polarization_plan(
    tx_value: Any,
    rx_value: Any,
    override: Any,
) -> dict[str, Any]:
    """Translate official ISED TAFL polarization codes into a P.452 run plan.

    ITU-R P.452 accepts only ``pol=1`` (horizontal) or ``pol=2`` (vertical).
    The ISED TAFL extract uses its own coded vocabulary.  In particular,
    ``A`` means horizontal, ``B`` means vertical, and ``G`` means co-channel
    dual polarization.  A ``G/G`` pair is therefore evaluated twice, once for
    each P.452 polarization.  The pilot exports both branches separately and
    performs no hidden power aggregation.

    Other non-H/V TAFL codes are not silently approximated.  They require a
    documented override or a future polarization-specific extension.
    """
    tx_code = clean_text(tx_value).upper()
    rx_code = clean_text(rx_value).upper()
    if tx_code != rx_code:
        raise ValueError(
            "TAFL endpoint polarization codes do not match: "
            f"tx={tx_code!r}, rx={rx_code!r}"
        )

    if override is not None:
        value = str(override).strip().upper()
        if value in {"H", "1", "HORIZONTAL"}:
            codes = [1]
            labels = ["H"]
            source = "documented_override_horizontal"
        elif value in {"V", "2", "VERTICAL"}:
            codes = [2]
            labels = ["V"]
            source = "documented_override_vertical"
        else:
            raise ValueError(
                "polarization_override must be H/1/horizontal, "
                "V/2/vertical, or null"
            )
        return {
            "tafl_code": tx_code,
            "tafl_description": TAFL_POLARIZATION_DESCRIPTIONS.get(
                tx_code, "Unknown/undocumented TAFL code"
            ),
            "p452_codes": codes,
            "p452_labels": labels,
            "mode": source,
            "aggregation": "none_pipeline_exports_each_branch",
        }

    if tx_code == "A":
        return {
            "tafl_code": tx_code,
            "tafl_description": TAFL_POLARIZATION_DESCRIPTIONS[tx_code],
            "p452_codes": [1],
            "p452_labels": ["H"],
            "mode": "tafl_horizontal",
            "aggregation": "single_branch",
        }
    if tx_code == "B":
        return {
            "tafl_code": tx_code,
            "tafl_description": TAFL_POLARIZATION_DESCRIPTIONS[tx_code],
            "p452_codes": [2],
            "p452_labels": ["V"],
            "mode": "tafl_vertical",
            "aggregation": "single_branch",
        }
    if tx_code == "G":
        return {
            "tafl_code": tx_code,
            "tafl_description": TAFL_POLARIZATION_DESCRIPTIONS[tx_code],
            "p452_codes": [1, 2],
            "p452_labels": ["H", "V"],
            "mode": "tafl_cochannel_dual_evaluate_both",
            "aggregation": "none_pipeline_exports_each_branch",
        }

    description = TAFL_POLARIZATION_DESCRIPTIONS.get(
        tx_code, "Unknown/undocumented TAFL code"
    )
    raise ValueError(
        "TAFL polarization cannot be mapped uniquely to P.452 horizontal/vertical: "
        f"code={tx_code!r}, description={description!r}. "
        "Use a documented polarization_override only when an authoritative "
        "source establishes the actual branch."
    )


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)


def load_yaml(path: Path) -> dict[str, Any]:
    require_file(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML mapping")
    return data


def bool_value(value: Any) -> bool:
    return bool(value is True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/p452_pilot.yaml")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Freeze MATLAB-ready inputs after every manual confirmation is true",
    )
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    cfg = load_yaml(config_path)
    inputs = cfg["inputs"]
    pilot = cfg["pilot"]
    confirmations = cfg["manual_confirmations"]

    links_path = Path(inputs["links_csv"]).resolve()
    profile_path = Path(inputs["terrain_profiles_csv_gz"]).resolve()
    summary_path = Path(inputs["terrain_summary_csv"]).resolve()
    tafl_path = Path(inputs["canonical_tafl_csv"]).resolve()
    resolution_path = Path(inputs["source_id_resolution_csv"]).resolve()
    commit_path = Path(inputs["p452_reference_commit_file"]).resolve()
    evidence_path = Path(inputs["p452_reference_evidence_file"]).resolve()
    for path in [links_path, profile_path, summary_path, tafl_path, resolution_path, commit_path, evidence_path]:
        require_file(path)

    link_id = str(pilot["link_id"])
    out_dir = Path(pilot["output_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    links = pd.read_csv(
        links_path,
        dtype={"link_id": str, "tx_source_record_id": str, "rx_source_record_id": str},
    )
    selected = links.loc[links["link_id"].astype(str) == link_id]
    if len(selected) != 1:
        raise ValueError(f"Expected exactly one row for link_id={link_id!r}; found {len(selected)}")
    link = selected.iloc[0]

    profiles = pd.read_csv(profile_path)
    profile = profiles.loc[profiles["link_id"].astype(str) == link_id].copy()
    profile = profile.sort_values("sample_index")
    if len(profile) < 4:
        raise ValueError(f"Pilot path has only {len(profile)} profile points; at least 4 are required")

    summary = pd.read_csv(summary_path)
    selected_summary = summary.loc[summary["link_id"].astype(str) == link_id]
    if len(selected_summary) != 1:
        raise ValueError(f"Expected one terrain summary row for {link_id}; found {len(selected_summary)}")
    terrain = selected_summary.iloc[0]
    if int(terrain["qc_flag_count"]) != 0:
        raise ValueError(f"Terrain summary contains unresolved QC flags: {terrain['qc_flags']}")

    # Endpoint consistency.
    tol_deg = float(pilot["coordinate_tolerance_deg"])
    endpoint_pairs = [
        ("tx_lat_deg", float(profile.iloc[0]["latitude_deg"])),
        ("tx_lon_deg", float(profile.iloc[0]["longitude_deg"])),
        ("rx_lat_deg", float(profile.iloc[-1]["latitude_deg"])),
        ("rx_lon_deg", float(profile.iloc[-1]["longitude_deg"])),
    ]
    for column, observed in endpoint_pairs:
        expected = float(link[column])
        if abs(expected - observed) > tol_deg:
            raise ValueError(
                f"Endpoint mismatch for {column}: link={expected}, profile={observed}, tol={tol_deg}"
            )

    d_m = pd.to_numeric(profile["distance_from_tx_m"], errors="raise").to_numpy(float)
    h = pd.to_numeric(profile["elevation_m_asl"], errors="raise").to_numpy(float)
    if not np.all(np.isfinite(d_m)) or not np.all(np.isfinite(h)):
        raise ValueError("Profile contains non-finite values")
    if abs(d_m[0]) > 1e-9 or np.any(np.diff(d_m) <= 0):
        raise ValueError("Profile distance must start at zero and be strictly increasing")

    htg = float(link["tx_antenna_alt_m_asl"]) - float(h[0])
    hrg = float(link["rx_antenna_alt_m_asl"]) - float(h[-1])
    if htg <= 0 or hrg <= 0:
        raise ValueError(f"Non-positive terminal height above profile ground: htg={htg}, hrg={hrg}")
    endpoint_tol = float(pilot["endpoint_height_tolerance_m"])
    if abs(htg - float(terrain["tx_implied_antenna_height_agl_m"])) > endpoint_tol:
        raise ValueError("Tx height above terrain disagrees with frozen terrain summary")
    if abs(hrg - float(terrain["rx_implied_antenna_height_agl_m"])) > endpoint_tol:
        raise ValueError("Rx height above terrain disagrees with frozen terrain summary")

    tafl = pd.read_csv(tafl_path, header=None, names=TAFL_COLUMNS, dtype=str, keep_default_na=False)
    resolution = pd.read_csv(resolution_path, dtype=str, keep_default_na=False)
    tx_input_id = clean_text(link["tx_source_record_id"])
    rx_input_id = clean_text(link["rx_source_record_id"])
    tx_id = resolve_id(tx_input_id, resolution, tafl)
    rx_id = resolve_id(rx_input_id, resolution, tafl)
    tafl_index = tafl.set_index(tafl["freq_rec_id"].astype(str).str.strip(), drop=False)
    if tx_id not in tafl_index.index or rx_id not in tafl_index.index:
        raise ValueError("Resolved TAFL IDs are absent from the canonical source")
    tx = tafl_index.loc[tx_id]
    rx = tafl_index.loc[rx_id]
    if isinstance(tx, pd.DataFrame) or isinstance(rx, pd.DataFrame):
        raise ValueError("Canonical TAFL source ID is not unique")
    tx_role, rx_role = validate_tafl_endpoint_roles(tx, rx, tx_id, rx_id)

    polarization_plan = parse_polarization_plan(
        tx["polarization"],
        rx["polarization"],
        pilot.get("polarization_override"),
    )

    if str(pilot["terminal_gain_mode"]) != "isotropic_zero_dbi":
        raise ValueError("Pilot version 1 supports only terminal_gain_mode=isotropic_zero_dbi")
    gt = float(pilot["tx_horizon_gain_dbi"])
    gr = float(pilot["rx_horizon_gain_dbi"])
    if abs(gt) > 1e-12 or abs(gr) > 1e-12:
        raise ValueError("isotropic_zero_dbi mode requires both horizon gains to equal 0 dBi")
    if str(pilot["clutter_mode"]) != "none":
        raise ValueError("Pilot version 1 supports clutter_mode=none only")
    zone_code = int(pilot["radio_climatic_zone_code"])
    if zone_code != 2:
        raise ValueError("This pilot is intentionally limited to a manually reviewed all-inland path (zone=2)")

    time_percentages = [float(v) for v in pilot["time_percentages"]]
    if not time_percentages or any(not (0.001 <= v <= 50.0) for v in time_percentages):
        raise ValueError("All P.452 time percentages must lie in [0.001, 50]")
    export_p = float(pilot["export_time_percentage"])
    if export_p not in time_percentages:
        raise ValueError("export_time_percentage must be included in time_percentages")

    commit = commit_path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", commit):
        raise ValueError(f"Invalid P.452 commit string: {commit!r}")

    pilot_profile = pd.DataFrame(
        {
            "sample_index": profile["sample_index"].astype(int),
            "distance_km": d_m / 1000.0,
            "terrain_m_asl": h,
            "clutter_plus_terrain_m_asl": h,
            "radio_climatic_zone": np.full(len(profile), zone_code, dtype=int),
            "longitude_deg": pd.to_numeric(profile["longitude_deg"]),
            "latitude_deg": pd.to_numeric(profile["latitude_deg"]),
        }
    )
    pilot_profile_path = out_dir / "p452_pilot_profile.csv"
    pilot_profile.to_csv(pilot_profile_path, index=False)

    parameters = {
        "purpose": cfg["purpose"],
        "link_id": link_id,
        "frequency_ghz": float(link["frequency_ghz"]),
        "time_percentages": time_percentages,
        "export_time_percentage": export_p,
        "htg_m": htg,
        "hrg_m": hrg,
        "tx_longitude_deg": float(link["tx_lon_deg"]) % 360.0,
        "tx_latitude_deg": float(link["tx_lat_deg"]),
        "rx_longitude_deg": float(link["rx_lon_deg"]) % 360.0,
        "rx_latitude_deg": float(link["rx_lat_deg"]),
        "tx_horizon_gain_dbi": gt,
        "rx_horizon_gain_dbi": gr,
        "tafl_tx_polarization_code": clean_text(tx["polarization"]).upper(),
        "tafl_rx_polarization_code": clean_text(rx["polarization"]).upper(),
        "tafl_polarization_description": polarization_plan["tafl_description"],
        "p452_polarization_codes": polarization_plan["p452_codes"],
        "p452_polarization_labels": polarization_plan["p452_labels"],
        "polarization_mode": polarization_plan["mode"],
        "polarization_aggregation": polarization_plan["aggregation"],
        "dct_km": float(pilot["dct_km"]),
        "dcr_km": float(pilot["dcr_km"]),
        "pressure_hpa": float(pilot["pressure_hpa"]),
        "temperature_c": float(pilot["temperature_c"]),
        "clutter_treatment": "none_documented",
        "terminal_gain_accounting": (
            "P.452 called with Gt=Gr=0 dBi. Exported path_gain_linear is 10^(-Lb/10); "
            "no directional terminal or array gain is separately included in the pilot."
        ),
        "p452_reference_commit": commit,
        "matlab_release_required": "R2026a",
        "pilot_profile_csv": str(pilot_profile_path),
        "pilot_profile_sha256": sha256_file(pilot_profile_path),
        "canonical_tafl_tx_id": tx_id,
        "canonical_tafl_rx_id": rx_id,
        "canonical_tafl_tx_role": tx_role,
        "canonical_tafl_rx_role": rx_role,
        "tafl_tx_antenna_gain_dbi_for_reference_only": clean_text(tx["ant_gain_dbi"]),
        "tafl_rx_antenna_gain_dbi_for_reference_only": clean_text(rx["ant_gain_dbi"]),
        "tafl_tx_azimuth_deg_for_reference_only": clean_text(tx["azimuth_deg"]),
        "tafl_rx_azimuth_deg_for_reference_only": clean_text(rx["azimuth_deg"]),
    }
    parameters_path = out_dir / "p452_pilot_parameters.json"
    parameters_path.write_text(json.dumps(parameters, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"link_id": link_id, "purpose": "P452_PIPELINE_PILOT_ONLY"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": pilot_profile[["longitude_deg", "latitude_deg"]].to_numpy().tolist(),
                },
            }
        ],
    }
    geojson_path = out_dir / "p452_pilot_path.geojson"
    geojson_path.write_text(json.dumps(geojson, indent=2) + "\n", encoding="utf-8")

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(pilot_profile["distance_km"], pilot_profile["terrain_m_asl"], linewidth=1.5)
    ax.scatter([0, pilot_profile["distance_km"].iloc[-1]], [h[0], h[-1]], s=30)
    ax.set_xlabel("Distance from transmitter (km)")
    ax.set_ylabel("Terrain elevation (m ASL)")
    ax.set_title(f"P.452 pipeline pilot terrain profile\n{link_id}")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plot_path = out_dir / "p452_pilot_profile_review.png"
    fig.savefig(plot_path, dpi=180)
    plt.close(fig)

    confirmation_names = [
        "profile_plot_reviewed",
        "path_has_no_p452_sea_segment",
        "tx_is_at_least_5km_from_sea_coast",
        "rx_is_at_least_5km_from_sea_coast",
        "understood_pipeline_only_status",
    ]
    confirmation_state = {name: bool_value(confirmations.get(name)) for name in confirmation_names}
    all_confirmed = all(confirmation_state.values())
    ready = bool(args.confirm and all_confirmed)

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "MATLAB_READY_FROZEN" if ready else "REVIEW_REQUIRED",
        "confirm_flag_supplied": bool(args.confirm),
        "manual_confirmations": confirmation_state,
        "inputs_sha256": {
            str(path): sha256_file(path)
            for path in [links_path, profile_path, summary_path, tafl_path, resolution_path, commit_path, evidence_path, config_path]
        },
        "outputs_sha256": {
            str(path): sha256_file(path)
            for path in [pilot_profile_path, parameters_path, geojson_path, plot_path]
        },
        "profile_point_count": int(len(pilot_profile)),
        "path_distance_km": float(pilot_profile["distance_km"].iloc[-1]),
        "terminal_heights_agl_m": {"tx": htg, "rx": hrg},
        "claim_boundary": (
            "This path reuses a fixed-service wanted-link endpoint pair solely to audit the P.452 pipeline. "
            "It is not a cellular base-station-to-incumbent coupling result and is not paper evidence."
        ),
    }
    audit_path = out_dir / "P452_PILOT_PREP_AUDIT.json"
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    checklist = f"""# P.452 Pilot Review Checklist

Pilot link: `{link_id}`

Before freezing MATLAB-ready inputs, review:

- [ ] `{plot_path}` contains a physically plausible terrain profile.
- [ ] `{geojson_path}` shows no P.452 sea segment along the path.
- [ ] The transmitter is at least 5 km from the sea coast.
- [ ] The receiver is at least 5 km from the sea coast.
- [ ] The pilot is understood to be a pipeline audit only, not a cellular interference result.

After review, set every item under `manual_confirmations` in `{config_path}` to `true`, then rerun with `--confirm`.

P.452 modeling choices for this pilot:

- distributed clutter: none (`g=h`);
- radio-climatic zone: inland (`2`) at every profile point;
- horizon gains passed to P.452: 0 dBi at both terminals;
- dct=dcr=5 km, usable only after confirming both terminals are at least 5 km from the sea coast;
- pressure: {parameters['pressure_hpa']} hPa;
- temperature: {parameters['temperature_c']} °C;
- TAFL polarization: {parameters['tafl_tx_polarization_code']} ({parameters['tafl_polarization_description']});
- P.452 branches: {parameters['p452_polarization_labels']} with codes {parameters['p452_polarization_codes']};
- polarization aggregation: {parameters['polarization_aggregation']}.
"""
    checklist_path = out_dir / "P452_PILOT_REVIEW_CHECKLIST.md"
    checklist_path.write_text(checklist, encoding="utf-8")

    print("P.452 PILOT PREPARATION: PASS")
    print(f"Link: {link_id}")
    print(f"Profile points: {len(pilot_profile)}")
    print(f"Distance: {pilot_profile['distance_km'].iloc[-1]:.6f} km")
    print(f"Tx/Rx heights AGL: {htg:.3f} / {hrg:.3f} m")
    print(f"Output directory: {out_dir}")
    if ready:
        print("P.452 PILOT FREEZE: PASS — MATLAB-ready inputs are frozen")
        return 0
    if args.confirm and not all_confirmed:
        missing = [name for name, value in confirmation_state.items() if not value]
        print(f"P.452 PILOT FREEZE: REFUSED — missing confirmations: {missing}")
        return 2
    print("REVIEW REQUIRED: inspect the PNG, GeoJSON, and checklist; no MATLAB-ready freeze was claimed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
