from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .geo import build_link_geometry
from .grids import P530GridProducts
from .io import environment_record, sha256_file
from .p530 import fade_exceedance_worst_month_percent, validity_warnings
from .units import interference_fade_margin_penalty_db

REQUIRED_COLUMNS = [
    "link_id",
    "tx_lat_deg",
    "tx_lon_deg",
    "rx_lat_deg",
    "rx_lon_deg",
    "tx_antenna_alt_m_asl",
    "rx_antenna_alt_m_asl",
    "mean_terrain_elevation_m_asl",
    "frequency_ghz",
    "fade_margin_db",
    "allocated_incremental_outage_pct",
    "provenance_note",
]


def _float_or_none(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)) or str(value).strip() == "":
        return None
    return float(value)


def validate_links_dataframe(df: pd.DataFrame, mode: str) -> list[str]:
    errors: list[str] = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {missing}")
        return errors
    if df.empty:
        errors.append("No links found")
        return errors
    if df["link_id"].astype(str).duplicated().any():
        errors.append("Duplicate link_id values")

    numeric_ranges = {
        "tx_lat_deg": (-90, 90),
        "rx_lat_deg": (-90, 90),
        "tx_lon_deg": (-180, 180),
        "rx_lon_deg": (-180, 180),
        "frequency_ghz": (0.1, 100),
        "fade_margin_db": (0, 100),
        "allocated_incremental_outage_pct": (0, 100),
    }
    for col, (lo, hi) in numeric_ranges.items():
        vals = pd.to_numeric(df[col], errors="coerce")
        if vals.isna().any():
            errors.append(f"Column {col} has missing/non-numeric values")
        elif ((vals < lo) | (vals > hi)).any():
            errors.append(f"Column {col} has values outside [{lo}, {hi}]")
    fade_margin_values = pd.to_numeric(df["fade_margin_db"], errors="coerce")
    if not fade_margin_values.isna().any() and (fade_margin_values <= 0).any():
        errors.append("fade_margin_db must be strictly positive for the S1 adequacy calculation")
    for col in ["tx_antenna_alt_m_asl", "rx_antenna_alt_m_asl", "mean_terrain_elevation_m_asl"]:
        vals = pd.to_numeric(df[col], errors="coerce")
        if vals.isna().any():
            errors.append(f"Column {col} has missing/non-numeric values")
    if mode == "real":
        if df["provenance_note"].fillna("").astype(str).str.strip().eq("").any():
            errors.append("Every real link requires a provenance_note")
        if df["link_id"].astype(str).str.contains("example|demo|synthetic", case=False, regex=True).any():
            errors.append("Real mode contains an example/demo/synthetic link ID")
    return errors


