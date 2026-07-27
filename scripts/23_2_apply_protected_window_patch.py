#!/usr/bin/env python3
"""Patch the historical E3 pattern/layout script so future reruns use the protected window."""
from __future__ import annotations

import argparse
import ast
import hashlib
from datetime import datetime, timezone
from pathlib import Path


OLD = """    # Dynamic off-axis summary per site/sector for the selected pass
    summaries: list[dict] = []
    for site in sites_pre.to_dict(orient="records"):
        horizontal = float(site["station_to_site_distance_m"])
        elevation_to_site = math.degrees(math.atan2(float(site["antenna_altitude_m_asl"]) - station_alt, horizontal))
        off_axis = angular_separation_deg(track["azimuth_deg"].to_numpy(float), track["elevation_deg"].to_numpy(float), float(site["station_to_site_bearing_deg"]), elevation_to_site)
        nominal_gain = sa509_gain(off_axis, dict(nominal_params), multiple=True)
        for sector_index in range(1, int(layout_cfg["sectors_per_site"]) + 1):
            summaries.append({
                "site_id": site["site_id"],
                "sector_id": f"{site['site_id']}_SEC_{sector_index}",
                "station_to_site_bearing_deg": site["station_to_site_bearing_deg"],
                "station_to_site_distance_m": horizontal,
                "station_to_site_elevation_deg": elevation_to_site,
                "minimum_off_axis_deg_during_selected_track": float(np.min(off_axis)),
                "median_off_axis_deg_during_selected_track": float(np.median(off_axis)),
                "maximum_reference_gain_dbi_during_selected_track": float(np.max(nominal_gain)),
            })
    pd.DataFrame(summaries).to_csv(review_dir / "selected_pass_off_axis_summary.csv", index=False)
"""

NEW = """    # Dynamic off-axis summary restricted to the protected tracking window.
    minimum_elevation_deg = float(station["minimum_elevation_deg"])
    protected_mask = track["elevation_deg"].to_numpy(float) >= minimum_elevation_deg
    protected_indices = np.flatnonzero(protected_mask)
    if protected_indices.size < 2:
        raise ValueError("Protected tracking window has fewer than two samples")
    if np.any(np.diff(protected_indices) != 1):
        raise ValueError("Protected tracking window is not one contiguous segment")
    protected_track = track.loc[protected_mask].copy().reset_index(drop=True)
    summaries: list[dict] = []
    for site in sites_pre.to_dict(orient="records"):
        horizontal = float(site["station_to_site_distance_m"])
        elevation_to_site = math.degrees(math.atan2(float(site["antenna_altitude_m_asl"]) - station_alt, horizontal))
        off_axis = angular_separation_deg(
            protected_track["azimuth_deg"].to_numpy(float),
            protected_track["elevation_deg"].to_numpy(float),
            float(site["station_to_site_bearing_deg"]),
            elevation_to_site,
        )
        nominal_gain = sa509_gain(off_axis, dict(nominal_params), multiple=True)
        min_index = int(np.argmin(off_axis))
        max_gain_index = int(np.argmax(nominal_gain))
        for sector_index in range(1, int(layout_cfg["sectors_per_site"]) + 1):
            summaries.append({
                "site_id": site["site_id"],
                "sector_id": f"{site['site_id']}_SEC_{sector_index}",
                "station_to_site_bearing_deg": site["station_to_site_bearing_deg"],
                "station_to_site_distance_m": horizontal,
                "station_to_site_elevation_deg": elevation_to_site,
                "protected_minimum_elevation_deg": minimum_elevation_deg,
                "protected_window_sample_count": int(len(protected_track)),
                "protected_window_start_utc": str(protected_track.iloc[0]["time_utc"]),
                "protected_window_end_utc": str(protected_track.iloc[-1]["time_utc"]),
                "minimum_off_axis_deg_during_protected_window": float(np.min(off_axis)),
                "minimum_off_axis_time_utc": str(protected_track.iloc[min_index]["time_utc"]),
                "median_off_axis_deg_during_protected_window": float(np.median(off_axis)),
                "maximum_reference_gain_dbi_during_protected_window": float(np.max(nominal_gain)),
                "maximum_reference_gain_time_utc": str(protected_track.iloc[max_gain_index]["time_utc"]),
                "selection_window": "earth_station_elevation_ge_minimum_elevation",
                # Backward-compatible aliases now explicitly represent the protected window.
                "minimum_off_axis_deg_during_selected_track": float(np.min(off_axis)),
                "median_off_axis_deg_during_selected_track": float(np.median(off_axis)),
                "maximum_reference_gain_dbi_during_selected_track": float(np.max(nominal_gain)),
            })
    summary_frame = pd.DataFrame(summaries)
    summary_frame.to_csv(review_dir / "selected_pass_off_axis_summary.csv", index=False)
    summary_frame.to_csv(review_dir / "selected_pass_off_axis_summary_protected.csv", index=False)
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="scripts/23_2_prepare_e3_pattern_layout.py")
    parser.add_argument("--root")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    target = root / args.target
    if not target.is_file():
        raise FileNotFoundError(target)

    text = target.read_text(encoding="utf-8")
    if NEW in text:
        print("E3 PATTERN/LAYOUT PROTECTED-WINDOW PATCH: ALREADY APPLIED")
        print("SHA-256:", digest(target))
        return 0
    if OLD not in text:
        raise SystemExit(
            "PATCH REFUSED: expected historical off-axis block was not found. "
            "Do not patch an unknown source version."
        )

    backup_dir = root / "backups" / (
        "e3_protected_window_source_patch_"
        + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup = backup_dir / target.name
    backup.write_text(text, encoding="utf-8")

    patched = text.replace(OLD, NEW, 1)
    ast.parse(patched, filename=str(target))
    target.write_text(patched, encoding="utf-8")

    print("E3 PATTERN/LAYOUT PROTECTED-WINDOW PATCH: PASS")
    print("Backup:", backup)
    print("Patched:", target)
    print("SHA-256:", digest(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
