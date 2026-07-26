#!/usr/bin/env python3
"""Freeze the reviewed GTA TAFL pairing rule and export S1 link inputs.

This script is deliberately strict. It does not discover or infer pairs. It only
accepts the output of scripts/03_1_audit_tafl_auth_freq_pairs.py after the audit
has established that every GTA group is an exact 1-TX/1-RX, point-to-point,
authorized, same-frequency group with valid coordinates and a TAFL fade margin.

The output still lacks mean path terrain and an allocated incremental outage.
Those two fields remain blank by design, so the real-mode S1 validator cannot
pass prematurely.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError

EXPECTED_REQUIRED_COLUMNS = {
    "pair_id_candidate",
    "auth_number",
    "frequency_mhz",
    "gta_rx",
    "point_to_point_service_2_subservice_200",
    "fully_authorized_status",
    "same_frequency_within_1khz",
    "coordinates_valid",
    "distance_km",
    "tx_lat_deg",
    "tx_lon_deg",
    "rx_lat_deg",
    "rx_lon_deg",
    "tx_antenna_alt_m_asl",
    "rx_antenna_alt_m_asl",
    "tx_azimuth_error_deg",
    "rx_azimuth_error_deg",
    "tx_freq_rec_id",
    "rx_freq_rec_id",
    "tx_station_location",
    "rx_station_location",
    "rx_unfaded_dbw",
    "rx_threshold_ber1e3_dbw",
    "fade_margin_inputs_present",
    "fade_margin_db_from_tafl",
    "eligible_exact_gta_p2p_authorized",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv_allow_empty(path: Path) -> pd.DataFrame:
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()


def bool_series(series: pd.Series, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }
    values = series.astype(str).str.strip().str.lower().map(mapping)
    if values.isna().any():
        bad = sorted(series[values.isna()].astype(str).unique().tolist())
        raise ValueError(f"Column {name} has unrecognized Boolean values: {bad[:10]}")
    return values.astype(bool)


def finite_numeric(df: pd.DataFrame, columns: list[str]) -> list[str]:
    errors: list[str] = []
    for column in columns:
        values = pd.to_numeric(df[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
            bad_rows = df.loc[values.isna(), "pair_id_candidate"].astype(str).tolist()
            errors.append(f"{column} has missing/non-finite values; examples={bad_rows[:5]}")
    return errors


def ensure_hash(path: Path, expected: str | None, label: str) -> str:
    actual = sha256(path)
    if expected and actual.lower() != expected.lower():
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {expected.lower()}, found {actual.lower()}"
        )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze the dataset-specific GTA auth_number+frequency pairing rule "
            "after a successful read-only TAFL detailed audit."
        )
    )
    parser.add_argument("--audit-dir", default="data/real/tafl_pair_review")
    parser.add_argument(
        "--canonical-source",
        default="data/external/tafl_raw/canonical/TAFL_LTAF_Fixe.csv",
    )
    parser.add_argument(
        "--output-endpoints", default="data/real/tafl_fs_endpoints.csv"
    )
    parser.add_argument(
        "--output-links", default="data/real/paired_fs_links_before_terrain.csv"
    )
    parser.add_argument(
        "--decision-json", default="data/real/TAFL_PAIRING_DECISION.json"
    )
    parser.add_argument(
        "--decision-md", default="data/real/TAFL_PAIRING_DECISION.md"
    )
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--expected-count", type=int, default=70)
    parser.add_argument("--expected-source-sha256")
    parser.add_argument("--expected-summary-sha256")
    parser.add_argument("--expected-eligible-sha256")
    parser.add_argument(
        "--max-azimuth-error-deg",
        type=float,
        default=15.0,
        help=(
            "Project QC gate only; not a regulatory threshold and not the pairing basis. "
            "Default matches the prior detailed-review flag convention."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write frozen decision and export files after all checks pass.",
    )
    args = parser.parse_args()

    audit_dir = Path(args.audit_dir).expanduser().resolve()
    source = Path(args.canonical_source).expanduser().resolve()
    summary_path = audit_dir / "summary.json"
    eligible_path = audit_dir / "gta_eligible_exact_pairs.csv"
    exceptions_path = audit_dir / "gta_exact_pair_exceptions.csv"
    ambiguous_gta_path = audit_dir / "gta_ambiguous_auth_frequency_group_rows.csv"

    required_paths = [source, summary_path, eligible_path]
    missing_paths = [str(path) for path in required_paths if not path.is_file()]
    if missing_paths:
        raise FileNotFoundError(f"Required files are missing: {missing_paths}")

    source_hash = ensure_hash(
        source, args.expected_source_sha256, "canonical TAFL source"
    )
    summary_hash = ensure_hash(summary_path, args.expected_summary_sha256, "audit summary")
    eligible_hash = ensure_hash(
        eligible_path, args.expected_eligible_sha256, "eligible GTA pair table"
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected_summary = {
        "exact_groups_with_gta_rx": args.expected_count,
        "eligible_exact_gta_p2p_fully_authorized": args.expected_count,
        "gta_exact_pair_exceptions": 0,
        "ambiguous_groups_with_gta_rx": 0,
        "eligible_gta_pairs_with_tafl_fade_margin": args.expected_count,
        "eligible_gta_pairs_missing_tafl_fade_margin": 0,
    }
    summary_errors = []
    for key, expected in expected_summary.items():
        actual = summary.get(key)
        if actual != expected:
            summary_errors.append(f"summary[{key!r}] expected {expected}, found {actual}")
    if summary_errors:
        raise ValueError("Audit summary gate failed: " + "; ".join(summary_errors))

    exceptions = read_csv_allow_empty(exceptions_path)
    ambiguous_gta = read_csv_allow_empty(ambiguous_gta_path)
    if not exceptions.empty:
        raise ValueError(
            f"GTA exception table is not empty ({len(exceptions)} rows); pairing cannot be frozen"
        )
    if not ambiguous_gta.empty:
        raise ValueError(
            f"GTA ambiguous-group table is not empty ({len(ambiguous_gta)} rows); pairing cannot be frozen"
        )

    df = pd.read_csv(eligible_path)
    missing_columns = sorted(EXPECTED_REQUIRED_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(f"Eligible-pair table is missing columns: {missing_columns}")
    if len(df) != args.expected_count:
        raise ValueError(f"Expected {args.expected_count} eligible pairs; found {len(df)}")

    errors: list[str] = []
    if df["pair_id_candidate"].astype(str).duplicated().any():
        errors.append("duplicate pair_id_candidate values")
    for column in ["tx_freq_rec_id", "rx_freq_rec_id"]:
        values = df[column].fillna("").astype(str).str.strip()
        if values.eq("").any():
            errors.append(f"{column} has blank values")
        if values.duplicated().any():
            duplicates = values[values.duplicated(keep=False)].unique().tolist()
            errors.append(f"{column} has duplicate record IDs: {duplicates[:5]}")

    for column in [
        "gta_rx",
        "point_to_point_service_2_subservice_200",
        "fully_authorized_status",
        "same_frequency_within_1khz",
        "coordinates_valid",
        "fade_margin_inputs_present",
        "eligible_exact_gta_p2p_authorized",
    ]:
        values = bool_series(df[column], column)
        if not values.all():
            bad = df.loc[~values, "pair_id_candidate"].astype(str).tolist()
            errors.append(f"{column} is not true for all pairs; examples={bad[:5]}")

    numeric_columns = [
        "frequency_mhz",
        "distance_km",
        "tx_lat_deg",
        "tx_lon_deg",
        "rx_lat_deg",
        "rx_lon_deg",
        "tx_antenna_alt_m_asl",
        "rx_antenna_alt_m_asl",
        "tx_azimuth_error_deg",
        "rx_azimuth_error_deg",
        "rx_unfaded_dbw",
        "rx_threshold_ber1e3_dbw",
        "fade_margin_db_from_tafl",
    ]
    errors.extend(finite_numeric(df, numeric_columns))

    frequency = pd.to_numeric(df["frequency_mhz"], errors="coerce")
    distance = pd.to_numeric(df["distance_km"], errors="coerce")
    margin = pd.to_numeric(df["fade_margin_db_from_tafl"], errors="coerce")
    tx_az_error = pd.to_numeric(df["tx_azimuth_error_deg"], errors="coerce")
    rx_az_error = pd.to_numeric(df["rx_azimuth_error_deg"], errors="coerce")

    if ((frequency < 7725.0) | (frequency > 8275.0)).any():
        errors.append("one or more frequencies are outside 7725-8275 MHz")
    if (distance <= 0.05).any():
        bad = df.loc[distance <= 0.05, "pair_id_candidate"].astype(str).tolist()
        errors.append(f"one or more endpoint separations are <=0.05 km: {bad[:5]}")
    if (margin <= 0.0).any():
        bad = df.loc[margin <= 0.0, "pair_id_candidate"].astype(str).tolist()
        errors.append(f"one or more TAFL fade margins are non-positive: {bad[:5]}")

    max_az = float(max(tx_az_error.max(), rx_az_error.max()))
    if max_az > args.max_azimuth_error_deg:
        worst_mask = (tx_az_error > args.max_azimuth_error_deg) | (
            rx_az_error > args.max_azimuth_error_deg
        )
        worst = df.loc[
            worst_mask,
            ["pair_id_candidate", "tx_azimuth_error_deg", "rx_azimuth_error_deg"],
        ]
        errors.append(
            f"azimuth QC error exceeds {args.max_azimuth_error_deg:g} deg; "
            f"examples={worst.head(5).to_dict(orient='records')}"
        )

    # Reconcile record count with physical-site count without deduplicating S1 links.
    rounded_lat = pd.to_numeric(df["rx_lat_deg"], errors="coerce").round(7)
    rounded_lon = pd.to_numeric(df["rx_lon_deg"], errors="coerce").round(7)
    unique_rx_coordinates = int(pd.DataFrame({"lat": rounded_lat, "lon": rounded_lon}).drop_duplicates().shape[0])
    unique_rx_locations = int(
        df[["rx_station_location", "rx_lat_deg", "rx_lon_deg"]]
        .astype(str)
        .drop_duplicates()
        .shape[0]
    )

    metrics = {
        "pair_count": int(len(df)),
        "unique_rx_frequency_record_count": int(df["rx_freq_rec_id"].nunique()),
        "unique_rx_coordinate_count_rounded_1e-7_deg": unique_rx_coordinates,
        "unique_rx_location_coordinate_count": unique_rx_locations,
        "frequency_mhz_min": float(frequency.min()),
        "frequency_mhz_max": float(frequency.max()),
        "distance_km_min": float(distance.min()),
        "distance_km_max": float(distance.max()),
        "fade_margin_db_min": float(margin.min()),
        "fade_margin_db_median": float(margin.median()),
        "fade_margin_db_max": float(margin.max()),
        "tx_azimuth_error_deg_max": float(tx_az_error.max()),
        "rx_azimuth_error_deg_max": float(rx_az_error.max()),
        "azimuth_qc_threshold_deg": float(args.max_azimuth_error_deg),
    }

    print("TAFL GTA PAIRING FREEZE PREFLIGHT")
    print(json.dumps(metrics, indent=2, sort_keys=True))

    if errors:
        print("PAIRING FREEZE PREFLIGHT: FAIL", file=sys.stderr)
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    print("PAIRING FREEZE PREFLIGHT: PASS")
    if not args.confirm:
        print("No files were written because --confirm was not supplied.")
        return 0

    output_endpoints = Path(args.output_endpoints).expanduser().resolve()
    output_links = Path(args.output_links).expanduser().resolve()
    decision_json = Path(args.decision_json).expanduser().resolve()
    decision_md = Path(args.decision_md).expanduser().resolve()
    for path in [output_endpoints, output_links, decision_json, decision_md]:
        path.parent.mkdir(parents=True, exist_ok=True)

    endpoint_rows: list[dict[str, Any]] = []
    for _, row in df.sort_values(["auth_number", "frequency_mhz"]).iterrows():
        for role, prefix in [("TX", "tx"), ("RX", "rx")]:
            endpoint_rows.append(
                {
                    "PAIR_ID": str(row["pair_id_candidate"]),
                    "ROLE": role,
                    "LATITUDE": float(row[f"{prefix}_lat_deg"]),
                    "LONGITUDE": float(row[f"{prefix}_lon_deg"]),
                    "ANTENNA_ALT_M_ASL": float(row[f"{prefix}_antenna_alt_m_asl"]),
                    "FREQUENCY_GHZ": float(row["frequency_mhz"]) / 1000.0,
                    "RECORD_ID": str(row[f"{prefix}_freq_rec_id"]),
                    "AUTH_NUMBER": str(row["auth_number"]),
                    "STATION_LOCATION": str(row[f"{prefix}_station_location"]),
                    "PAIRING_RULE": "same authorization_number + same frequency; exactly one TX and one RX",
                }
            )
    endpoints_df = pd.DataFrame(endpoint_rows)

    links_df = pd.DataFrame(
        {
            "link_id": df["pair_id_candidate"].astype(str),
            "tx_lat_deg": pd.to_numeric(df["tx_lat_deg"]),
            "tx_lon_deg": pd.to_numeric(df["tx_lon_deg"]),
            "rx_lat_deg": pd.to_numeric(df["rx_lat_deg"]),
            "rx_lon_deg": pd.to_numeric(df["rx_lon_deg"]),
            "tx_antenna_alt_m_asl": pd.to_numeric(df["tx_antenna_alt_m_asl"]),
            "rx_antenna_alt_m_asl": pd.to_numeric(df["rx_antenna_alt_m_asl"]),
            "mean_terrain_elevation_m_asl": np.nan,
            "frequency_ghz": pd.to_numeric(df["frequency_mhz"]) / 1000.0,
            "fade_margin_db": pd.to_numeric(df["fade_margin_db_from_tafl"]),
            "allocated_incremental_outage_pct": np.nan,
            "k_override_percent": np.nan,
            "dn75_override_n_units": np.nan,
            "wanted_received_level_dbm": pd.to_numeric(df["rx_unfaded_dbw"]) + 30.0,
            "receiver_threshold_dbm": pd.to_numeric(df["rx_threshold_ber1e3_dbw"]) + 30.0,
            "other_reserved_margin_db": np.nan,
            "tx_source_record_id": df["tx_freq_rec_id"].astype(str),
            "rx_source_record_id": df["rx_freq_rec_id"].astype(str),
            "tafl_auth_number": df["auth_number"].astype(str),
            "tafl_rx_unfaded_dbw": pd.to_numeric(df["rx_unfaded_dbw"]),
            "tafl_rx_threshold_ber1e3_dbw": pd.to_numeric(
                df["rx_threshold_ber1e3_dbw"]
            ),
            "provenance_note": [
                (
                    "Frozen TAFL source SHA-256="
                    f"{source_hash}; paired by authorization_number+frequency only when "
                    "the frozen group contained exactly one TX and one RX; service=2, "
                    "subservice=200; authorized; same-frequency; valid coordinates; "
                    "fade_margin_db=TAFL rx_unfaded_dbw-rx_threshold_ber1e3_dbw. "
                    "Mean path terrain and outage allocation remain unfilled."
                )
                for _ in range(len(df))
            ],
        }
    ).sort_values("link_id")

    endpoints_df.to_csv(output_endpoints, index=False)
    links_df.to_csv(output_links, index=False)

    now = datetime.now(timezone.utc).isoformat()
    decision = {
        "decision": "FROZEN_FOR_THIS_DATASET_AND_GTA_FILTER",
        "reviewer": args.reviewer,
        "decided_utc": now,
        "canonical_source": str(source),
        "canonical_source_sha256": source_hash,
        "audit_summary": str(summary_path),
        "audit_summary_sha256": summary_hash,
        "eligible_pair_table": str(eligible_path),
        "eligible_pair_table_sha256": eligible_hash,
        "pairing_rule": (
            "Within the frozen 7725-8275 MHz TAFL snapshot and GTA receiver box, "
            "group by authorization_number and frequency rounded to 0.001 MHz; retain "
            "only groups with exactly one TX and one RX, service 2/subservice 200, "
            "authorized status, same endpoint frequency, valid coordinates, and TAFL "
            "wanted-level/threshold inputs. Quarantine every other group."
        ),
        "claim_boundary": (
            "This is a deterministic extraction rule for the cited frozen TAFL snapshot "
            "and study filter. It is not a claim that authorization_number+frequency is "
            "a universal link identifier in all TAFL releases or services. Geometry was "
            "used only as a corroborative QC check, never to select a partner."
        ),
        "metrics": metrics,
        "outputs": {
            "endpoints_csv": str(output_endpoints),
            "endpoints_sha256": sha256(output_endpoints),
            "links_before_terrain_csv": str(output_links),
            "links_before_terrain_sha256": sha256(output_links),
        },
        "remaining_blockers": [
            "mean_terrain_elevation_m_asl from a reviewed ground-elevation DEM/profile",
            "explicit allocated_incremental_outage_pct decision",
        ],
    }
    decision_json.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = f"""# TAFL GTA Pairing Decision\n\n- **Decision:** Frozen for this dataset and GTA filter\n- **Reviewer:** {args.reviewer}\n- **UTC time:** {now}\n- **Canonical source SHA-256:** `{source_hash}`\n- **Eligible pair table SHA-256:** `{eligible_hash}`\n- **Frequency-specific directed links retained:** {metrics['pair_count']}\n- **Unique RX coordinates (rounded to 1e-7 degree):** {metrics['unique_rx_coordinate_count_rounded_1e-7_deg']}\n\n## Frozen rule\n\nWithin the frozen 7725–8275 MHz TAFL snapshot and GTA receiver box, group by authorization number and frequency rounded to 0.001 MHz. Retain only groups containing exactly one TX and one RX, service 2/subservice 200, authorized status, equal endpoint frequency, valid coordinates, and TAFL wanted-level/threshold inputs. Quarantine every other group.\n\n## Claim boundary\n\nThis rule is frozen only for the cited source snapshot and study filter. It does not assert that authorization number plus frequency is a universal TAFL link identifier. Antenna geometry is a corroborative QC check and was never used to invent or select a partner.\n\n## Remaining blockers before real S1 validation\n\n1. Add reviewed mean path terrain elevation for every link.\n2. Declare and document the incremental worst-month outage allocation.\n\n"""
    decision_md.write_text(md, encoding="utf-8")

    print(f"Wrote endpoints: {output_endpoints}")
    print(f"Wrote unfinished S1 links: {output_links}")
    print(f"Wrote decision: {decision_json}")
    print("PAIRING RULE FREEZE: PASS")
    print("Do not run the real S1 validator yet: terrain and outage allocation are intentionally blank.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
