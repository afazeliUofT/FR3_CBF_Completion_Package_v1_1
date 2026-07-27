from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

REQUIRED_NAMES = {
    "logk": "LogK.csv",
    "dn75": "dN75.csv",
    "lat": "LatitudeQuarterDegree.csv",
    "lon": "LongitudeQuarterDegree.csv",
}


def _find_case_insensitive(root: Path, filename: str) -> Path:
    matches = [p for p in root.rglob("*") if p.is_file() and p.name.lower() == filename.lower()]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected exactly one {filename} under {root}; found {len(matches)}")
    return matches[0]


def _read_numeric_csv(path: Path) -> np.ndarray:
    arr = np.genfromtxt(path, delimiter=",", dtype=float)
    if arr.ndim == 0 or np.isnan(arr).all():
        arr = np.genfromtxt(path, dtype=float)
    arr = np.asarray(arr, dtype=float)
    if arr.ndim == 2:
        arr = arr[~np.all(np.isnan(arr), axis=1)]
        arr = arr[:, ~np.all(np.isnan(arr), axis=0)]
    else:
        arr = arr[~np.isnan(arr)]
    if arr.size == 0 or np.isnan(arr).all():
        raise ValueError(f"No numeric data found in {path}")
    return arr


def _regular_axes(lat: np.ndarray, lon: np.ndarray, field: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    candidates: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []

    def add(la: np.ndarray, lo: np.ndarray, fi: np.ndarray) -> None:
        if la.ndim == 1 and lo.ndim == 1 and fi.shape == (la.size, lo.size):
            candidates.append((la.astype(float), lo.astype(float), fi.astype(float)))

    if lat.ndim == 1 and lon.ndim == 1:
        add(lat, lon, field)
        add(lat, lon, field.T)
    if lat.ndim == 2 and lon.ndim == 2:
        if lat.shape == lon.shape == field.shape:
            add(lat[:, 0], lon[0, :], field)
            add(lat[0, :], lon[:, 0], field.T)
        if lat.shape == lon.shape == field.T.shape:
            f = field.T
            add(lat[:, 0], lon[0, :], f)
            add(lat[0, :], lon[:, 0], f.T)
    if lat.ndim == 2 and 1 in lat.shape and lon.ndim == 2 and 1 in lon.shape:
        add(lat.ravel(), lon.ravel(), field)
        add(lat.ravel(), lon.ravel(), field.T)

    for la, lo, fi in candidates:
        if np.all(np.isfinite(la)) and np.all(np.isfinite(lo)) and np.all(np.isfinite(fi)):
            # Require regular mesh orientation: each axis strictly monotone after sorting.
            li = np.argsort(la)
            oi = np.argsort(lo)
            la2 = la[li]
            lo2 = lo[oi]
            if np.all(np.diff(la2) > 0) and np.all(np.diff(lo2) > 0):
                return la2, lo2, fi[np.ix_(li, oi)]
    raise ValueError(
        f"Could not infer regular axes: lat={lat.shape}, lon={lon.shape}, field={field.shape}"
    )


def _normalize_longitude(query_lon: float, lon_axis: np.ndarray) -> float:
    lon = float(query_lon)
    if lon_axis.min() >= 0.0 and lon < 0.0:
        lon %= 360.0
    elif lon_axis.max() <= 180.0 and lon > 180.0:
        lon = ((lon + 180.0) % 360.0) - 180.0
    return lon


def bilinear_interpolate(lat_axis: np.ndarray, lon_axis: np.ndarray, field: np.ndarray, lat: float, lon: float) -> float:
    lon = _normalize_longitude(lon, lon_axis)
    lat = float(lat)
    tol = 1e-9
    if lat < lat_axis[0] - tol or lat > lat_axis[-1] + tol:
        raise ValueError(f"Latitude {lat} outside grid [{lat_axis[0]}, {lat_axis[-1]}]")
    if lon < lon_axis[0] - tol or lon > lon_axis[-1] + tol:
        # Permit a global grid with a duplicated or nearly full 360-degree axis.
        span = lon_axis[-1] - lon_axis[0]
        if span >= 359.0:
            lon = ((lon - lon_axis[0]) % 360.0) + lon_axis[0]
        else:
            raise ValueError(f"Longitude {lon} outside grid [{lon_axis[0]}, {lon_axis[-1]}]")

    i1 = int(np.searchsorted(lat_axis, lat, side="right"))
    j1 = int(np.searchsorted(lon_axis, lon, side="right"))
    i0 = max(0, min(i1 - 1, len(lat_axis) - 2))
    j0 = max(0, min(j1 - 1, len(lon_axis) - 2))
    i1 = i0 + 1
    j1 = j0 + 1

    y0, y1 = lat_axis[i0], lat_axis[i1]
    x0, x1 = lon_axis[j0], lon_axis[j1]
    ty = 0.0 if y1 == y0 else (lat - y0) / (y1 - y0)
    tx = 0.0 if x1 == x0 else (lon - x0) / (x1 - x0)
    q00 = field[i0, j0]
    q01 = field[i0, j1]
    q10 = field[i1, j0]
    q11 = field[i1, j1]
    return float((1 - ty) * ((1 - tx) * q00 + tx * q01) + ty * ((1 - tx) * q10 + tx * q11))


@dataclass(frozen=True)
class P530GridProducts:
    latitude_axis_deg: np.ndarray
    longitude_axis_deg: np.ndarray
    logk_grid: np.ndarray
    dn75_grid: np.ndarray
    source_files: dict[str, str]

    @classmethod
    def from_directory(cls, root: str | Path) -> "P530GridProducts":
        root = Path(root)
        paths = {key: _find_case_insensitive(root, name) for key, name in REQUIRED_NAMES.items()}
        lat = _read_numeric_csv(paths["lat"])
        lon = _read_numeric_csv(paths["lon"])
        logk = _read_numeric_csv(paths["logk"])
        dn75 = _read_numeric_csv(paths["dn75"])
        la, lo, logk2 = _regular_axes(lat, lon, logk)
        la2, lo2, dn752 = _regular_axes(lat, lon, dn75)
        if not np.array_equal(la, la2) or not np.array_equal(lo, lo2):
            raise ValueError("LogK and dN75 axes do not match")
        return cls(
            latitude_axis_deg=la,
            longitude_axis_deg=lo,
            logk_grid=logk2,
            dn75_grid=dn752,
            source_files={k: str(v) for k, v in paths.items()},
        )

    def interpolate(self, latitude_deg: float, longitude_deg: float) -> tuple[float, float]:
        logk = bilinear_interpolate(
            self.latitude_axis_deg, self.longitude_axis_deg, self.logk_grid, latitude_deg, longitude_deg
        )
        dn75 = bilinear_interpolate(
            self.latitude_axis_deg, self.longitude_axis_deg, self.dn75_grid, latitude_deg, longitude_deg
        )
        return 10.0**logk, dn75
