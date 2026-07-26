#!/usr/bin/env python3
"""Generate a coarse track, select a complete visible pass, and create a 1 s track."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import yaml


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def complete_passes(df: pd.DataFrame, minimum_elevation: float) -> pd.DataFrame:
    visible = df["elevation_deg"].to_numpy(float) >= minimum_elevation
    rows: list[dict] = []
    start = None
    for idx, flag in enumerate(visible):
        if flag and start is None:
            start = idx
        if start is not None and (not flag or idx == len(visible) - 1):
            end = idx - 1 if not flag else idx
            complete = start > 0 and end < len(visible) - 1
            segment = df.iloc[start : end + 1]
            peak_idx = int(segment["elevation_deg"].idxmax())
            rows.append(
                {
                    "start_index": start,
                    "end_index": end,
                    "start_utc": segment.iloc[0]["time_utc"],
                    "end_utc": segment.iloc[-1]["time_utc"],
                    "duration_s": float(segment.iloc[-1]["time_s"] - segment.iloc[0]["time_s"]),
                    "max_elevation_deg": float(segment["elevation_deg"].max()),
                    "peak_utc": df.loc[peak_idx, "time_utc"],
                    "complete_within_search_window": complete,
                }
            )
            start = None
    return pd.DataFrame(rows)


def run_track(root: Path, tle: Path, start: datetime, duration_s: int, step_s: float, lat: float, lon: float, alt: float, engine: str, output: Path) -> None:
    command = [
        sys.executable,
        str(root / "scripts/06_generate_tle_track.py"),
        "--tle",
        str(tle),
        "--start-utc",
        start.isoformat().replace("+00:00", "Z"),
        "--duration-s",
        str(duration_s),
        "--step-s",
        str(step_s),
        "--station-lat",
        str(lat),
        "--station-lon",
        str(lon),
        "--station-alt-m",
        str(alt),
        "--engine",
        engine,
        "--output",
        str(output.relative_to(root)),
    ]
    subprocess.run(command, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_reference_intake.yaml")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / args.config).read_text(encoding="utf-8"))
    track_cfg = cfg["track"]
    station_csv = root / "data/real/e3_reference_case/earth_station_staging.csv"
    tle = root / "data/external/tle/active_case.tle"
    tle_record = root / "data/external/tle/TLE_SOURCE_RECORD.json"
    if not station_csv.is_file() or not tle.is_file() or not tle_record.is_file():
        raise FileNotFoundError("Run station and TLE preparation before pass generation")
    station = pd.read_csv(station_csv).iloc[0]
    lat = float(station["latitude_deg"])
    lon = float(station["longitude_deg"])
    alt = float(station["altitude_m_asl"])
    start_value = track_cfg.get("start_utc")
    if start_value:
        start = parse_utc(str(start_value))
    else:
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    duration_s = int(float(track_cfg["coarse_search_days"]) * 86400)
    step_s = float(track_cfg["coarse_step_s"])
    minimum_elevation = float(track_cfg["minimum_elevation_deg"])
    engine = str(track_cfg["engine"])
    out_dir = root / "data/real/e3_reference_case"
    coarse = out_dir / "e3_track_coarse.csv"
    run_track(root, tle, start, duration_s, step_s, lat, lon, alt, engine, coarse)
    df = pd.read_csv(coarse)
    required = {"time_utc", "time_s", "azimuth_deg", "elevation_deg", "slant_range_km"}
    if not required.issubset(df.columns) or df[list(required)].isna().any().any():
        raise RuntimeError("Coarse track is missing required finite fields")
    catalog = complete_passes(df, minimum_elevation)
    complete = catalog[catalog["complete_within_search_window"] == True].copy()  # noqa: E712
    if complete.empty:
        raise RuntimeError("No complete pass above the minimum elevation; increase coarse_search_days")
    complete = complete.sort_values(["max_elevation_deg", "start_utc"], ascending=[False, True])
    selected = complete.iloc[0]
    catalog_path = out_dir / "e3_pass_catalog.csv"
    catalog.to_csv(catalog_path, index=False)
    margin = int(track_cfg["detailed_margin_s"])
    detailed_start = parse_utc(str(selected["start_utc"])) - timedelta(seconds=margin)
    detailed_end = parse_utc(str(selected["end_utc"])) + timedelta(seconds=margin)
    detailed_duration = int((detailed_end - detailed_start).total_seconds())
    detailed = out_dir / "e3_track_selected_pass_1s.csv"
    run_track(
        root,
        tle,
        detailed_start,
        detailed_duration,
        float(track_cfg["detailed_step_s"]),
        lat,
        lon,
        alt,
        engine,
        detailed,
    )
    detail_df = pd.read_csv(detailed)
    if detail_df.isna().any().any():
        raise RuntimeError("Detailed track contains missing values")
    detail_peak = float(detail_df["elevation_deg"].max())
    coarse_peak = float(selected["max_elevation_deg"])
    if abs(detail_peak - coarse_peak) > 1.0:
        raise RuntimeError("Detailed/coarse pass peak differs by more than 1 degree")
    selection = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "coarse_search_start_utc": start.isoformat(),
        "coarse_search_duration_s": duration_s,
        "coarse_step_s": step_s,
        "minimum_elevation_deg": minimum_elevation,
        "selected_pass": selected.to_dict(),
        "detailed_start_utc": detailed_start.isoformat(),
        "detailed_duration_s": detailed_duration,
        "detailed_step_s": float(track_cfg["detailed_step_s"]),
        "detailed_max_elevation_deg": detail_peak,
        "station_altitude_m_asl_nominal": alt,
        "engine": engine,
        "claim_boundary": (
            "Orbit geometry is model input. Selected pass points still require an independent spot check before paper use."
        ),
        "next_gate": "EARTH_STATION_PATTERN_AND_CELLULAR_LAYOUT_FREEZE",
    }
    (out_dir / "E3_PASS_SELECTION.json").write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(detail_df["time_s"], detail_df["elevation_deg"])
    ax.axhline(minimum_elevation, linestyle="--", label="minimum elevation")
    ax.set_xlabel("Seconds from detailed-track start")
    ax.set_ylabel("Elevation (degrees)")
    ax.set_title("Selected E3 geometry-reference pass")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "e3_selected_pass_elevation.png", dpi=180)
    plt.close(fig)
    print("E3 PASS GENERATION/SELECTION: PASS")
    print(f"Complete passes found: {len(complete)}")
    print(f"Selected start: {selected['start_utc']}")
    print(f"Selected end: {selected['end_utc']}")
    print(f"Selected max elevation: {detail_peak:.3f} deg")
    print(f"Detailed track: {detailed}")
    print("Next gate: earth-station pattern and cellular-layout freeze")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
