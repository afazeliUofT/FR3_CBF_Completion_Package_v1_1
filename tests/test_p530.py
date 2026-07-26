import math

from fr3_cbf.p530 import fade_exceedance_worst_month_percent, multipath_occurrence_factor_percent

PARAMS = dict(
    k_percent=1e-4,
    distance_km=15.0,
    frequency_ghz=8.0,
    path_inclination_mrad=1.0,
    lower_antenna_alt_m_asl=150.0,
    hc_m=50.0,
    dn75_n_units=20.0,
)


def test_p530_transition_is_continuous():
    p0, _ = multipath_occurrence_factor_percent(**PARAMS)
    at = 25.0 + 1.2 * math.log10(p0)
    left = fade_exceedance_worst_month_percent(at - 1e-6, **PARAMS)
    right = fade_exceedance_worst_month_percent(at + 1e-6, **PARAMS)
    assert math.isclose(left.exceedance_percent, right.exceedance_percent, rel_tol=2e-5, abs_tol=1e-10)


def test_p530_exceedance_decreases_with_fade_depth():
    values = [fade_exceedance_worst_month_percent(a, **PARAMS).exceedance_percent for a in [0, 10, 20, 30, 40]]
    assert all(a >= b for a, b in zip(values, values[1:]))


def test_short_path_zero_multipath():
    result = fade_exceedance_worst_month_percent(20.0, **{**PARAMS, "distance_km": 5.0})
    assert result.exceedance_percent == 0.0
