from __future__ import annotations

import argparse

import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.geo import haversine_distance_km
from fr3_cbf.s1 import validate_links_dataframe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--mode", choices=["demo", "real"], default="real")
    args = parser.parse_args()
    df = pd.read_csv(args.csv)
    errors = validate_links_dataframe(df, args.mode)
    for _, row in df.iterrows():
        try:
            d = haversine_distance_km(row.tx_lat_deg, row.tx_lon_deg, row.rx_lat_deg, row.rx_lon_deg)
            if d < 0.05:
                errors.append(f"{row.link_id}: endpoint separation is only {d:.3f} km")
        except Exception as exc:
            errors.append(f"{row.get('link_id', '?')}: geometry error: {exc}")
    if errors:
        for error in errors:
            print("ERROR:", error)
        print("PAIRED-LINK VALIDATION: FAIL")
        return 1
    print(f"PAIRED-LINK VALIDATION: PASS ({len(df)} links, mode={args.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
