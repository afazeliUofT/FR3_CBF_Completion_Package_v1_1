from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NAMES = [
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

NUMERIC = [
    "freq_mhz", "occ_bw_khz", "tx_erp_dbw", "tx_power_w", "total_losses_db",
    "rx_unfaded_dbw", "rx_thresh_ber1e3_dbw", "ant_gain_dbi", "hpbw_deg",
    "f2b_db", "height_agl_m", "azimuth_deg", "elev_angle_deg", "lat", "lon",
    "ground_elev_m", "struct_height_m", "radius_km", "service", "subservice",
]

# Official field-description codes that are already granted/authorized rather than
# preliminary, rejected, cancelled, or still under technical processing.
FULLY_AUTHORIZED_CODES = {"G", "1", "3", "11"}


def _clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _codes(values: pd.Series) -> list[str]:
    return sorted({_clean_text(v).upper() for v in values if _clean_text(v)})


def _valid_coordinate(lat: float, lon: float) -> bool:
    return bool(np.isfinite(lat) and np.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _angle_error_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _first_float(row: pd.Series, key: str) -> float:
    value = row.get(key, np.nan)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Second-stage, read-only audit of TAFL auth_number+frequency groups. "
            "It never pairs ambiguous groups and never overwrites final S1 inputs."
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", default="data/real/tafl_pair_review")
    parser.add_argument("--f-min-mhz", type=float, default=7725.0)
    parser.add_argument("--f-max-mhz", type=float, default=8275.0)
    parser.add_argument("--gta-lat-min", type=float, default=43.2)
    parser.add_argument("--gta-lat-max", type=float, default=44.4)
    parser.add_argument("--gta-lon-min", type=float, default=-80.3)
    parser.add_argument("--gta-lon-max", type=float, default=-78.3)
    args = parser.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(src)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(
        src,
        header=None,
        names=NAMES,
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
        low_memory=False,
    )
    if df.shape[1] != 61:
        raise ValueError(f"Expected 61 columns; found {df.shape[1]}")

    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    df = df.mask(df.eq("") | df.eq("-"))
    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["txrx"] = df["txrx"].astype(str).str.upper().str.strip()
    df["auth_status"] = df["auth_status"].astype(str).str.upper().str.strip()
    df["op_status"] = df["op_status"].astype(str).str.upper().str.strip()
    df["freq_key_mhz"] = df["freq_mhz"].round(3)

    band = df[df["freq_mhz"].between(args.f_min_mhz, args.f_max_mhz, inclusive="both")].copy()
    band = band[band["txrx"].isin(["TX", "RX"])].copy()
    band["gta_coordinate"] = (
        band["lat"].between(args.gta_lat_min, args.gta_lat_max, inclusive="both")
        & band["lon"].between(args.gta_lon_min, args.gta_lon_max, inclusive="both")
    )

    status_summary = (
        band.groupby(["auth_status", "op_status", "service", "subservice", "txrx"], dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values("rows", ascending=False)
    )
    status_summary.to_csv(out_dir / "status_service_summary.csv", index=False)

    exact_rows: list[dict[str, Any]] = []
    ambiguous_frames: list[pd.DataFrame] = []
    unpaired_frames: list[pd.DataFrame] = []

    keys = ["auth_number", "freq_key_mhz"]
    usable = band[band["auth_number"].notna() & band["freq_key_mhz"].notna()].copy()

    for (auth_number, freq_key), group in usable.groupby(keys, dropna=False, sort=True):
        txs = group[group["txrx"] == "TX"]
        rxs = group[group["txrx"] == "RX"]
        group_gta_rx = bool(rxs["gta_coordinate"].fillna(False).any())

        if len(txs) == 1 and len(rxs) == 1:
            tx = txs.iloc[0]
            rx = rxs.iloc[0]
            tx_lat, tx_lon = _first_float(tx, "lat"), _first_float(tx, "lon")
            rx_lat, rx_lon = _first_float(rx, "lat"), _first_float(rx, "lon")
            coords_valid = _valid_coordinate(tx_lat, tx_lon) and _valid_coordinate(rx_lat, rx_lon)

            distance_km = float("nan")
            tx_bearing = float("nan")
            rx_bearing = float("nan")
            tx_az_error = float("nan")
            rx_az_error = float("nan")
            if coords_valid:
                distance_km = _haversine_km(tx_lat, tx_lon, rx_lat, rx_lon)
                tx_bearing = _bearing_deg(tx_lat, tx_lon, rx_lat, rx_lon)
                rx_bearing = _bearing_deg(rx_lat, rx_lon, tx_lat, tx_lon)
                tx_az = _first_float(tx, "azimuth_deg")
                rx_az = _first_float(rx, "azimuth_deg")
                if np.isfinite(tx_az):
                    tx_az_error = _angle_error_deg(tx_az, tx_bearing)
                if np.isfinite(rx_az):
                    rx_az_error = _angle_error_deg(rx_az, rx_bearing)

            services = sorted({int(v) for v in group["service"].dropna().astype(float)})
            subservices = sorted({int(v) for v in group["subservice"].dropna().astype(float)})
            auth_codes = _codes(group["auth_status"])
            op_codes = _codes(group["op_status"])
            fully_authorized = bool(auth_codes) and set(auth_codes).issubset(FULLY_AUTHORIZED_CODES)
            point_to_point = services == [2] and subservices == [200]

            tx_ground = _first_float(tx, "ground_elev_m")
            tx_agl = _first_float(tx, "height_agl_m")
            rx_ground = _first_float(rx, "ground_elev_m")
            rx_agl = _first_float(rx, "height_agl_m")
            tx_alt_asl = tx_ground + tx_agl if np.isfinite(tx_ground) and np.isfinite(tx_agl) else float("nan")
            rx_alt_asl = rx_ground + rx_agl if np.isfinite(rx_ground) and np.isfinite(rx_agl) else float("nan")

            rx_unfaded = _first_float(rx, "rx_unfaded_dbw")
            rx_threshold = _first_float(rx, "rx_thresh_ber1e3_dbw")
            fade_inputs_present = bool(
                np.isfinite(rx_unfaded)
                and np.isfinite(rx_threshold)
                and rx_unfaded < 0.0
                and rx_threshold < 0.0
            )
            fade_margin = rx_unfaded - rx_threshold if fade_inputs_present else float("nan")

            tx_freq = _first_float(tx, "freq_mhz")
            rx_freq = _first_float(rx, "freq_mhz")
            same_frequency = bool(np.isfinite(tx_freq) and np.isfinite(rx_freq) and abs(tx_freq - rx_freq) <= 0.001)

            exact_rows.append(
                {
                    "pair_id_candidate": f"{_clean_text(auth_number)}__{float(freq_key):.3f}MHz",
                    "auth_number": _clean_text(auth_number),
                    "frequency_mhz": float(freq_key),
                    "gta_rx": group_gta_rx,
                    "service_codes": ";".join(map(str, services)),
                    "subservice_codes": ";".join(map(str, subservices)),
                    "point_to_point_service_2_subservice_200": point_to_point,
                    "auth_status_codes": ";".join(auth_codes),
                    "fully_authorized_status": fully_authorized,
                    "op_status_codes": ";".join(op_codes),
                    "same_frequency_within_1khz": same_frequency,
                    "coordinates_valid": coords_valid,
                    "distance_km": distance_km,
                    "tx_lat_deg": tx_lat,
                    "tx_lon_deg": tx_lon,
                    "rx_lat_deg": rx_lat,
                    "rx_lon_deg": rx_lon,
                    "tx_ground_elev_m": tx_ground,
                    "tx_height_agl_m": tx_agl,
                    "tx_antenna_alt_m_asl": tx_alt_asl,
                    "rx_ground_elev_m": rx_ground,
                    "rx_height_agl_m": rx_agl,
                    "rx_antenna_alt_m_asl": rx_alt_asl,
                    "tx_azimuth_deg": _first_float(tx, "azimuth_deg"),
                    "tx_geodesic_bearing_deg": tx_bearing,
                    "tx_azimuth_error_deg": tx_az_error,
                    "rx_azimuth_deg": _first_float(rx, "azimuth_deg"),
                    "rx_geodesic_bearing_deg": rx_bearing,
                    "rx_azimuth_error_deg": rx_az_error,
                    "tx_ref_id": _clean_text(tx.get("ref_id")),
                    "rx_ref_id": _clean_text(rx.get("ref_id")),
                    "ref_ids_equal": _clean_text(tx.get("ref_id")) == _clean_text(rx.get("ref_id")),
                    "tx_freq_rec_id": _clean_text(tx.get("freq_rec_id")),
                    "rx_freq_rec_id": _clean_text(rx.get("freq_rec_id")),
                    "tx_station_location": _clean_text(tx.get("station_loc")),
                    "rx_station_location": _clean_text(rx.get("station_loc")),
                    "tx_station_type": _clean_text(tx.get("station_type")),
                    "rx_station_type": _clean_text(rx.get("station_type")),
                    "tx_itu_class": _clean_text(tx.get("itu_class")),
                    "rx_itu_class": _clean_text(rx.get("itu_class")),
                    "tx_polarization": _clean_text(tx.get("polarization")),
                    "rx_polarization": _clean_text(rx.get("polarization")),
                    "rx_unfaded_dbw": rx_unfaded,
                    "rx_threshold_ber1e3_dbw": rx_threshold,
                    "fade_margin_inputs_present": fade_inputs_present,
                    "fade_margin_db_from_tafl": fade_margin,
                    "eligible_exact_gta_p2p_authorized": bool(
                        group_gta_rx and point_to_point and fully_authorized and same_frequency and coords_valid
                    ),
                }
            )
        elif len(txs) > 1 or len(rxs) > 1:
            frame = group.copy()
            frame.insert(0, "group_n_rx", len(rxs))
            frame.insert(0, "group_n_tx", len(txs))
            frame.insert(0, "group_has_gta_rx", group_gta_rx)
            frame.insert(0, "pair_group_frequency_mhz", float(freq_key))
            frame.insert(0, "pair_group_auth_number", _clean_text(auth_number))
            ambiguous_frames.append(frame)
        else:
            frame = group.copy()
            frame.insert(0, "group_n_rx", len(rxs))
            frame.insert(0, "group_n_tx", len(txs))
            frame.insert(0, "group_has_gta_rx", group_gta_rx)
            frame.insert(0, "pair_group_frequency_mhz", float(freq_key))
            frame.insert(0, "pair_group_auth_number", _clean_text(auth_number))
            unpaired_frames.append(frame)

    exact = pd.DataFrame(exact_rows).sort_values(
        ["gta_rx", "eligible_exact_gta_p2p_authorized", "auth_number", "frequency_mhz"],
        ascending=[False, False, True, True],
    )
    exact.to_csv(out_dir / "exact_auth_frequency_pairs.csv", index=False)

    gta_exact = exact[exact["gta_rx"]].copy()
    gta_exact.to_csv(out_dir / "gta_exact_auth_frequency_pairs.csv", index=False)

    gta_eligible = exact[exact["eligible_exact_gta_p2p_authorized"]].copy()
    gta_eligible.to_csv(out_dir / "gta_eligible_exact_pairs.csv", index=False)

    gta_exceptions = gta_exact[~gta_exact["eligible_exact_gta_p2p_authorized"]].copy()
    gta_exceptions.to_csv(out_dir / "gta_exact_pair_exceptions.csv", index=False)

    if ambiguous_frames:
        ambiguous = pd.concat(ambiguous_frames, ignore_index=True)
    else:
        ambiguous = pd.DataFrame()
    ambiguous.to_csv(out_dir / "ambiguous_auth_frequency_group_rows.csv", index=False)
    ambiguous_gta = ambiguous[ambiguous.get("group_has_gta_rx", pd.Series(dtype=bool)).fillna(False)] if not ambiguous.empty else ambiguous
    ambiguous_gta.to_csv(out_dir / "gta_ambiguous_auth_frequency_group_rows.csv", index=False)

    if unpaired_frames:
        unpaired = pd.concat(unpaired_frames, ignore_index=True)
    else:
        unpaired = pd.DataFrame()
    unpaired.to_csv(out_dir / "unpaired_auth_frequency_group_rows.csv", index=False)

    summary = {
        "source_file": str(src),
        "band_mhz": [args.f_min_mhz, args.f_max_mhz],
        "band_rows": int(len(band)),
        "band_tx_rows": int((band["txrx"] == "TX").sum()),
        "band_rx_rows": int((band["txrx"] == "RX").sum()),
        "auth_frequency_groups": int(usable.groupby(keys, dropna=False).ngroups),
        "exact_one_tx_one_rx_groups": int(len(exact)),
        "exact_groups_with_gta_rx": int(len(gta_exact)),
        "eligible_exact_gta_p2p_fully_authorized": int(len(gta_eligible)),
        "gta_exact_pair_exceptions": int(len(gta_exceptions)),
        "ambiguous_groups": int(ambiguous[["pair_group_auth_number", "pair_group_frequency_mhz"]].drop_duplicates().shape[0]) if not ambiguous.empty else 0,
        "ambiguous_groups_with_gta_rx": int(ambiguous_gta[["pair_group_auth_number", "pair_group_frequency_mhz"]].drop_duplicates().shape[0]) if not ambiguous_gta.empty else 0,
        "unpaired_groups": int(unpaired[["pair_group_auth_number", "pair_group_frequency_mhz"]].drop_duplicates().shape[0]) if not unpaired.empty else 0,
        "eligible_gta_pairs_with_tafl_fade_margin": int(gta_eligible["fade_margin_inputs_present"].sum()) if not gta_eligible.empty else 0,
        "eligible_gta_pairs_missing_tafl_fade_margin": int((~gta_eligible["fade_margin_inputs_present"]).sum()) if not gta_eligible.empty else 0,
        "fully_authorized_codes_used_for_classification": sorted(FULLY_AUTHORIZED_CODES),
        "final_pairing_rule_frozen": False,
        "note": "Read-only audit. No ambiguous group was paired and no final paired_fs_links.csv was created.",
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)

    print("TAFL AUTHORIZATION+FREQUENCY REVIEW")
    for key, value in summary.items():
        if key not in {"source_file", "note", "fully_authorized_codes_used_for_classification"}:
            print(f"{key}: {value}")
    print(f"Outputs: {out_dir.resolve()}")
    print("No final pairing rule was frozen. Review GTA exceptions and GTA ambiguous groups next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
