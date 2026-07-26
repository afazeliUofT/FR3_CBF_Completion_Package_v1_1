import numpy as np

from fr3_cbf.grids import bilinear_interpolate


def test_bilinear_interpolation():
    lat = np.array([0.0, 1.0])
    lon = np.array([10.0, 11.0])
    field = np.array([[0.0, 1.0], [2.0, 3.0]])
    assert np.isclose(bilinear_interpolate(lat, lon, field, 0.5, 10.5), 1.5)
