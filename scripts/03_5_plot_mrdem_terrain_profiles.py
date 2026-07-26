#!/usr/bin/env python3
"""Create a multipage PDF for human review of all terrain profiles."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    profiles_path = Path(args.profiles)
    summary_path = Path(args.summary)
    if not profiles_path.is_file():
        raise FileNotFoundError(profiles_path)
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)

    profiles = pd.read_csv(profiles_path)
    summary = pd.read_csv(summary_path).set_index("link_id")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(out) as pdf:
        for link_id, group in profiles.groupby("link_id", sort=True):
            if link_id not in summary.index:
                raise ValueError(f"{link_id}: missing from terrain summary")
            row = summary.loc[link_id]
            fig, ax = plt.subplots(figsize=(10, 5.5))
            x_km = group["distance_from_tx_m"] / 1000.0
            ax.plot(x_km, group["elevation_m_asl"], linewidth=1.1, label="MRDEM DTM profile")
            ax.scatter(
                [x_km.iloc[0], x_km.iloc[-1]],
                [group.iloc[0]["elevation_m_asl"], group.iloc[-1]["elevation_m_asl"]],
                s=18,
                label="DEM endpoint ground",
            )
            ax.axhline(
                row["mean_terrain_elevation_m_asl"],
                linestyle="--",
                linewidth=0.9,
                label=f"Selected mean ({row['selected_mean_convention']})",
            )
            if "mean_terrain_inclusive_m_asl" in row and "mean_terrain_interior_m_asl" in row:
                delta = float(row["inclusive_minus_interior_m"])
            else:
                delta = float("nan")
            flags = str(row.get("qc_flags", "")).strip() or "none"
            ax.set_title(
                f"{link_id} | {row['distance_km_wgs84']:.3f} km | "
                f"inclusive-interior={delta:.4f} m | flags={flags}"
            )
            ax.set_xlabel("Distance from TX (km)")
            ax.set_ylabel("Terrain elevation (m ASL)")
            ax.grid(True, linewidth=0.3)
            ax.legend(loc="best")
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)
    print(f"Wrote terrain-review PDF: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