def evaluate_s1(
    links_csv: str | Path,
    candidate_i_over_n_db: list[float],
    mode: str,
    p530_products_dir: str | Path | None,
    global_allocation_pct: float | None,
    use_all_percentages_method: bool,
    require_real_grids: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    links_csv = Path(links_csv)
    df = pd.read_csv(links_csv)
    errors = validate_links_dataframe(df, mode)
    if errors:
        raise ValueError("; ".join(errors))

    grids: P530GridProducts | None = None
    if p530_products_dir and Path(p530_products_dir).exists():
        try:
            grids = P530GridProducts.from_directory(p530_products_dir)
        except (FileNotFoundError, ValueError):
            grids = None
    if mode == "real" and require_real_grids and grids is None:
        raise FileNotFoundError(
            "Real mode requires validated P.530 grids. Run scripts/02_download_p530_products.py."
        )

    details: list[dict[str, Any]] = []
    link_warnings: dict[str, list[str]] = {}
    for _, row in df.iterrows():
        link_id = str(row["link_id"])
        geom = build_link_geometry(
            float(row["tx_lat_deg"]),
            float(row["tx_lon_deg"]),
            float(row["rx_lat_deg"]),
            float(row["rx_lon_deg"]),
            float(row["tx_antenna_alt_m_asl"]),
            float(row["rx_antenna_alt_m_asl"]),
            float(row["mean_terrain_elevation_m_asl"]),
        )
        k_override = _float_or_none(row.get("k_override_percent"))
        dn_override = _float_or_none(row.get("dn75_override_n_units"))
        if k_override is not None and dn_override is not None:
            k_pct, dn75 = k_override, dn_override
            p530_source = "documented row overrides"
        elif grids is not None:
            k_pct, dn75 = grids.interpolate(geom.midpoint_lat_deg, geom.midpoint_lon_deg)
            p530_source = "official P.530 integral grids"
        else:
            raise ValueError(
                f"Link {link_id}: provide both K/dN75 overrides for demo or install official grids"
            )

        allocation = _float_or_none(row.get("allocated_incremental_outage_pct"))
        if allocation is None:
            allocation = global_allocation_pct
        if allocation is None:
            raise ValueError(
                f"Link {link_id}: allocated_incremental_outage_pct is missing and no reviewed global allocation is set"
            )

        lower_alt = min(float(row["tx_antenna_alt_m_asl"]), float(row["rx_antenna_alt_m_asl"]))
        baseline = fade_exceedance_worst_month_percent(
            fade_depth_db=float(row["fade_margin_db"]),
            k_percent=k_pct,
            distance_km=geom.distance_km,
            frequency_ghz=float(row["frequency_ghz"]),
            path_inclination_mrad=geom.path_inclination_mrad,
            lower_antenna_alt_m_asl=lower_alt,
            hc_m=geom.mean_terrain_clearance_m,
            dn75_n_units=dn75,
            use_all_percentages_method=use_all_percentages_method,
        )
        warnings = validity_warnings(
            distance_km=geom.distance_km,
            frequency_ghz=float(row["frequency_ghz"]),
            path_inclination_mrad=geom.path_inclination_mrad,
            lower_antenna_alt_m_asl=lower_alt,
            hc_m=geom.mean_terrain_clearance_m,
            dn75_n_units=dn75,
            p0_percent=baseline.p0_percent,
        )
        link_warnings[link_id] = warnings

        for candidate in candidate_i_over_n_db:
            penalty = interference_fade_margin_penalty_db(float(candidate))
            effective_margin_raw = float(row["fade_margin_db"]) - penalty
            if effective_margin_raw <= 0.0:
                # The interference penalty has exhausted the documented fade margin.
                # P.530's fading formula is defined for nonnegative fade depth; using A=0
                # would understate the engineering outage. Conservatively mark the link
                # unavailable for this always-on candidate.
                effective_margin = 0.0
                after_outage_percent = 100.0
                after_method = "fade margin exhausted by always-on interference candidate"
            else:
                effective_margin = effective_margin_raw
                after = fade_exceedance_worst_month_percent(
                    fade_depth_db=effective_margin,
                    k_percent=k_pct,
                    distance_km=geom.distance_km,
                    frequency_ghz=float(row["frequency_ghz"]),
                    path_inclination_mrad=geom.path_inclination_mrad,
                    lower_antenna_alt_m_asl=lower_alt,
                    hc_m=geom.mean_terrain_clearance_m,
                    dn75_n_units=dn75,
                    use_all_percentages_method=use_all_percentages_method,
                )
                after_outage_percent = after.exceedance_percent
                after_method = after.method
            incremental = max(0.0, after_outage_percent - baseline.exceedance_percent)
            details.append(
                {
                    "link_id": link_id,
                    "candidate_i_over_n_db": float(candidate),
                    "distance_km": geom.distance_km,
                    "midpoint_lat_deg": geom.midpoint_lat_deg,
                    "midpoint_lon_deg": geom.midpoint_lon_deg,
                    "path_inclination_mrad": geom.path_inclination_mrad,
                    "mean_terrain_clearance_m": geom.mean_terrain_clearance_m,
                    "k_percent": k_pct,
                    "dn75_n_units": dn75,
                    "p530_source": p530_source,
                    "fade_margin_db": float(row["fade_margin_db"]),
                    "interference_penalty_db": penalty,
                    "effective_fade_margin_db": effective_margin,
                    "effective_fade_margin_raw_db": effective_margin_raw,
                    "baseline_outage_pct_worst_month": baseline.exceedance_percent,
                    "after_outage_pct_worst_month": after_outage_percent,
                    "after_outage_method": after_method,
                    "incremental_outage_pct_worst_month": incremental,
                    "allocated_incremental_outage_pct": allocation,
                    "allocation_pass": bool(incremental <= allocation + 1e-12),
                    "warning_count": len(warnings),
                    "warnings": " | ".join(warnings),
                    "provenance_note": str(row["provenance_note"]),
                }
            )

    detail_df = pd.DataFrame(details)
    summary = (
        detail_df.groupby("candidate_i_over_n_db", as_index=False)
        .agg(
            link_count=("link_id", "nunique"),
            all_links_pass=("allocation_pass", "all"),
            worst_incremental_outage_pct=("incremental_outage_pct_worst_month", "max"),
            minimum_allocation_margin_pct=(
                "incremental_outage_pct_worst_month",
                lambda x: float(
                    np.min(
                        detail_df.loc[x.index, "allocated_incremental_outage_pct"].to_numpy()
                        - x.to_numpy()
                    )
                ),
            ),
            links_with_warnings=("warning_count", lambda x: int((x > 0).sum())),
        )
        .sort_values("candidate_i_over_n_db")
    )
    audit = {
        "mode": mode,
        "input_csv": str(links_csv),
        "input_sha256": sha256_file(links_csv),
        "candidate_i_over_n_db": [float(x) for x in candidate_i_over_n_db],
        "all_percentages_method": bool(use_all_percentages_method),
        "p530_products_loaded": grids is not None,
        "p530_source_files": grids.source_files if grids else None,
        "links_with_warnings": {k: v for k, v in link_warnings.items() if v},
        "environment": environment_record(),
        "summary": summary.to_dict(orient="records"),
    }
    return detail_df, summary, audit
