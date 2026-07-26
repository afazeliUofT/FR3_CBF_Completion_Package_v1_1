from __future__ import annotations

import argparse
from pathlib import Path

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
    "freq_mhz", "lat", "lon", "ground_elev_m", "height_agl_m",
    "rx_unfaded_dbw", "rx_thresh_ber1e3_dbw",
]

CANDIDATES = [
    ("freq_rec_id", ["freq_rec_id"]),
    ("ref_id", ["ref_id"]),
    ("auth_number", ["auth_number"]),
    ("licensee_ref", ["licensee_ref"]),
    ("call_sign", ["call_sign"]),
    ("auth_number+freq_mhz", ["auth_number", "freq_key"]),
    ("ref_id+freq_mhz", ["ref_id", "freq_key"]),
    ("auth_number+ref_id+freq_mhz", ["auth_number", "ref_id", "freq_key"]),
    ("licensee_ref+freq_mhz", ["licensee_ref", "freq_key"]),
    ("call_sign+freq_mhz", ["call_sign", "freq_key"]),
]


def nonblank(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit candidate authoritative TAFL pair keys; never auto-pairs by geometry."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--output", default="data/real/tafl_pair_key_diagnostic.csv"
    )
    args = parser.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(src)

    df = pd.read_csv(
        src,
        header=None,
        names=NAMES,
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    if df.shape[1] != 61:
        raise ValueError(f"Expected 61 columns; found {df.shape[1]}")

    df = df.apply(lambda col: col.str.strip())
    df = df.replace({"": np.nan, "-": np.nan})
    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["txrx"] = df["txrx"].astype(str).str.upper().str.strip()
    df["freq_key"] = df["freq_mhz"].round(3)

    band = df[df["freq_mhz"].between(7725.0, 8275.0, inclusive="both")].copy()
    print(f"Source rows: {len(df):,}")
    print(f"Rows in 7725-8275 MHz: {len(band):,}")
    print("TX/RX counts:", band["txrx"].value_counts(dropna=False).to_dict())

    reports: list[dict[str, object]] = []
    for label, keys in CANDIDATES:
        usable = band.copy()
        for key in keys:
            usable = usable[nonblank(usable[key])]

        total_groups = 0
        exact_groups = 0
        same_freq_groups = 0
        gta_rx_groups = 0
        ambiguous_groups = 0
        unpaired_groups = 0

        for _, group in usable.groupby(keys, dropna=False, sort=False):
            total_groups += 1
            ntx = int((group["txrx"] == "TX").sum())
            nrx = int((group["txrx"] == "RX").sum())
            if ntx == 1 and nrx == 1:
                exact_groups += 1
                tx = group.loc[group["txrx"] == "TX"].iloc[0]
                rx = group.loc[group["txrx"] == "RX"].iloc[0]
                if abs(float(tx["freq_mhz"]) - float(rx["freq_mhz"])) <= 0.001:
                    same_freq_groups += 1
                    if (
                        43.2 <= float(rx["lat"]) <= 44.4
                        and -80.3 <= float(rx["lon"]) <= -78.3
                    ):
                        gta_rx_groups += 1
            elif ntx > 1 or nrx > 1:
                ambiguous_groups += 1
            else:
                unpaired_groups += 1

        reports.append(
            {
                "candidate": label,
                "rows_with_nonblank_key": len(usable),
                "total_groups": total_groups,
                "exactly_one_tx_one_rx": exact_groups,
                "exact_pair_same_frequency": same_freq_groups,
                "exact_pair_with_gta_rx": gta_rx_groups,
                "ambiguous_groups": ambiguous_groups,
                "unpaired_groups": unpaired_groups,
            }
        )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    report = pd.DataFrame(reports).sort_values(
        ["exact_pair_with_gta_rx", "ambiguous_groups", "unpaired_groups"],
        ascending=[False, True, True],
    )
    report.to_csv(out, index=False)
    print("\nPAIR-KEY DIAGNOSTIC")
    print(report.to_string(index=False))
    print(f"\nWrote: {out}")
    print("No pair key was selected automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
