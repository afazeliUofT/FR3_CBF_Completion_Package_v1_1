from fr3_cbf.geo import build_link_geometry, haversine_distance_km


def test_haversine_and_geometry():
    d = haversine_distance_km(43.65, -79.38, 43.75, -79.30)
    assert 10 < d < 15
    g = build_link_geometry(43.65, -79.38, 43.75, -79.30, 165, 175, 105)
    assert g.distance_km == d
    assert g.mean_terrain_clearance_m > 0
