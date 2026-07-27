from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts/23_4_recover_protected_window_history.py"
    spec = importlib.util.spec_from_file_location("pw_recovery", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def historical_selection() -> dict:
    return {
        "sector_id": "E3_SITE_11_SEC_1",
        "site_id": "E3_SITE_11",
        "distance_m": 3774.9172176348084,
        "minimum_earth_station_off_axis_deg": 1.5758955144300562,
    }


def historical_summary() -> pd.DataFrame:
    rows = []
    for index in range(57):
        site = f"E3_SITE_{index // 3 + 1:02d}"
        sector = f"{site}_SEC_{index % 3 + 1}"
        minimum = 1.5758955144300562 if site == "E3_SITE_11" else 10.0 + index
        rows.append(
            {
                "site_id": site,
                "sector_id": sector,
                "station_to_site_distance_m": 2000.0 + index,
                "minimum_off_axis_deg_during_selected_track": minimum,
                "median_off_axis_deg_during_selected_track": minimum + 1.0,
                "maximum_reference_gain_dbi_during_selected_track": 5.0,
            }
        )
    return pd.DataFrame(rows)


def test_semantic_selection_extracts_expected_values():
    module = load_module()
    assert module.semantic_selection(historical_selection()) == (
        "E3_SITE_11_SEC_1",
        "E3_SITE_11",
        3774.9172176348084,
        1.5758955144300562,
    )


def test_historical_summary_validation_passes():
    module = load_module()
    module.validate_historical_summary(
        historical_summary(),
        historical_selection(),
        expected_sector_count=57,
    )


def test_protected_summary_is_rejected():
    module = load_module()
    frame = historical_summary()
    frame["selection_window"] = "earth_station_elevation_ge_minimum_elevation"
    with pytest.raises(ValueError, match="protected-window"):
        module.validate_historical_summary(
            frame,
            historical_selection(),
            expected_sector_count=57,
        )


def test_wrong_global_minimum_is_rejected():
    module = load_module()
    frame = historical_summary()
    frame.loc[0, "minimum_off_axis_deg_during_selected_track"] = 0.5
    with pytest.raises(ValueError, match="global minimum"):
        module.validate_historical_summary(
            frame,
            historical_selection(),
            expected_sector_count=57,
        )


def test_historical_minimum_is_numerically_stable():
    frame = historical_summary()
    value = float(frame["minimum_off_axis_deg_during_selected_track"].min())
    assert math.isclose(value, 1.5758955144300562, rel_tol=0.0, abs_tol=1e-12)
