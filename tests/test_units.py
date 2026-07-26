import math

from fr3_cbf.units import db_to_linear, interference_fade_margin_penalty_db, thermal_noise_w


def test_db_roundtrip_reference():
    assert math.isclose(db_to_linear(10.0), 10.0)
    assert math.isclose(interference_fade_margin_penalty_db(-10.0), 10 * math.log10(1.1))
    assert math.isclose(interference_fade_margin_penalty_db(19.0), 10 * math.log10(1 + 10**1.9))


def test_thermal_noise_positive():
    assert thermal_noise_w(30e6, 4.5) > 0
