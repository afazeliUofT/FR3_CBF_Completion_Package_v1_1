#!/usr/bin/env python3
"""Build a read-only evidence table for the S1 outage-allocation decision.

This script deliberately does NOT choose or populate an outage allocation.
It verifies the frozen terrain-stage input, joins each frozen link back to its
canonical TAFL TX/RX frequency records, and exposes the equipment/capacity
metadata needed for a standards-anchored engineering decision.
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

ID_COLUMNS = ["link_id", "tx_source_record_id", "rx_source_record_id", "tafl_auth_number"]
NUMERIC_TAFL = [
    "freq_mhz", "occ_bw_khz", "digital_cap", "analog_cap", "lat", "lon",
    "service", "subservice", "rx_unfaded_dbw", "rx_thresh_ber1e3_dbw",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text in {"", "-", "nan", "NaN", "NAN"} else text


def finite_float(value: Any) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return x if math.isfinite(x) else float("nan")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))


def semicolon_counts(series: pd.Series) -> str:
    counts = series.fillna("").astype(str).replace("", "<blank>").value_counts(dropna=False)
    return "; ".join(f"{idx}={int(count)}" for idx, count in counts.items())


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a read-only S1 allocation evidence table by joining the frozen 70-link "
            "terrain output to its canonical TAFL TX/RX frequency records. No allocation is chosen."
        )
    )
    parser.add_argument(
        "--links",
        default="data/real/paired_fs_links_before_allocation.csv",
        help="Frozen terrain-stage link table with blank outage allocation",
    )
    parser.add_argument(
        "--tafl",
        default="data/external/tafl_raw/canonical/TAFL_LTAF_Fixe.csv",
        help="Canonical frozen TAFL Fixed Service CSV",
    )
    parser.add_argument(
        "--terrain-decision",
        default="data/real/TERRAIN_DECISION.json",
    )
    parser.add_argument(
        "--pairing-decision",
        default="data/real/TAFL_PAIRING_DECISION.json",
    )
    parser.add_argument(
        "--out-dir",
        default="data/real/s1_allocation_review",
    )
    parser.add_argument("--expected-links", type=int, default=70)
    args = parser.parse_args()

    links_path = Path(args.links).expanduser().resolve()
    tafl_path = Path(args.tafl).expanduser().resolve()
    terrain_decision_path = Path(args.terrain_decision).expanduser().resolve()
    pairing_decision_path = Path(args.pairing_decision).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()

    for path in [links_path, tafl_path, terrain_decision_path, pairing_decision_path]:
        require_file(path)
    if args.expected_links <= 0:
        raise ValueError("--expected-links must be positive")

    terrain_decision = json.loads(terrain_decision_path.read_text(encoding="utf-8"))
    pairing_decision = json.loads(pairing_decision_path.read_text(encoding="utf-8"))

    links_hash = sha256_file(links_path)
    tafl_hash = sha256_file(tafl_path)

    expected_links_hash = clean_text(terrain_decision.get("output", {}).get("sha256", "")).lower()
    if not expected_links_hash:
        raise ValueError("TERRAIN_DECISION.json does not contain output.sha256")
    if links_hash != expected_links_hash:
        raise ValueError(
            f"Frozen links hash mismatch: terrain decision={expected_links_hash}, actual={links_hash}"
        )

    expected_tafl_hash = clean_text(pairing_decision.get("canonical_source_sha256", "")).lower()
    if not expected_tafl_hash:
        raise ValueError("TAFL_PAIRING_DECISION.json does not contain canonical_source_sha256")
    if tafl_hash != expected_tafl_hash:
        raise ValueError(
            f"Canonical TAFL hash mismatch: pairing decision={expected_tafl_hash}, actual={tafl_hash}"
        )

    links = pd.read_csv(
        links_path,
        dtype={col: str for col in ID_COLUMNS},
        keep_default_na=True,
    )
    required_link_columns = {
        "link_id", "tx_lat_deg", "tx_lon_deg", "rx_lat_deg", "rx_lon_deg",
        "frequency_ghz", "fade_margin_db", "mean_terrain_elevation_m_asl",
        "allocated_incremental_outage_pct", "tx_source_record_id", "rx_source_record_id",
        "tafl_auth_number", "provenance_note",
    }
    missing = sorted(required_link_columns - set(links.columns))
    if missing:
        raise ValueError(f"Frozen link table is missing required columns: {missing}")
    if len(links) != args.expected_links:
        raise ValueError(f"Expected {args.expected_links} links; found {len(links)}")
    if links["link_id"].astype(str).duplicated().any():
        raise ValueError("Duplicate link_id values in frozen link table")
    if links["allocated_incremental_outage_pct"].notna().any():
        raise ValueError(
            "Outage allocation is already populated. This evidence stage must precede allocation."
        )
    for col in ["mean_terrain_elevation_m_asl", "fade_margin_db"]:
        vals = pd.to_numeric(links[col], errors="coerce")
        if vals.isna().any() or not np.isfinite(vals).all():
            raise ValueError(f"Frozen link column {col} contains missing or non-finite values")
    if pd.to_numeric(links["fade_margin_db"], errors="raise").le(0.0).any():
        raise ValueError("One or more frozen fade margins are non-positive")

    tafl = pd.read_csv(
        tafl_path,
        header=None,
        names=TAFL_COLUMNS,
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
        low_memory=False,
    )
    if tafl.shape[1] != 61:
        raise ValueError(f"Expected 61 TAFL columns; found {tafl.shape[1]}")
    for col in tafl.columns:
        tafl[col] = tafl[col].astype(str).str.strip()
        tafl.loc[tafl[col].isin(["", "-"]), col] = np.nan
    for col in NUMERIC_TAFL:
        tafl[col] = pd.to_numeric(tafl[col], errors="coerce")
    tafl["freq_rec_id"] = tafl["freq_rec_id"].fillna("").astype(str).str.strip()
    tafl["txrx"] = tafl["txrx"].fillna("").astype(str).str.upper().str.strip()

    wanted_ids = set(links["tx_source_record_id"].astype(str).str.strip()) | set(
        links["rx_source_record_id"].astype(str).str.strip()
    )
    selected = tafl[tafl["freq_rec_id"].isin(wanted_ids)].copy()
    counts = selected["freq_rec_id"].value_counts()
    missing_ids = sorted(wanted_ids - set(counts.index))
    duplicate_ids = sorted(counts[counts != 1].index.astype(str).tolist())
    if missing_ids:
        raise ValueError(f"TAFL source records missing for {len(missing_ids)} IDs: {missing_ids[:10]}")
    if duplicate_ids:
        raise ValueError(
            f"TAFL frequency record IDs are not unique for {len(duplicate_ids)} IDs: {duplicate_ids[:10]}"
        )
    selected = selected.set_index("freq_rec_id", drop=False)

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for _, link in links.sort_values("link_id").iterrows():
        link_id = clean_text(link["link_id"])
        tx_id = clean_text(link["tx_source_record_id"])
        rx_id = clean_text(link["rx_source_record_id"])
        tx = selected.loc[tx_id]
        rx = selected.loc[rx_id]

        link_freq_mhz = finite_float(link["frequency_ghz"]) * 1000.0
        tx_freq_mhz = finite_float(tx["freq_mhz"])
        rx_freq_mhz = finite_float(rx["freq_mhz"])
        auth = clean_text(link["tafl_auth_number"])

        checks = {
            "tx_role_ok": clean_text(tx["txrx"]).upper() == "TX",
            "rx_role_ok": clean_text(rx["txrx"]).upper() == "RX",
            "tx_frequency_ok": math.isfinite(tx_freq_mhz) and abs(tx_freq_mhz - link_freq_mhz) <= 0.001,
            "rx_frequency_ok": math.isfinite(rx_freq_mhz) and abs(rx_freq_mhz - link_freq_mhz) <= 0.001,
            "tx_auth_ok": clean_text(tx["auth_number"]) == auth,
            "rx_auth_ok": clean_text(rx["auth_number"]) == auth,
            "service_ok": finite_float(tx["service"]) == 2.0 and finite_float(rx["service"]) == 2.0,
            "subservice_ok": finite_float(tx["subservice"]) == 200.0 and finite_float(rx["subservice"]) == 200.0,
        }
        failed_checks = [name for name, passed in checks.items() if not passed]
        if failed_checks:
            errors.append(f"{link_id}: failed source checks {failed_checks}")

        tx_ad = clean_text(tx["analog_digital"]).upper()
        rx_ad = clean_text(rx["analog_digital"]).upper()
        tx_cap = finite_float(tx["digital_cap"])
        rx_cap = finite_float(rx["digital_cap"])
        tx_bw = finite_float(tx["occ_bw_khz"])
        rx_bw = finite_float(rx["occ_bw_khz"])
        capacity_consistent = bool(
            math.isfinite(tx_cap)
            and math.isfinite(rx_cap)
            and abs(tx_cap - rx_cap) <= max(1e-6, 1e-6 * max(abs(tx_cap), abs(rx_cap), 1.0))
        )
        bandwidth_consistent = bool(
            math.isfinite(tx_bw)
            and math.isfinite(rx_bw)
            and abs(tx_bw - rx_bw) <= max(1e-6, 1e-6 * max(abs(tx_bw), abs(rx_bw), 1.0))
        )
        fully_digital = tx_ad == "D" and rx_ad == "D"

        distance = haversine_km(
            finite_float(link["tx_lat_deg"]),
            finite_float(link["tx_lon_deg"]),
            finite_float(link["rx_lat_deg"]),
            finite_float(link["rx_lon_deg"]),
        )

        rows.append(
            {
                "link_id": link_id,
                "tafl_auth_number": auth,
                "frequency_ghz": finite_float(link["frequency_ghz"]),
                "distance_km": distance,
                "fade_margin_db": finite_float(link["fade_margin_db"]),
                "mean_terrain_elevation_m_asl": finite_float(
                    link["mean_terrain_elevation_m_asl"]
                ),
                "tx_source_record_id": tx_id,
                "rx_source_record_id": rx_id,
                "tx_analog_digital": tx_ad,
                "rx_analog_digital": rx_ad,
                "fully_digital_pair": fully_digital,
                "tx_digital_capacity_mbps": tx_cap,
                "rx_digital_capacity_mbps": rx_cap,
                "digital_capacity_consistent": capacity_consistent,
                "tx_occupied_bandwidth_khz": tx_bw,
                "rx_occupied_bandwidth_khz": rx_bw,
                "occupied_bandwidth_consistent": bandwidth_consistent,
                "tx_modulation": clean_text(tx["modulation"]),
                "rx_modulation": clean_text(rx["modulation"]),
                "tx_emission_designator": clean_text(tx["emission_desig"]),
                "rx_emission_designator": clean_text(rx["emission_desig"]),
                "tx_communication_type": clean_text(tx["comm_type"]),
                "rx_communication_type": clean_text(rx["comm_type"]),
                "tx_station_type": clean_text(tx["station_type"]),
                "rx_station_type": clean_text(rx["station_type"]),
                "tx_itu_class": clean_text(tx["itu_class"]),
                "rx_itu_class": clean_text(rx["itu_class"]),
                "tx_licensee_name": clean_text(tx["licensee_name"]),
                "rx_licensee_name": clean_text(rx["licensee_name"]),
                "source_checks_pass": not failed_checks,
                # Decision fields intentionally left blank.
                "sharing_class": "",
                "network_portion": "",
                "performance_basis": "",
                "performance_parameter": "",
                "ber_outage_mapping": "",
                "allocation_derivation": "",
                "allocated_incremental_outage_pct": np.nan,
                "decision_source": "",
                "review_note": "",
            }
        )

    if errors:
        raise ValueError("; ".join(errors[:20]))

    review = pd.DataFrame(rows).sort_values("link_id")
    out_dir.mkdir(parents=True, exist_ok=True)
    review_path = out_dir / "s1_allocation_review_unfinished.csv"
    summary_path = out_dir / "summary.json"
    summary_md_path = out_dir / "SUMMARY.md"
    audit_path = out_dir / "S1_ALLOCATION_EVIDENCE_AUDIT.json"
    review.to_csv(review_path, index=False)

    capacity_values = pd.concat(
        [review["tx_digital_capacity_mbps"], review["rx_digital_capacity_mbps"]],
        ignore_index=True,
    ).dropna()
    bandwidth_values = pd.concat(
        [review["tx_occupied_bandwidth_khz"], review["rx_occupied_bandwidth_khz"]],
        ignore_index=True,
    ).dropna()

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "link_count": int(len(review)),
        "fully_digital_pair_count": int(review["fully_digital_pair"].sum()),
        "non_digital_or_unknown_pair_count": int((~review["fully_digital_pair"]).sum()),
        "capacity_present_both_endpoints_count": int(
            (
                review["tx_digital_capacity_mbps"].notna()
                & review["rx_digital_capacity_mbps"].notna()
            ).sum()
        ),
        "capacity_consistent_pair_count": int(review["digital_capacity_consistent"].sum()),
        "bandwidth_consistent_pair_count": int(review["occupied_bandwidth_consistent"].sum()),
        "source_checks_pass_count": int(review["source_checks_pass"].sum()),
        "distance_km_min": float(review["distance_km"].min()),
        "distance_km_median": float(review["distance_km"].median()),
        "distance_km_max": float(review["distance_km"].max()),
        "digital_capacity_mbps_min": float(capacity_values.min()) if not capacity_values.empty else None,
        "digital_capacity_mbps_median": float(capacity_values.median()) if not capacity_values.empty else None,
        "digital_capacity_mbps_max": float(capacity_values.max()) if not capacity_values.empty else None,
        "occupied_bandwidth_khz_min": float(bandwidth_values.min()) if not bandwidth_values.empty else None,
        "occupied_bandwidth_khz_median": float(bandwidth_values.median()) if not bandwidth_values.empty else None,
        "occupied_bandwidth_khz_max": float(bandwidth_values.max()) if not bandwidth_values.empty else None,
        "analog_digital_pair_distribution": semicolon_counts(
            review["tx_analog_digital"].astype(str) + "/" + review["rx_analog_digital"].astype(str)
        ),
        "modulation_pair_distribution": semicolon_counts(
            review["tx_modulation"].astype(str) + "/" + review["rx_modulation"].astype(str)
        ),
        "allocation_selected": False,
        "next_decision_required": (
            "Choose and document a standards basis and network/sharing classification, or run "
            "explicitly labelled sensitivity scenarios. Do not infer a universal allocation from path length."
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    audit = {
        "created_utc": summary["created_utc"],
        "inputs": {
            "links": {"path": str(links_path), "sha256": links_hash},
            "tafl": {"path": str(tafl_path), "sha256": tafl_hash},
            "terrain_decision": {
                "path": str(terrain_decision_path),
                "sha256": sha256_file(terrain_decision_path),
            },
            "pairing_decision": {
                "path": str(pairing_decision_path),
                "sha256": sha256_file(pairing_decision_path),
            },
        },
        "outputs": {
            "review_csv": {"path": str(review_path), "sha256": sha256_file(review_path)},
            "summary_json": {"path": str(summary_path), "sha256": sha256_file(summary_path)},
        },
        "claim_boundary": (
            "This stage verifies and exposes TAFL equipment metadata. It does not determine whether "
            "a link belongs to access, short-haul, long-haul, or international network portions; does "
            "not decide co-primary versus other-source sharing; does not equate P.530 BER outage with "
            "SESR as a standards identity; and does not populate an outage allocation."
        ),
    }
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = f"""# S1 Allocation Evidence Summary

