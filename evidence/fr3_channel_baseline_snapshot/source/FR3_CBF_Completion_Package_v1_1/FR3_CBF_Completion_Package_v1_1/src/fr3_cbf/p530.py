from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class P530Result:
    fade_depth_db: float
    exceedance_percent: float
    p0_percent: float
    transition_fade_db: float | None
    method: str
    vsr: float


def subrefractive_parameter(dn75_n_units: float, distance_km: float, frequency_ghz: float, hc_m: float) -> float:
    if dn75_n_units < 0 or distance_km <= 0 or frequency_ghz <= 0:
        raise ValueError("dn75 must be nonnegative; distance and frequency must be positive")
    raw = (dn75_n_units / 50.0) ** 1.8 * math.exp(-hc_m / (2.5 * math.sqrt(distance_km)))
    limit = dn75_n_units * distance_km**1.5 * math.sqrt(frequency_ghz) / 24730.0
    return min(raw, limit)


def multipath_occurrence_factor_percent(
    k_percent: float,
    distance_km: float,
    frequency_ghz: float,
    path_inclination_mrad: float,
    lower_antenna_alt_m_asl: float,
    hc_m: float,
    dn75_n_units: float,
) -> tuple[float, float]:
    if k_percent <= 0 or distance_km <= 0 or frequency_ghz <= 0:
        raise ValueError("K, distance, and frequency must be positive")
    vsr = subrefractive_parameter(dn75_n_units, distance_km, frequency_ghz, hc_m)
    exponent = (
        -0.376 * math.tanh((hc_m - 147.0) / 125.0)
        - 0.334 * abs(path_inclination_mrad) ** 0.39
        - 0.00027 * lower_antenna_alt_m_asl
        + 17.85 * vsr
    )
    p0 = (
        k_percent
        * distance_km**3.51
        * (frequency_ghz**2 + 13.0) ** 0.447
        * 10.0**exponent
    )
    return p0, vsr


def fade_exceedance_worst_month_percent(
    fade_depth_db: float,
    k_percent: float,
    distance_km: float,
    frequency_ghz: float,
    path_inclination_mrad: float,
    lower_antenna_alt_m_asl: float,
    hc_m: float,
    dn75_n_units: float,
    use_all_percentages_method: bool = True,
) -> P530Result:
    """Implement ITU-R P.530-19 section 2.3.1/2.3.2.

    Returns the percentage of the average worst month for which a fade depth A is exceeded.
    Multipath fading is set to zero for paths of 5 km or shorter as stated in P.530-19.
    """
    a = float(fade_depth_db)
    if a < 0:
        raise ValueError("fade_depth_db must be nonnegative")
    if distance_km <= 5.0:
        return P530Result(a, 0.0, 0.0, None, "P.530-19: multipath set to zero for d <= 5 km", 0.0)

    p0, vsr = multipath_occurrence_factor_percent(
        k_percent,
        distance_km,
        frequency_ghz,
        path_inclination_mrad,
        lower_antenna_alt_m_asl,
        hc_m,
        dn75_n_units,
    )

    if not use_all_percentages_method:
        pw = p0 * 10.0 ** (-a / 10.0)
        return P530Result(a, min(100.0, max(0.0, pw)), p0, None, "P.530-19 Eq. (7)/(13)", vsr)

    if p0 <= 0:
        return P530Result(a, 0.0, p0, None, "P.530-19 all-percentages", vsr)

    at = 25.0 + 1.2 * math.log10(p0)
    if a >= at:
        pw = p0 * 10.0 ** (-a / 10.0)
        method = "P.530-19 Eq. (13), deep-fading branch"
    else:
        pt = min(p0 * 10.0 ** (-at / 10.0), 99.9999)
        inner = -math.log((100.0 - pt) / 100.0)
        if inner <= 0 or at == 0:
            raise ArithmeticError("P.530 shallow-fading interpolation is undefined for this parameter set")
        q_a_prime = -20.0 * math.log10(inner) / at
        # P.530-19 Eq. (16). The full product
        # [1 + 0.3*10^(-A_t/20)] * 10^(-0.016*A_t) is the denominator.
        # This interpretation is also required for continuity with Eq. (17) at A=A_t.
        denominator = (1.0 + 0.3 * 10.0 ** (-at / 20.0)) * 10.0 ** (-0.016 * at)
        q_t = (q_a_prime - 2.0) / denominator - 4.3 * (10.0 ** (-at / 20.0) + at / 800.0)
        q_a = 2.0 + (1.0 + 0.3 * 10.0 ** (-a / 20.0)) * 10.0 ** (-0.016 * a) * (
            q_t + 4.3 * (10.0 ** (-a / 20.0) + a / 800.0)
        )
        pw = 100.0 * (1.0 - math.exp(-10.0 ** (-q_a * a / 20.0)))
        method = "P.530-19 Eqs. (14)-(18), shallow-fading branch"

    return P530Result(a, min(100.0, max(0.0, pw)), p0, at, method, vsr)


def validity_warnings(
    distance_km: float,
    frequency_ghz: float,
    path_inclination_mrad: float,
    lower_antenna_alt_m_asl: float,
    hc_m: float,
    dn75_n_units: float,
    p0_percent: float | None = None,
) -> list[str]:
    warnings: list[str] = []
    if distance_km <= 5.0:
        warnings.append("P.530-19 prescribes zero multipath fading for d <= 5 km; this link cannot support a discriminating multipath S1 test.")
    elif distance_km < 7.5:
        warnings.append("Distance is below the 7.5 km lower end of the Eq. (7) regression dataset.")
    if distance_km > 300.0:
        warnings.append("Distance is above the 300 km upper end of the Eq. (7) regression dataset.")
    if frequency_ghz < 0.45 or frequency_ghz > 45.0:
        warnings.append("Frequency is outside the documented/expected Eq. (7) frequency range.")
    f_min = 15.0 / distance_km if distance_km > 0 else math.inf
    if frequency_ghz < f_min:
        warnings.append(f"Frequency is below the rough lower limit f_min=15/d={f_min:.3f} GHz.")
    if abs(path_inclination_mrad) > 37.0:
        warnings.append("Path inclination exceeds the 37 mrad regression range.")
    if lower_antenna_alt_m_asl < 17.0 or lower_antenna_alt_m_asl > 2300.0:
        warnings.append("Lower antenna altitude is outside the 17-2300 m regression range.")
    if hc_m < 26.0 or hc_m > 1180.0:
        warnings.append("Mean terrain clearance is outside the 26-1180 m regression range.")
    if dn75_n_units < 0.0 or dn75_n_units > 54.0:
        warnings.append("dN75 is outside the 0-54 N-unit regression range.")
    if p0_percent is not None and p0_percent >= 2000.0:
        warnings.append("p0 >= 2000%; P.530 notes the all-percentages curve is monotonic provided p0 < 2000.")
    return warnings
