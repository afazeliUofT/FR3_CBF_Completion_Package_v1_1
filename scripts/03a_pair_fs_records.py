from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.io import load_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Strictly pair FS endpoints using an explicit pair key")
    parser.add_argument("--input", required=True)
    parser.add_argument("--mapping", default="config/tafl_column_mapping.yaml")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    mapping = load_yaml(ROOT / args.mapping)
    cols = mapping["input_columns"]
    roles = mapping["role_values"]
    df = pd.read_csv(args.input)
    required = list(cols.values())
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Input is missing mapped columns: {missing}")

    rows = []
    errors = []
    for pair_id, group in df.groupby(cols["pair_key"], dropna=False):
        tx = group[group[cols["endpoint_role"]].astype(str) == str(roles["tx"])]
        rx = group[group[cols["endpoint_role"]].astype(str) == str(roles["rx"])]
        if len(tx) != 1 or len(rx) != 1:
            errors.append(f"{pair_id}: expected exactly one TX and one RX, got TX={len(tx)}, RX={len(rx)}")
            continue
        t = tx.iloc[0]
        r = rx.iloc[0]
        ft, fr = float(t[cols["frequency_ghz"]]), float(r[cols["frequency_ghz"]])
        if abs(ft - fr) > 0.001:
            errors.append(f"{pair_id}: endpoint frequencies differ ({ft}, {fr})")
            continue
        rows.append(
            {
                "link_id": str(pair_id),
                "tx_lat_deg": t[cols["latitude_deg"]],
                "tx_lon_deg": t[cols["longitude_deg"]],
                "rx_lat_deg": r[cols["latitude_deg"]],
                "rx_lon_deg": r[cols["longitude_deg"]],
                "tx_antenna_alt_m_asl": t[cols["antenna_altitude_m_asl"]],
                "rx_antenna_alt_m_asl": r[cols["antenna_altitude_m_asl"]],
                "mean_terrain_elevation_m_asl": None,
                "frequency_ghz": (ft + fr) / 2.0,
                "fade_margin_db": None,
                "allocated_incremental_outage_pct": None,
                "k_override_percent": None,
                "dn75_override_n_units": None,
                "wanted_received_level_dbm": None,
                "receiver_threshold_dbm": None,
                "other_reserved_margin_db": None,
                "tx_source_record_id": t[cols["source_record_id"]],
                "rx_source_record_id": r[cols["source_record_id"]],
                "provenance_note": f"Strict pair-key join from {Path(args.input).name}; review required",
            }
        )

    if errors:
        print("PAIRING ERRORS:")
        for error in errors[:50]:
            print("-", error)
        raise SystemExit(2)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote {len(rows)} paired links to {out}")
    print("Incomplete terrain, fade-margin, and outage-allocation fields must be reviewed next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
