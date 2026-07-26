from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from _bootstrap import ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute fade margin only from explicitly supplied link-budget fields")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    df = pd.read_csv(args.input)
    needed = ["wanted_received_level_dbm", "receiver_threshold_dbm", "other_reserved_margin_db"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    for i, row in df.iterrows():
        if pd.notna(row.get("fade_margin_db")) and not args.force:
            continue
        if any(pd.isna(row[c]) for c in needed):
            raise ValueError(f"Link {row.link_id}: link-budget fields are incomplete")
        margin = float(row.wanted_received_level_dbm) - float(row.receiver_threshold_dbm) - float(row.other_reserved_margin_db)
        if margin < 0:
            raise ValueError(f"Link {row.link_id}: computed negative fade margin {margin:.3f} dB")
        df.at[i, "fade_margin_db"] = margin
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
