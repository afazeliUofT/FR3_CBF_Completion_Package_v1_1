#!/usr/bin/env python3
"""Add P.530-19 mean-path terrain using a reviewed MRDEM DTM subset.

The profile is sampled at approximately equal distance along the WGS84 geodesic.
ITU-R P.530-19 defines h_t as the mean terrain elevation along the path,
excluding trees, but does not prescribe a discrete endpoint convention. This
script therefore computes both inclusive and interior-sample means, records
their difference, and uses an explicit command-line convention (inclusive by
default) for the value written to the S1 link table.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def append_note(existing: object, addition: str) -> str:
    text = "" if pd.isna(existing) else str(existing).strip()
    return f"{text}; {addition}" if text else addition


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--links", required=True)
    parser.add_argument("--dem", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--out-dir", default="data/real/terrain_review")
    parser.add_argument("--spacing-m", type=float, default=30.0)
    parser.add_argument("--expected-links", type=int, default=70)
    parser.add_argument("--dem-product", default="NRCan MRDEM DTM")
    parser.add_argument("--dem-vertical-datum", default="CGVD2013")
    parser.add_argument(
        "--mean-convention",
        choices=("inclusive", "interior"),
        default="inclusive",
        help=(
            "Discrete line-mean convention. P.530-19 does not explicitly state "
            "whether endpoint samples are included. Both estimates are retained."
        ),
    )
    args = parser.parse_args()

    if args.spacing_m <= 0:
        raise ValueError("--spacing-m must be positive")
    if args.expected_links <= 0:
        raise ValueError("--expected-links must be positive")

    links_path = Path(args.links).expanduser().resolve()
    dem_path = Path(args.dem).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    if not links_path.is_file():
        raise FileNotFoundError(links_path)
    if not dem_path.is_file():
        raise FileNotFoundError(dem_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import rasterio
        from pyproj import Geod
        from rasterio.warp import transform
    except ImportError as exc:
        raise SystemExit(
            "Install the terrain requirements: "
            "python3 -m pip install -r requirements-terrain.txt"
        ) from exc

    df = pd.read_csv(links_path)
    required = {
        "link_id",
        "tx_lat_deg",
        "tx_lon_deg",
        "rx_lat_deg",
        "rx_lon_deg",
        "tx_antenna_alt_m_asl",
        "rx_antenna_alt_m_asl",
        "mean_terrain_elevation_m_asl",
        "provenance_note",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Link CSV is missing columns: {missing}")
    if len(df) != args.expected_links:
        raise ValueError(f"Expected {args.expected_links} links; found {len(df)}")
    if df["link_id"].astype(str).duplicated().any():
        raise ValueError("Duplicate link_id values")

    numeric_columns = [
        "tx_lat_deg",
        "tx_lon_deg",
        "rx_lat_deg",
        "rx_lon_deg",
        "tx_antenna_alt_m_asl",
        "rx_antenna_alt_m_asl",
    ]
    numeric = df[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("Link CSV contains missing/non-finite required numeric values")

    geod = Geod(ellps="WGS84")
    profile_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    dem_hash = sha256_file(dem_path)

    with rasterio.open(dem_path) as src:
        if src.crs is None:
            raise ValueError("DEM has no CRS")
        if src.count < 1:
            raise ValueError("DEM has no raster band")
        nodata = src.nodata

        for _, row in df.iterrows():
            link_id = str(row["link_id"])
            lon1, lat1 = float(row["tx_lon_deg"]), float(row["tx_lat_deg"])
            lon2, lat2 = float(row["rx_lon_deg"]), float(row["rx_lat_deg"])
            _, _, distance_m = geod.inv(lon1, lat1, lon2, lat2)
            if not math.isfinite(distance_m) or distance_m <= 0:
                raise ValueError(f"{link_id}: invalid geodesic distance {distance_m}")

            n_segments = max(2, int(math.ceil(distance_m / args.spacing_m)))
            n_interior = n_segments - 1
            interior = geod.npts(lon1, lat1, lon2, lat2, n_interior)
            lons = [lon1] + [p[0] for p in interior] + [lon2]
            lats = [lat1] + [p[1] for p in interior] + [lat2]
            xs, ys = transform("EPSG:4326", src.crs, lons, lats)
            raw = np.array([sample[0] for sample in src.sample(zip(xs, ys))], dtype=float)

            invalid = ~np.isfinite(raw)
            if nodata is not None and math.isfinite(float(nodata)):
                invalid |= np.isclose(raw, float(nodata), rtol=0.0, atol=1e-6)
            if invalid.any():
                bad = np.flatnonzero(invalid)[:10].tolist()
                raise ValueError(f"{link_id}: DEM has invalid/nodata samples at indices {bad}")
            if raw.size < 3:
                raise ValueError(f"{link_id}: fewer than one interior terrain sample")

            interior_elev = raw[1:-1]
            mean_inclusive = float(np.mean(raw))
            mean_interior = float(np.mean(interior_elev))
            selected_mean = mean_inclusive if args.mean_convention == "inclusive" else mean_interior
            min_elev = float(np.min(raw))
            max_elev = float(np.max(raw))
            std_elev = float(np.std(raw, ddof=0))
            tx_ground = float(raw[0])
            rx_ground = float(raw[-1])
            tx_implied_agl = float(row["tx_antenna_alt_m_asl"]) - tx_ground
            rx_implied_agl = float(row["rx_antenna_alt_m_asl"]) - rx_ground
            actual_spacing = distance_m / n_segments

            flags: list[str] = []
            if tx_implied_agl < 0:
                flags.append("tx_antenna_below_dem_ground")
            if rx_implied_agl < 0:
                flags.append("rx_antenna_below_dem_ground")
            if tx_implied_agl > 600:
                flags.append("tx_implied_agl_gt_600m")
            if rx_implied_agl > 600:
                flags.append("rx_implied_agl_gt_600m")
            if abs(mean_inclusive - mean_interior) > 0.5:
                flags.append("inclusive_interior_mean_difference_gt_0p5m")

            summaries.append(
                {
                    "link_id": link_id,
                    "distance_km_wgs84": distance_m / 1000.0,
                    "segment_count": n_segments,
                    "total_sample_count": len(raw),
                    "interior_sample_count": n_interior,
                    "actual_spacing_m": actual_spacing,
                    "selected_mean_convention": args.mean_convention,
                    "mean_terrain_elevation_m_asl": selected_mean,
                    "mean_terrain_inclusive_m_asl": mean_inclusive,
                    "mean_terrain_interior_m_asl": mean_interior,
                    "inclusive_minus_interior_m": mean_inclusive - mean_interior,
                    "min_profile_terrain_m_asl": min_elev,
                    "max_profile_terrain_m_asl": max_elev,
                    "std_profile_terrain_m": std_elev,
                    "tx_dem_ground_m_asl": tx_ground,
                    "rx_dem_ground_m_asl": rx_ground,
                    "tx_antenna_alt_m_asl": float(row["tx_antenna_alt_m_asl"]),
                    "rx_antenna_alt_m_asl": float(row["rx_antenna_alt_m_asl"]),
                    "tx_implied_antenna_height_agl_m": tx_implied_agl,
                    "rx_implied_antenna_height_agl_m": rx_implied_agl,
                    "qc_flag_count": len(flags),
                    "qc_flags": " | ".join(flags),
                }
            )

            for idx, (lon, lat, elevation) in enumerate(zip(lons, lats, raw)):
                profile_rows.append(
                    {
                        "link_id": link_id,
                        "sample_index": idx,
                        "is_endpoint": idx in (0, len(raw) - 1),
                        "fraction_from_tx": idx / n_segments,
                        "distance_from_tx_m": idx * actual_spacing,
                        "longitude_deg": lon,
                        "latitude_deg": lat,
                        "elevation_m_asl": float(elevation),
                    }
                )

    summary_df = pd.DataFrame(summaries).sort_values("link_id")
    profile_df = pd.DataFrame(profile_rows).sort_values(["link_id", "sample_index"])
    mean_map = summary_df.set_index("link_id")["mean_terrain_elevation_m_asl"]
    df["mean_terrain_elevation_m_asl"] = df["link_id"].astype(str).map(mean_map)
    if df["mean_terrain_elevation_m_asl"].isna().any():
        raise RuntimeError("Failed to map a terrain mean to every link")

    provenance = (
        f"terrain={args.dem_product}; vertical_datum={args.dem_vertical_datum}; "
        f"DEM_SHA256={dem_hash}; WGS84_geodesic_spacing_target={args.spacing_m:g}m; "
        f"discrete_mean_convention={args.mean_convention}; both inclusive and interior means retained; "
        "P.530-19 defines mean terrain along the path excluding trees; "
        "TAFL AMSL datum is not asserted identical to the DEM datum and remains covered by sensitivity analysis"
    )
    df["provenance_note"] = [append_note(v, provenance) for v in df["provenance_note"]]
    df.to_csv(output_path, index=False)

    summary_path = out_dir / "terrain_summary.csv"
    profile_path = out_dir / "terrain_profile_samples.csv.gz"
    summary_df.to_csv(summary_path, index=False)
    profile_df.to_csv(profile_path, index=False, compression="gzip")

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "links_input": str(links_path),
        "links_input_sha256": sha256_file(links_path),
        "dem": str(dem_path),
        "dem_sha256": dem_hash,
        "dem_product": args.dem_product,
        "dem_vertical_datum": args.dem_vertical_datum,
        "tafl_vertical_datum_statement": (
            "TAFL supplies elevation above mean sea level; exact geodetic realization "
            "is not asserted identical to CGVD2013 in this workflow"
        ),
        "p530_definition": "mean terrain elevation along the path, excluding trees",
        "discrete_mean_convention": args.mean_convention,
        "both_mean_conventions_retained": True,
        "target_spacing_m": args.spacing_m,
        "link_count": int(len(df)),
        "profile_sample_count": int(len(profile_df)),
        "links_with_qc_flags": int((summary_df["qc_flag_count"] > 0).sum()),
        "max_abs_inclusive_interior_difference_m": float(
            summary_df["inclusive_minus_interior_m"].abs().max()
        ),
        "terrain_mean_min_m_asl": float(summary_df["mean_terrain_elevation_m_asl"].min()),
        "terrain_mean_median_m_asl": float(summary_df["mean_terrain_elevation_m_asl"].median()),
        "terrain_mean_max_m_asl": float(summary_df["mean_terrain_elevation_m_asl"].max()),
        "output_links": str(output_path),
        "output_links_sha256": sha256_file(output_path),
        "summary_csv": str(summary_path),
        "summary_csv_sha256": sha256_file(summary_path),
        "profiles_csv_gz": str(profile_path),
        "profiles_csv_gz_sha256": sha256_file(profile_path),
    }
    audit_path = out_dir / "TERRAIN_AUDIT.json"
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    flagged = summary_df.loc[summary_df["qc_flag_count"] > 0]
    print("TERRAIN PROFILE BUILD: PASS")
    print(f"Links: {len(df)}")
    print(f"Total retained profile samples: {len(profile_df)}")
    print(f"Selected mean convention: {args.mean_convention}")
    print(
        "Mean terrain range (min/median/max): "
        f"{audit['terrain_mean_min_m_asl']:.3f} / "
        f"{audit['terrain_mean_median_m_asl']:.3f} / "
        f"{audit['terrain_mean_max_m_asl']:.3f} m ASL"
    )
    print(
        "Maximum |inclusive - interior| mean difference: "
        f"{audit['max_abs_inclusive_interior_difference_m']:.6f} m"
    )
    print(f"Links with QC flags: {len(flagged)}")
    print(f"Wrote: {output_path}")
    print(f"Review: {summary_path}")
    print(f"Profiles: {profile_path}")
    print("Human review is still required before the terrain field is frozen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
