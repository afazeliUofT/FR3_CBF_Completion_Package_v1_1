from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from _bootstrap import ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Add mean terrain elevation from a user-supplied DEM GeoTIFF")
    parser.add_argument("--links", required=True)
    parser.add_argument("--dem", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=201)
    args = parser.parse_args()
    if args.samples < 5:
        raise ValueError("--samples must be at least 5")
    try:
        import rasterio
        from rasterio.warp import transform
    except ImportError as exc:
        raise SystemExit("Install requirements-full.txt to use rasterio") from exc

    df = pd.read_csv(args.links)
    means = []
    with rasterio.open(args.dem) as src:
        for _, row in df.iterrows():
            # Short terrestrial links: a dense great-circle approximation is unnecessary for DEM sampling;
            # linear geographic interpolation is used and documented in the output note.
            lats = np.linspace(float(row.tx_lat_deg), float(row.rx_lat_deg), args.samples)[1:-1]
            lons = np.linspace(float(row.tx_lon_deg), float(row.rx_lon_deg), args.samples)[1:-1]
            xs, ys = transform("EPSG:4326", src.crs, lons.tolist(), lats.tolist())
            vals = np.array([v[0] for v in src.sample(zip(xs, ys))], dtype=float)
            if src.nodata is not None:
                vals = vals[vals != src.nodata]
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                raise ValueError(f"No valid DEM samples for link {row.link_id}")
            means.append(float(vals.mean()))
    df["mean_terrain_elevation_m_asl"] = means
    df["provenance_note"] = df["provenance_note"].astype(str) + f"; DEM={Path(args.dem).name}, samples={args.samples}, endpoints excluded"
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Wrote terrain-completed file to {out}")
    print("Review profiles and DEM suitability before using as evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
