from __future__ import annotations

import math

BOLTZMANN_J_PER_K = 1.380649e-23


def db_to_linear(value_db: float) -> float:
    return 10.0 ** (float(value_db) / 10.0)


def linear_to_db(value: float) -> float:
    if value <= 0:
        raise ValueError("linear value must be positive")
    return 10.0 * math.log10(float(value))


def dbm_to_w(value_dbm: float) -> float:
    return 10.0 ** ((float(value_dbm) - 30.0) / 10.0)


def w_to_dbm(value_w: float) -> float:
    return linear_to_db(value_w) + 30.0


def dbw_to_w(value_dbw: float) -> float:
    return 10.0 ** (float(value_dbw) / 10.0)


def w_to_dbw(value_w: float) -> float:
    return linear_to_db(value_w)


def thermal_noise_w(bandwidth_hz: float, noise_figure_db: float = 0.0, temperature_k: float = 290.0) -> float:
    if bandwidth_hz <= 0 or temperature_k <= 0:
        raise ValueError("bandwidth_hz and temperature_k must be positive")
    return BOLTZMANN_J_PER_K * temperature_k * bandwidth_hz * db_to_linear(noise_figure_db)


def i_over_n_threshold_w(noise_w: float, i_over_n_db: float) -> float:
    if noise_w <= 0:
        raise ValueError("noise_w must be positive")
    return noise_w * db_to_linear(i_over_n_db)


def interference_fade_margin_penalty_db(i_over_n_db: float) -> float:
    """Additive loss of fade margin caused by interference-to-noise ratio x.

    Delta A = 10 log10(1 + 10^(x/10)).
    """
    return 10.0 * math.log10(1.0 + db_to_linear(i_over_n_db))