- Frozen directed links: **{summary['link_count']}**
- Fully digital TX/RX pairs: **{summary['fully_digital_pair_count']}**
- Pairs with capacity at both endpoints: **{summary['capacity_present_both_endpoints_count']}**
- Pairs with consistent endpoint capacity: **{summary['capacity_consistent_pair_count']}**
- Source-integrity checks passed: **{summary['source_checks_pass_count']}**
- Distance range: **{summary['distance_km_min']:.3f} to {summary['distance_km_max']:.3f} km**

## What is still undecided

No outage allocation has been selected. Before the final S1 input can be created, the project must document either:

1. an operator/regulator-supported per-link classification and derived allocation; or
2. explicitly labelled standards-anchored sensitivity scenarios that are **not** claimed as a final compliance allocation.

Path length alone must not be used to infer access, short-haul, long-haul, or international network function.

## Output to review

`{review_path}`

The decision columns at the right of that CSV are intentionally blank.
"""
    summary_md_path.write_text(md, encoding="utf-8")

    print("S1 ALLOCATION EVIDENCE BUILD: PASS")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Review table: {review_path}")
    print(f"Summary: {summary_path}")
    print(f"Audit: {audit_path}")
    print("No allocation was selected or written.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"S1 ALLOCATION EVIDENCE BUILD FAILED: {exc}", file=sys.stderr)
        raise
