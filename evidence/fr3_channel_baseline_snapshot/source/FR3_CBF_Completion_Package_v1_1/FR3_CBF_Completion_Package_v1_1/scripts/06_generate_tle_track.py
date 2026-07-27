from __future__ import annotations

import argparse
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.io import sha256_file, write_json

WGS84_A_KM = 6378.137
WGS84_E2 = 6.69437999014e-3


def read_tle(path: Path) -> tuple[str, str, str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) == 2:
        return "UNNAMED", lines[0], lines[1]
    if len(lines) >= 3:
        return lines[0], lines[1], lines[2]
    raise ValueError("TLE file must contain two element lines, with optional name line")


def parse_iso_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def datetimes(start: datetime, duration_s: int, step_s: float) -> list[datetime]:
    count = int(math.floor(duration_s / step_s)) + 1
    return [start + timedelta(seconds=index * step_s) for index in range(count)]


def skyfield_track(
    name: str,
    line1: str,
    line2: str,
    times: list[datetime],
    lat_deg: float,
    lon_deg: float,
    alt_m: float,
) -> pd.DataFrame:
    try:
        from skyfield.api import EarthSatellite, load, wgs84
    except ImportError as exc:
        raise SystemExit("Install requirements-full.txt to use the paper-preferred Skyfield engine") from exc
    ts = load.timescale()
    sat = EarthSatellite(line1, line2, name, ts)
    station = wgs84.latlon(latitude_degrees=lat_deg, longitude_degrees=lon_deg, elevation_m=alt_m)
    t = ts.from_datetimes(times)
    alt, az, distance = (sat - station).at(t).altaz()
    return pd.DataFrame(
        {
            "time_utc": [x.isoformat() for x in times],
            "time_s": [(x - times[0]).total_seconds() for x in times],
            "satellite_name": name,
            "azimuth_deg": az.degrees,
            "elevation_deg": alt.degrees,
            "slant_range_km": distance.km,
            "orbit_engine": "skyfield_earthsatellite",
        }
    )


# The functions below provide a transparent lightweight reference. They omit full
# Earth-orientation treatment and therefore are not the preferred paper engine.
def gmst_rad(jdut1: float) -> float:
    tut1 = (jdut1 - 2451545.0) / 36525.0
    seconds = -6.2e-6 * tut1**3 + 0.093104 * tut1**2 + (876600.0 * 3600.0 + 8640184.812866) * tut1 + 67310.54841
    return (seconds * math.pi / 43200.0) % (2.0 * math.pi)


def teme_to_ecef_km(r_teme: np.ndarray, jd: float) -> np.ndarray:
    theta = gmst_rad(jd)
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]]) @ r_teme


def geodetic_to_ecef_km(lat_deg: float, lon_deg: float, alt_m: float) -> np.ndarray:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = WGS84_A_KM / math.sqrt(1.0 - WGS84_E2 * math.sin(lat) ** 2)
    alt_km = alt_m / 1000.0
    return np.array([(n + alt_km) * math.cos(lat) * math.cos(lon), (n + alt_km) * math.cos(lat) * math.sin(lon), (n * (1.0 - WGS84_E2) + alt_km) * math.sin(lat)])


def ecef_to_az_el_range(r_sat: np.ndarray, lat_deg: float, lon_deg: float, alt_m: float) -> tuple[float, float, float]:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    rho = r_sat - geodetic_to_ecef_km(lat_deg, lon_deg, alt_m)
    transform = np.array([[-math.sin(lon), math.cos(lon), 0.0], [-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)], [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]])
    east, north, up = transform @ rho
    rng = float(np.linalg.norm(rho))
    return math.degrees(math.atan2(east, north)) % 360.0, math.degrees(math.asin(up / rng)), rng


def sgp4_reference_track(name: str, line1: str, line2: str, times: list[datetime], lat_deg: float, lon_deg: float, alt_m: float) -> pd.DataFrame:
    try:
        from sgp4.api import Satrec, jday
    except ImportError as exc:
        raise SystemExit("Install requirements-full.txt to use sgp4") from exc
    sat = Satrec.twoline2rv(line1, line2)
    rows = []
    for dt in times:
        sec = dt.second + dt.microsecond / 1e6
        jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, sec)
        error, position, _velocity = sat.sgp4(jd, fr)
        if error != 0:
            raise RuntimeError(f"SGP4 error code {error} at {dt.isoformat()}")
        az, el, rng = ecef_to_az_el_range(teme_to_ecef_km(np.asarray(position, dtype=float), jd + fr), lat_deg, lon_deg, alt_m)
        rows.append({"time_utc": dt.isoformat(), "time_s": (dt - times[0]).total_seconds(), "satellite_name": name, "azimuth_deg": az, "elevation_deg": el, "slant_range_km": rng, "orbit_engine": "sgp4_gmst_reference"})
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a topocentric TLE track")
    parser.add_argument("--tle", required=True)
    parser.add_argument("--start-utc", required=True, help="ISO 8601, e.g. 2026-07-23T12:00:00Z")
    parser.add_argument("--duration-s", type=int, default=900)
    parser.add_argument("--step-s", type=float, default=1.0)
    parser.add_argument("--station-lat", type=float, required=True)
    parser.add_argument("--station-lon", type=float, required=True)
    parser.add_argument("--station-alt-m", type=float, default=0.0)
    parser.add_argument("--engine", choices=["skyfield", "sgp4_reference"], default="skyfield")
    parser.add_argument("--output", default="data/real/e3_track.csv")
    args = parser.parse_args()
    if args.duration_s <= 0 or args.step_s <= 0:
        raise ValueError("duration and step must be positive")
    tle_path = Path(args.tle)
    name, line1, line2 = read_tle(tle_path)
    start = parse_iso_utc(args.start_utc)
    times = datetimes(start, args.duration_s, args.step_s)
    if args.engine == "skyfield":
        df = skyfield_track(name, line1, line2, times, args.station_lat, args.station_lon, args.station_alt_m)
        claim_boundary = "Skyfield topocentric track; independently compare selected pass points before paper use."
    else:
        df = sgp4_reference_track(name, line1, line2, times, args.station_lat, args.station_lon, args.station_alt_m)
        claim_boundary = "Transparent GMST reference only; not the preferred paper-grade orbit/coordinate engine."
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    write_json(
        out.with_suffix(".audit.json"),
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "tle_path": str(tle_path),
            "tle_sha256": sha256_file(tle_path),
            "engine": args.engine,
            "station": {"lat_deg": args.station_lat, "lon_deg": args.station_lon, "alt_m": args.station_alt_m},
            "start_utc": start.isoformat(),
            "duration_s": args.duration_s,
            "step_s": args.step_s,
            "points": len(df),
            "claim_boundary": claim_boundary,
        },
    )
    print(f"Wrote {len(df)} track points to {out} using {args.engine}")
    print(claim_boundary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
