"""Protected-pass record construction helpers.

The orbit is a geometry-only model input. Distinct passes generated from one
archived TLE are distinct geometry trajectories, not independent ephemeris
uncertainty samples.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SelectedPass:
    target_peak_date: str
    start_utc: str
    end_utc: str
    peak_utc: str
    maximum_elevation_deg: float
    duration_s: float


def parse_utc(value: str) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def complete_pass_catalog(
    track: pd.DataFrame,
    minimum_elevation_deg: float,
) -> pd.DataFrame:
    required = {
        "time_utc",
        "time_s",
        "azimuth_deg",
        "elevation_deg",
        "slant_range_km",
    }
    if not required.issubset(track.columns):
        raise ValueError("coarse track is missing required columns")
    if track[list(required)].isna().any().any():
        raise ValueError("coarse track contains missing values")

    visible = (
        track["elevation_deg"].to_numpy(float)
        >= float(minimum_elevation_deg)
    )
    rows: list[dict[str, object]] = []
    start: int | None = None
    for index, flag in enumerate(visible):
        if flag and start is None:
            start = index
        if start is not None and (
            not flag or index == len(visible) - 1
        ):
            stop = index - 1 if not flag else index
            segment = track.iloc[start : stop + 1]
            complete = start > 0 and stop < len(track) - 1
            peak_label = int(segment["elevation_deg"].idxmax())
            peak_utc = str(track.loc[peak_label, "time_utc"])
            rows.append(
                {
                    "start_index": start,
                    "end_index": stop,
                    "start_utc": str(segment.iloc[0]["time_utc"]),
                    "end_utc": str(segment.iloc[-1]["time_utc"]),
                    "peak_utc": peak_utc,
                    "peak_utc_date": parse_utc(peak_utc).date().isoformat(),
                    "duration_s": float(
                        segment.iloc[-1]["time_s"]
                        - segment.iloc[0]["time_s"]
                    ),
                    "max_elevation_deg": float(
                        segment["elevation_deg"].max()
                    ),
                    "complete_within_search_window": bool(complete),
                }
            )
            start = None
    return pd.DataFrame(rows)


def select_passes_by_peak_date(
    catalog: pd.DataFrame,
    target_dates: list[str],
) -> list[SelectedPass]:
    if catalog.empty:
        raise ValueError("pass catalog is empty")
    complete = catalog.loc[
        catalog["complete_within_search_window"] == True  # noqa: E712
    ].copy()
    selected: list[SelectedPass] = []
    for target in target_dates:
        candidates = complete.loc[
            complete["peak_utc_date"] == str(target)
        ].copy()
        if candidates.empty:
            raise RuntimeError(
                f"No complete visible pass has peak UTC date {target}"
            )
        candidates = candidates.sort_values(
            ["max_elevation_deg", "start_utc"],
            ascending=[False, True],
        )
        row = candidates.iloc[0]
        selected.append(
            SelectedPass(
                target_peak_date=str(target),
                start_utc=str(row["start_utc"]),
                end_utc=str(row["end_utc"]),
                peak_utc=str(row["peak_utc"]),
                maximum_elevation_deg=float(
                    row["max_elevation_deg"]
                ),
                duration_s=float(row["duration_s"]),
            )
        )
    return selected


def sa509_gain(
    off_axis_deg: np.ndarray,
    parameters: pd.Series,
    multiple_entry: bool,
) -> np.ndarray:
    phi = np.asarray(off_axis_deg, dtype=float)
    if np.any(~np.isfinite(phi)) or np.any(
        (phi < 0.0) | (phi > 180.0)
    ):
        raise ValueError("off-axis angles are invalid")
    g0 = float(parameters["g0_dbi"])
    phi0 = float(parameters["phi0_deg"])
    phi1 = float(parameters["phi1_deg"])
    phi2 = float(parameters["phi2_deg"])
    result = np.empty_like(phi)
    first = phi < phi1
    second = (phi >= phi1) & (phi < phi2)
    third = (phi >= phi2) & (phi < 48.0)
    fourth = (phi >= 48.0) & (phi < 80.0)
    fifth = (phi >= 80.0) & (phi < 120.0)
    sixth = phi >= 120.0
    result[first] = g0 - 3.0 * (phi[first] / phi0) ** 2
    result[second] = g0 - (20.0 if multiple_entry else 17.0)
    result[third] = (
        (29.0 if multiple_entry else 32.0)
        - 25.0 * np.log10(phi[third])
    )
    if multiple_entry:
        result[fourth] = -13.0
        result[fifth] = -8.0
        result[sixth] = -13.0
    else:
        result[fourth] = -10.0
        result[fifth] = -5.0
        result[sixth] = -10.0
    return result


def angular_separation_deg(
    azimuth_1_deg: np.ndarray,
    elevation_1_deg: np.ndarray,
    azimuth_2_deg: float,
    elevation_2_deg: float,
) -> np.ndarray:
    az1 = np.radians(np.asarray(azimuth_1_deg, dtype=float))
    el1 = np.radians(np.asarray(elevation_1_deg, dtype=float))
    az2 = math.radians(float(azimuth_2_deg))
    el2 = math.radians(float(elevation_2_deg))
    u1 = np.column_stack(
        (
            np.cos(el1) * np.sin(az1),
            np.cos(el1) * np.cos(az1),
            np.sin(el1),
        )
    )
    u2 = np.array(
        [
            math.cos(el2) * math.sin(az2),
            math.cos(el2) * math.cos(az2),
            math.sin(el2),
        ]
    )
    return np.degrees(np.arccos(np.clip(u1 @ u2, -1.0, 1.0)))


def protected_track(
    detailed_track: pd.DataFrame,
    minimum_elevation_deg: float,
) -> pd.DataFrame:
    mask = (
        detailed_track["elevation_deg"].to_numpy(float)
        >= float(minimum_elevation_deg)
    )
    indices = np.flatnonzero(mask)
    if len(indices) < 2:
        raise ValueError("protected window has fewer than two samples")
    if np.any(np.diff(indices) != 1):
        raise ValueError("protected window is not contiguous")
    return detailed_track.loc[mask].copy().reset_index(drop=True)


def site_gain_table(
    track: pd.DataFrame,
    station: pd.Series,
    sites: pd.DataFrame,
    multiple_parameters: pd.Series,
    single_parameters: pd.Series,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    station_altitude = float(station["altitude_m_asl"])
    for _, site in sites.sort_values("site_id").iterrows():
        horizontal = float(site["station_to_site_distance_m"])
        site_elevation = math.degrees(
            math.atan2(
                float(site["antenna_altitude_m_asl"])
                - station_altitude,
                horizontal,
            )
        )
        off_axis = angular_separation_deg(
            track["azimuth_deg"].to_numpy(float),
            track["elevation_deg"].to_numpy(float),
            float(site["station_to_site_bearing_deg"]),
            site_elevation,
        )
        rows.append(
            pd.DataFrame(
                {
                    "time_utc": track["time_utc"].astype(str),
                    "time_s": track["time_s"].to_numpy(float),
                    "site_id": str(site["site_id"]),
                    "site_direction_elevation_deg": site_elevation,
                    "off_axis_deg": off_axis,
                    "gain_multiple_entry_dbi": sa509_gain(
                        off_axis,
                        multiple_parameters,
                        True,
                    ),
                    "gain_single_entry_dbi": sa509_gain(
                        off_axis,
                        single_parameters,
                        False,
                    ),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def kappa_from_gain_table(
    gain_table: pd.DataFrame,
    static_accounting: pd.DataFrame,
    p452_time_percentage: float,
    polarization_label: str,
    bs_gain_case: str,
    gain_column: str,
) -> tuple[np.ndarray, list[str]]:
    subset = static_accounting.loc[
        np.isclose(
            static_accounting["p452_time_percentage"],
            float(p452_time_percentage),
        )
        & (
            static_accounting["polarization_label"].astype(str)
            == str(polarization_label)
        )
        & (
            static_accounting["bs_gain_case"].astype(str)
            == str(bs_gain_case)
        )
    ].copy()
    subset = subset.sort_values("sector_id").reset_index(drop=True)
    if len(subset) != 57 or subset["sector_id"].nunique() != 57:
        raise ValueError(
            "static accounting does not provide exactly 57 sectors"
        )

    pivot = gain_table.pivot(
        index="time_s",
        columns="site_id",
        values=gain_column,
    ).sort_index()
    values = np.empty((len(pivot), 57), dtype=np.float64)
    for sector_index, row in subset.iterrows():
        site_gain = pivot[str(row["site_id"])].to_numpy(float)
        values[:, sector_index] = np.power(
            10.0,
            (
                float(row["element_pattern_gain_dbi"])
                - float(row["basic_transmission_loss_db"])
                + site_gain
            )
            / 10.0,
        )
    if np.any(~np.isfinite(values)) or np.any(values <= 0.0):
        raise ValueError("derived kappa contains invalid values")
    return values, subset["sector_id"].astype(str).tolist()


def threshold_w(threshold_dbw: float) -> float:
    return 10.0 ** (float(threshold_dbw) / 10.0)
