from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd

from fr3_cbf.protected_pass_records import (
    complete_pass_catalog,
    kappa_from_gain_table,
    sa509_gain,
    select_passes_by_peak_date,
    threshold_w,
)

ROOT = Path(__file__).resolve().parents[1]


def test_complete_pass_selection_by_peak_date():
    time = pd.date_range(
        "2026-07-27T00:00:00Z",
        periods=30,
        freq="10s",
    )
    elevation = np.array(
        [-10, -5, 0, 6, 10, 6, 0, -5, -10, -10,
         -10, 0, 6, 15, 20, 15, 6, 0, -10, -10,
         -10, 0, 7, 8, 7, 0, -10, -10, -10, -10],
        dtype=float,
    )
    frame = pd.DataFrame(
        {
            "time_utc": [x.isoformat() for x in time],
            "time_s": np.arange(30) * 10.0,
            "azimuth_deg": np.linspace(0, 100, 30),
            "elevation_deg": elevation,
            "slant_range_km": np.full(30, 1000.0),
        }
    )
    catalog = complete_pass_catalog(frame, 5.0)
    selected = select_passes_by_peak_date(
        catalog,
        ["2026-07-27"],
    )
    assert len(selected) == 1
    assert selected[0].maximum_elevation_deg == 20.0


def test_sa509_single_entry_is_three_db_higher_in_far_sidelobe():
    parameters = pd.Series(
        {
            "g0_dbi": 59.0,
            "phi0_deg": 0.098,
            "phi1_deg": 0.253,
            "phi2_deg": 0.397,
        }
    )
    phi = np.array([5.0, 30.0, 60.0, 100.0, 150.0])
    multiple = sa509_gain(phi, parameters, True)
    single = sa509_gain(phi, parameters, False)
    assert np.allclose(single - multiple, 3.0)


def test_kappa_formula_and_threshold():
    gain = pd.DataFrame(
        {
            "time_s": [0.0, 1.0, 0.0, 1.0],
            "site_id": ["A", "A", "B", "B"],
            "gain_multiple_entry_dbi": [-10.0, -11.0, -20.0, -21.0],
        }
    )
    static = pd.DataFrame(
        {
            "sector_id": [f"S{index:02d}" for index in range(57)],
            "site_id": ["A"] + ["B"] * 56,
            "p452_time_percentage": [20.0] * 57,
            "polarization_label": ["H"] * 57,
            "bs_gain_case": ["ELEMENT_PATTERN_REFERENCE"] * 57,
            "element_pattern_gain_dbi": [8.0] * 57,
            "basic_transmission_loss_db": [120.0] * 57,
        }
    )
    value, ids = kappa_from_gain_table(
        gain,
        static,
        20.0,
        "H",
        "ELEMENT_PATTERN_REFERENCE",
        "gain_multiple_entry_dbi",
    )
    assert value.shape == (2, 57)
    assert ids[0] == "S00"
    assert ids[-1] == "S56"
    assert np.isclose(value[0, 0], 10.0 ** ((8 - 120 - 10) / 10))
    assert np.isclose(threshold_w(-150.0), 1e-15)


def test_owned_sources_parse():
    for relative in [
        "src/fr3_cbf/protected_pass_records.py",
        "scripts/45_0_generate_protected_pass_records.py",
        "scripts/45_1_validate_protected_pass_records.py",
        "scripts/45_2_build_complete_phase1_candidate.py",
        "scripts/45_3_sync_protected_pass_status.py",
        "scripts/45_4_build_protected_pass_review_bundle.py",
        "tests/test_protected_pass_records_phase1.py",
    ]:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
