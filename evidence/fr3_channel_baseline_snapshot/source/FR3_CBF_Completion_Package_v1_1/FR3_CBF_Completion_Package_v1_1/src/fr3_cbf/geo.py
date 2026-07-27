from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088


def haversine_distance_km(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1_deg, lon1_deg, lat2_deg, lon2_deg])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def spherical_midpoint_deg(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> tuple[float, float]:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1_deg, lon1_deg, lat2_deg, lon2_deg])
    bx = math.cos(lat2) * math.cos(lon2 - lon1)
    by = math.cos(lat2) * math.sin(lon2 - lon1)
    lat3 = math.atan2(math.sin(lat1) + math.sin(lat2), math.sqrt((math.cos(lat1) + bx) ** 2 + by**2))
    lon3 = lon1 + math.atan2(by, math.cos(lat1) + bx)
    lon3 = (lon3 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
    return math.degrees(lat3), math.degrees(lon3)


def path_inclination_mrad(tx_alt_m_asl: float, rx_alt_m_asl: float, distance_km: float) -> float:
    if distance_km <= 0:
        raise ValueError("distance_km must be positive")
    # m/km numerically equals mrad for a small path angle.
    return abs(float(rx_alt_m_asl) - float(tx_alt_m_asl)) / distance_km


def mean_path_terrain_clearance_m(
    tx_alt_m_asl: float,
    rx_alt_m_asl: float,
    distance_km: float,
    mean_terrain_m_asl: float,
) -> float:
    if distance_km <= 0:
        raise ValueError("distance_km must be positive")
    return (float(tx_alt_m_asl) + float(rx_alt_m_asl)) / 2.0 - distance_km**2 / 102.0 - float(mean_terrain_m_asl)


@dataclass(frozen=True)
class LinkGeometry:
    distance_km: float
    midpoint_lat_deg: float
    midpoint_lon_deg: float
    path_inclination_mrad: float
    mean_terrain_clearance_m: float


def build_link_geometry(
    tx_lat_deg: float,
    tx_lon_deg: float,
    rx_lat_deg: float,
    rx_lon_deg: float,
    tx_alt_m_asl: float,
    rx_alt_m_asl: float,
    mean_terrain_m_asl: float,
) -> LinkGeometry:
    distance = haversine_distance_km(tx_lat_deg, tx_lon_deg, rx_lat_deg, rx_lon_deg)
    mid_lat, mid_lon = spherical_midpoint_deg(tx_lat_deg, tx_lon_deg, rx_lat_deg, rx_lon_deg)
    return LinkGeometry(
        distance_km=distance,
        midpoint_lat_deg=mid_lat,
        midpoint_lon_deg=mid_lon,
        path_inclination_mrad=path_inclination_mrad(tx_alt_m_asl, rx_alt_m_asl, distance),
        mean_terrain_clearance_m=mean_path_terrain_clearance_m(
            tx_alt_m_asl, rx_alt_m_asl, distance, mean_terrain_m_asl
        ),
    )
