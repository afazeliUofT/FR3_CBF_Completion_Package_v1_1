#!/usr/bin/env python3
"""Build the 57-sector static reference aggregate-interference feasibility screen."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from pyproj import Geod

ROOT = Path(__file__).resolve().parents[1]
GEOD = Geod(ellps="WGS84")


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def unit_vector(az_deg: np.ndarray | float, el_deg: np.ndarray | float) -> np.ndarray:
    az = np.radians(np.asarray(az_deg, dtype=float))
    el = np.radians(np.asarray(el_deg, dtype=float))
    return np.stack(
        (np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)),
        axis=-1,
    )


def angular_separation(
    az1: np.ndarray, el1: np.ndarray, az2: float, el2: float
) -> np.ndarray:
    first = unit_vector(az1, el1)
    second = unit_vector(float(az2), float(el2))
    return np.degrees(np.arccos(np.clip(first @ second, -1.0, 1.0)))


def sa509_gain(phi: np.ndarray, row: pd.Series, multiple: bool) -> np.ndarray:
    phi = np.asarray(phi, dtype=float)
    out = np.empty_like(phi)
    g0 = float(row["g0_dbi"])
    p0 = float(row["phi0_deg"])
    p1 = float(row["phi1_deg"])
    p2 = float(row["phi2_deg"])
    m1 = phi < p1
    m2 = (phi >= p1) & (phi < p2)
    m3 = (phi >= p2) & (phi < 48.0)
    m4 = (phi >= 48.0) & (phi < 80.0)
    m5 = (phi >= 80.0) & (phi < 120.0)
    m6 = phi >= 120.0
    out[m1] = g0 - 3.0 * (phi[m1] / p0) ** 2
    out[m2] = g0 - (20.0 if multiple else 17.0)
    out[m3] = (29.0 if multiple else 32.0) - 25.0 * np.log10(phi[m3])
    if multiple:
        out[m4], out[m5], out[m6] = -13.0, -8.0, -13.0
    else:
        out[m4], out[m5], out[m6] = -10.0, -5.0, -10.0
    return out


def wrap_delta(first: float, second: float) -> float:
    return (float(first) - float(second) + 180.0) % 360.0 - 180.0


def element_gain(
    target_az: float,
    target_el: float,
    sector_az: float,
    boresight_el: float,
    peak_gain: float,
    hbw: float,
    vbw: float,
    amax: float,
    slav: float,
) -> tuple[float, float, float]:
    dh = wrap_delta(target_az, sector_az)
    dv = float(target_el) - float(boresight_el)
    ah = min(12.0 * (dh / hbw) ** 2, amax)
    av = min(12.0 * (dv / vbw) ** 2, slav)
    gain = peak_gain - min(ah + av, amax)
    return gain, dh, dv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/e3_57_sector_reference_screen.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    inp = {k: ROOT / v for k, v in cfg["inputs"].items()}
    work = ROOT / cfg["outputs"]["work_dir"]
    review = ROOT / cfg["outputs"]["review_dir"]
    work.mkdir(parents=True, exist_ok=True)
    review.mkdir(parents=True, exist_ok=True)

    mechanism = json.loads(
        (work / "P452_MECHANISM_FACTORISATION_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    if not mechanism["external_direct_gain_factorization_supported"]:
        raise ValueError("Mechanism audit does not support the reference screen")

    p452 = pd.read_csv(inp["all_site_basic_loss_csv"])
    sites = pd.read_csv(inp["bs_sites_csv"])
    sectors = pd.read_csv(inp["bs_sectors_csv"])
    station = pd.read_csv(inp["earth_station_csv"])
    patterns = pd.read_csv(inp["pattern_parameters_csv"])
    track = pd.read_csv(inp["selected_pass_track_csv"])

    expected = cfg["expected"]
    assert len(station) == 1
    assert len(sites) == int(expected["site_count"])
    assert len(sectors) == int(expected["sector_count"])
    protected = track.loc[
        pd.to_numeric(track["elevation_deg"], errors="raise")
        >= float(expected["minimum_elevation_deg"])
    ].copy().reset_index(drop=True)
    assert len(protected) == int(expected["protected_sample_count"])

    st = station.iloc[0]
    nominal_coast = float(expected["nominal_coast_distance_km"])
    nominal_p452 = p452.loc[
        np.isclose(p452["coast_distance_km"], nominal_coast)
    ].copy()
    assert len(nominal_p452) == 19 * 7 * 2

    nominal_eff = float(cfg["power_accounting"]["nominal_aperture_efficiency"])
    pattern_types = list(cfg["power_accounting"]["earth_station_pattern_types"])
    pattern_rows = {}
    for ptype in pattern_types:
        row = patterns.loc[
            np.isclose(patterns["aperture_efficiency"], nominal_eff)
            & (patterns["pattern_type"].astype(str) == ptype)
        ]
        assert len(row) == 1
        pattern_rows[ptype] = row.iloc[0]

    # Site geometry and time-varying earth-station gains.
    es_frames = []
    site_geometry = []
    for _, site in sites.sort_values("site_id").iterrows():
        station_to_site_az, _, distance_m = GEOD.inv(
            float(st["longitude_deg"]),
            float(st["latitude_deg"]),
            float(site["longitude_deg"]),
            float(site["latitude_deg"]),
        )
        station_to_site_az %= 360.0
        station_to_site_el = math.degrees(
            math.atan2(
                float(site["antenna_altitude_m_asl"]) - float(st["altitude_m_asl"]),
                distance_m,
            )
        )
        site_to_station_az, _, reverse_distance_m = GEOD.inv(
            float(site["longitude_deg"]),
            float(site["latitude_deg"]),
            float(st["longitude_deg"]),
            float(st["latitude_deg"]),
        )
        site_to_station_az %= 360.0
        site_to_station_el = math.degrees(
            math.atan2(
                float(st["altitude_m_asl"]) - float(site["antenna_altitude_m_asl"]),
                reverse_distance_m,
            )
        )
        off_axis = angular_separation(
            protected["azimuth_deg"].to_numpy(float),
            protected["elevation_deg"].to_numpy(float),
            station_to_site_az,
            station_to_site_el,
        )
        for ptype in pattern_types:
            gains = sa509_gain(
                off_axis,
                pattern_rows[ptype],
                multiple=(ptype == "multiple_entry_section_1_2"),
            )
            es_frames.append(
                pd.DataFrame(
                    {
                        "site_id": str(site["site_id"]),
                        "time_utc": protected["time_utc"],
                        "time_s": protected["time_s"],
                        "satellite_elevation_deg": protected["elevation_deg"],
                        "station_to_site_azimuth_deg": station_to_site_az,
                        "station_to_site_elevation_deg": station_to_site_el,
                        "earth_station_off_axis_deg": off_axis,
                        "earth_station_gain_dbi": gains,
                        "earth_station_pattern_type": ptype,
                        "aperture_efficiency": nominal_eff,
                    }
                )
            )
        site_geometry.append(
            {
                "site_id": str(site["site_id"]),
                "station_to_site_azimuth_deg": station_to_site_az,
                "station_to_site_elevation_deg": station_to_site_el,
                "site_to_station_azimuth_deg": site_to_station_az,
                "site_to_station_elevation_deg": site_to_station_el,
                "distance_m": distance_m,
            }
        )
    es_gain = pd.concat(es_frames, ignore_index=True)
    assert len(es_gain) == int(expected["expected_es_gain_rows"])
    es_gain.to_csv(
        work / "earth_station_site_gain_timeseries.csv.gz",
        index=False,
        compression="gzip",
    )
    geometry = pd.DataFrame(site_geometry)

    # Sector reference gains.
    ep = cfg["bs_element_pattern"]
    sector_rows = []
    for _, sector in sectors.sort_values("sector_id").iterrows():
        site_geo = geometry.loc[geometry["site_id"] == str(sector["site_id"])]
        assert len(site_geo) == 1
        site_geo = site_geo.iloc[0]
        element, dh, dv = element_gain(
            float(site_geo["site_to_station_azimuth_deg"]),
            float(site_geo["site_to_station_elevation_deg"]),
            float(sector["azimuth_deg"]),
            -float(sector["downtilt_deg"]),
            float(sector["element_gain_dbi"]),
            float(ep["horizontal_3db_beamwidth_deg"]),
            float(ep["vertical_3db_beamwidth_deg"]),
            float(ep["front_back_limit_db"]),
            float(ep["vertical_sidelobe_limit_db"]),
        )
        element_count = int(sector["array_rows"]) * int(sector["array_cols"])
        coherent_upper = element + 10.0 * math.log10(element_count)
        for case, gain in [
            ("ZERO_DBI_PROPAGATION_REFERENCE", 0.0),
            ("ELEMENT_PATTERN_REFERENCE", element),
            ("COHERENT_ARRAY_UPPER_ENVELOPE", coherent_upper),
        ]:
            for _, loss_row in nominal_p452.loc[
                nominal_p452["site_id"] == str(sector["site_id"])
            ].iterrows():
                power_dbw_100 = float(sector["conducted_power_dbm_per_100mhz"]) - 30.0
                bw_adjustment = 10.0 * math.log10(
                    float(cfg["power_accounting"]["protected_bandwidth_mhz"])
                    / float(cfg["power_accounting"]["reference_bandwidth_mhz"])
                )
                activity = float(sector["activity_factor"])
                activity_db = 10.0 * math.log10(activity) if activity > 0 else -np.inf
                base = (
                    power_dbw_100
                    + bw_adjustment
                    + activity_db
                    + gain
                    - float(loss_row["basic_transmission_loss_db"])
                    - float(cfg["power_accounting"]["polarization_mismatch_loss_db"])
                )
                sector_rows.append(
                    {
                        "sector_id": str(sector["sector_id"]),
                        "site_id": str(sector["site_id"]),
                        "p452_time_percentage": float(loss_row["time_percentage"]),
                        "polarization_label": str(loss_row["polarization_label"]),
                        "bs_gain_case": case,
                        "bs_gain_dbi": gain,
                        "element_pattern_gain_dbi": element,
                        "coherent_array_upper_gain_dbi": coherent_upper,
                        "horizontal_offset_deg": dh,
                        "vertical_offset_deg": dv,
                        "conducted_power_dbw_per_100mhz": power_dbw_100,
                        "bandwidth_adjustment_db": bw_adjustment,
                        "activity_factor": activity,
                        "activity_adjustment_db": activity_db,
                        "basic_transmission_loss_db": float(
                            loss_row["basic_transmission_loss_db"]
                        ),
                        "base_received_before_es_gain_dbw_per_10mhz": base,
                    }
                )
    static = pd.DataFrame(sector_rows)
    assert len(static) == int(expected["expected_static_sector_rows"])
    static.to_csv(work / "sector_static_reference_accounting.csv", index=False)

    # Aggregate the network in linear power, preserving all scenario dimensions.
    long_threshold = float(cfg["protection"]["long_threshold_dbw_per_10mhz"])
    short_threshold = float(cfg["protection"]["short_threshold_dbw_per_10mhz"])
    aggregate_frames = []
    peak_contribution_frames = []
    top_n = int(cfg["review"]["top_sector_count_per_scenario"])

    scenarios = static[
        ["p452_time_percentage", "polarization_label", "bs_gain_case"]
    ].drop_duplicates().sort_values(
        ["p452_time_percentage", "polarization_label", "bs_gain_case"]
    )

    for scenario in scenarios.itertuples(index=False):
        sector_scenario = static.loc[
            np.isclose(static["p452_time_percentage"], scenario.p452_time_percentage)
            & (static["polarization_label"] == scenario.polarization_label)
            & (static["bs_gain_case"] == scenario.bs_gain_case)
        ].copy()
        assert len(sector_scenario) == 57

        for ptype in pattern_types:
            es_case = es_gain.loc[
                es_gain["earth_station_pattern_type"] == ptype
            ][["site_id", "time_utc", "time_s", "earth_station_gain_dbi"]]
            site_base_linear = (
                sector_scenario.assign(
                    base_linear=10.0
                    ** (
                        sector_scenario[
                            "base_received_before_es_gain_dbw_per_10mhz"
                        ].to_numpy(float)
                        / 10.0
                    )
                )
                .groupby("site_id", as_index=False)["base_linear"]
                .sum()
            )
            joined = es_case.merge(site_base_linear, on="site_id", validate="many_to_one")
            joined["received_linear"] = joined["base_linear"] * (
                10.0 ** (joined["earth_station_gain_dbi"].to_numpy(float) / 10.0)
            )
            aggregate = (
                joined.groupby(["time_utc", "time_s"], as_index=False)[
                    "received_linear"
                ]
                .sum()
                .sort_values("time_s")
            )
            aggregate_dbw = 10.0 * np.log10(aggregate["received_linear"].to_numpy(float))
            frame = aggregate[["time_utc", "time_s"]].copy()
            frame["p452_time_percentage"] = scenario.p452_time_percentage
            frame["polarization_label"] = scenario.polarization_label
            frame["bs_gain_case"] = scenario.bs_gain_case
            frame["earth_station_pattern_type"] = ptype
            frame["aggregate_interference_dbw_per_10mhz"] = aggregate_dbw
            frame["long_threshold_dbw_per_10mhz"] = long_threshold
            frame["short_threshold_dbw_per_10mhz"] = short_threshold
            frame["long_exceeded"] = aggregate_dbw > long_threshold
            frame["short_exceeded"] = aggregate_dbw > short_threshold
            frame["required_long_backoff_db"] = np.maximum(
                0.0, aggregate_dbw - long_threshold
            )
            frame["required_short_backoff_db"] = np.maximum(
                0.0, aggregate_dbw - short_threshold
            )
            frame["maximum_common_scale_for_long"] = 10.0 ** (
                -frame["required_long_backoff_db"].to_numpy(float) / 10.0
            )
            frame["maximum_common_scale_for_short"] = 10.0 ** (
                -frame["required_short_backoff_db"].to_numpy(float) / 10.0
            )
            aggregate_frames.append(frame)

            peak_index = int(np.argmax(aggregate_dbw))
            peak_time = float(frame.iloc[peak_index]["time_s"])
            peak_rows = joined.loc[np.isclose(joined["time_s"], peak_time)].copy()
            sector_peak = sector_scenario.merge(
                peak_rows[["site_id", "earth_station_gain_dbi"]],
                on="site_id",
                validate="many_to_one",
            )
            sector_peak["sector_received_dbw_per_10mhz"] = (
                sector_peak["base_received_before_es_gain_dbw_per_10mhz"]
                + sector_peak["earth_station_gain_dbi"]
            )
            sector_peak["sector_received_linear"] = 10.0 ** (
                sector_peak["sector_received_dbw_per_10mhz"].to_numpy(float) / 10.0
            )
            total = float(sector_peak["sector_received_linear"].sum())
            sector_peak["fraction_of_aggregate_power"] = (
                sector_peak["sector_received_linear"] / total
            )
            sector_peak = sector_peak.sort_values(
                "sector_received_linear", ascending=False
            ).head(top_n)
            sector_peak["rank"] = np.arange(1, len(sector_peak) + 1)
            sector_peak["peak_time_s"] = peak_time
            sector_peak["earth_station_pattern_type"] = ptype
            peak_contribution_frames.append(
                sector_peak[
                    [
                        "p452_time_percentage",
                        "polarization_label",
                        "bs_gain_case",
                        "earth_station_pattern_type",
                        "peak_time_s",
                        "rank",
                        "sector_id",
                        "site_id",
                        "sector_received_dbw_per_10mhz",
                        "fraction_of_aggregate_power",
                    ]
                ]
            )

    aggregate = pd.concat(aggregate_frames, ignore_index=True)
    assert len(aggregate) == int(expected["expected_aggregate_rows"])
    aggregate.to_csv(
        work / "network_aggregate_reference_timeseries.csv.gz",
        index=False,
        compression="gzip",
    )
    peak_contributions = pd.concat(peak_contribution_frames, ignore_index=True)
    peak_contributions.to_csv(work / "peak_top_sector_contributions.csv", index=False)

    group_cols = [
        "p452_time_percentage",
        "polarization_label",
        "bs_gain_case",
        "earth_station_pattern_type",
    ]
    scenario_summary = (
        aggregate.groupby(group_cols, as_index=False)
        .agg(
            maximum_aggregate_interference_dbw_per_10mhz=(
                "aggregate_interference_dbw_per_10mhz",
                "max",
            ),
            minimum_aggregate_interference_dbw_per_10mhz=(
                "aggregate_interference_dbw_per_10mhz",
                "min",
            ),
            mean_aggregate_interference_dbw_per_10mhz=(
                "aggregate_interference_dbw_per_10mhz",
                "mean",
            ),
            long_exceedance_fraction=("long_exceeded", "mean"),
            short_exceedance_fraction=("short_exceeded", "mean"),
            maximum_required_long_backoff_db=("required_long_backoff_db", "max"),
            maximum_required_short_backoff_db=("required_short_backoff_db", "max"),
            median_required_long_backoff_db=("required_long_backoff_db", "median"),
            median_required_short_backoff_db=("required_short_backoff_db", "median"),
        )
        .sort_values(group_cols)
    )
    scenario_summary.to_csv(work / "network_reference_scenario_summary.csv", index=False)

    dominant = (
        peak_contributions.loc[peak_contributions["rank"] == 1]
        .groupby(["sector_id", "site_id"], as_index=False)
        .agg(
            scenarios_as_top_contributor=("rank", "size"),
            mean_top_fraction=("fraction_of_aggregate_power", "mean"),
            maximum_top_fraction=("fraction_of_aggregate_power", "max"),
        )
        .sort_values("scenarios_as_top_contributor", ascending=False)
    )
    dominant.to_csv(work / "dominant_sector_summary.csv", index=False)

    # Figures.
    subset = aggregate.loc[
        np.isclose(aggregate["p452_time_percentage"], 20.0)
        & (aggregate["polarization_label"] == "H")
        & (aggregate["earth_station_pattern_type"] == "multiple_entry_section_1_2")
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    for case, group in subset.groupby("bs_gain_case"):
        ax.plot(group["time_s"], group["aggregate_interference_dbw_per_10mhz"], label=case)
    ax.axhline(long_threshold, linestyle="--", label="long threshold")
    ax.axhline(short_threshold, linestyle=":", label="short threshold")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Aggregate interference (dBW/10 MHz)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7)
    ax.set_title("57-sector reference aggregate: p=20%, H, multiple-entry pattern")
    fig.tight_layout()
    fig.savefig(review / "aggregate_p20_H_multiple.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    for case, group in subset.groupby("bs_gain_case"):
        ax.plot(group["time_s"], group["required_short_backoff_db"], label=case)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Required common short-cap backoff (dB)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7)
    ax.set_title("57-sector short-threshold feasibility envelope")
    fig.tight_layout()
    fig.savefig(review / "required_short_backoff_p20_H_multiple.png", dpi=180)
    plt.close(fig)

    global_peak_row = scenario_summary.sort_values(
        "maximum_aggregate_interference_dbw_per_10mhz"
    ).iloc[-1]
    peak_case = peak_contributions.loc[
        np.isclose(
            peak_contributions["p452_time_percentage"],
            global_peak_row["p452_time_percentage"],
        )
        & (
            peak_contributions["polarization_label"]
            == global_peak_row["polarization_label"]
        )
        & (peak_contributions["bs_gain_case"] == global_peak_row["bs_gain_case"])
        & (
            peak_contributions["earth_station_pattern_type"]
            == global_peak_row["earth_station_pattern_type"]
        )
    ].sort_values("rank")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(peak_case["sector_id"], peak_case["fraction_of_aggregate_power"])
    ax.tick_params(axis="x", rotation=60, labelsize=7)
    ax.set_ylabel("Fraction of aggregate received power")
    ax.set_title("Top sector contributions at the global conditional peak")
    fig.tight_layout()
    fig.savefig(review / "global_peak_top_sector_contributions.png", dpi=180)
    plt.close(fig)

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "REFERENCE_SCREEN_READY_FOR_HUMAN_REVIEW",
        "claim_boundary": cfg["claim_boundary"]["sector_screen"],
        "sector_count": int(expected["sector_count"]),
        "site_count": int(expected["site_count"]),
        "protected_sample_count": len(protected),
        "aggregate_row_count": len(aggregate),
        "global_maximum_aggregate_interference_dbw_per_10mhz": float(
            aggregate["aggregate_interference_dbw_per_10mhz"].max()
        ),
        "global_maximum_required_short_backoff_db": float(
            aggregate["required_short_backoff_db"].max()
        ),
        "global_maximum_required_long_backoff_db": float(
            aggregate["required_long_backoff_db"].max()
        ),
        "mechanism_factorization_status": mechanism["status"],
        "open_items": [
            "Final composite WMMSE beam gains are not available.",
            "Propagation-time and operational-exceedance composition is not frozen.",
            "Physical polarization/XPD model is not frozen.",
            "This close-in synthetic layout may be intentionally severe and needs a non-degeneracy decision.",
        ],
        "next_gate": cfg["review"]["next_gate"],
    }
    write_json(work / "E3_57_SECTOR_REFERENCE_SCREEN_DECISION.json", decision)
    (work / "E3_57_SECTOR_REFERENCE_SCREEN_DECISION.md").write_text(
        "# E3 57-sector reference feasibility screen\n\n"
        f"- Status: `{decision['status']}`\n"
        f"- Sectors: `{decision['sector_count']}`\n"
        f"- Protected samples: `{decision['protected_sample_count']}`\n"
        f"- Aggregate rows: `{decision['aggregate_row_count']}`\n"
        f"- Global maximum aggregate interference: "
        f"`{decision['global_maximum_aggregate_interference_dbw_per_10mhz']:.6f}` "
        "dBW/10 MHz\n"
        f"- Maximum short-cap backoff: "
        f"`{decision['global_maximum_required_short_backoff_db']:.6f}` dB\n"
        f"- Next gate: `{decision['next_gate']}`\n\n"
        "This is a reference feasibility screen. It does not use final composite "
        "WMMSE beam gains and is not a dynamic-controller, paper, or compliance result.\n",
        encoding="utf-8",
    )

    print("E3 57-SECTOR REFERENCE FEASIBILITY SCREEN BUILD: PASS")
    print(json.dumps(decision, indent=2))
    print("\nSCENARIO SUMMARY")
    print(scenario_summary.to_string(index=False))
    print("\nDOMINANT SECTORS")
    print(dominant.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
