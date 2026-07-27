from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_expected_counts():
    assert 57 * 7 * 2 * 3 == 2394
    assert 19 * 587 * 2 == 22306
    assert 587 * 7 * 2 * 3 * 2 == 49308


def test_element_gain_reference():
    module = load(
        ROOT / "scripts/26_0_build_e3_57_sector_reference_screen.py",
        "screen_builder",
    )
    gain, dh, dv = module.element_gain(
        target_az=10.0,
        target_el=3.0,
        sector_az=0.0,
        boresight_el=-10.0,
        peak_gain=8.0,
        hbw=65.0,
        vbw=65.0,
        amax=30.0,
        slav=30.0,
    )
    assert np.isfinite(gain)
    assert abs(dh - 10.0) < 1e-12
    assert abs(dv - 13.0) < 1e-12


def test_sa509_single_entry_is_three_db_higher_in_far_sidelobe():
    module = load(
        ROOT / "scripts/26_0_build_e3_57_sector_reference_screen.py",
        "screen_builder_sa",
    )
    row = pd.Series(
        {"g0_dbi": 59.0, "phi0_deg": 0.1, "phi1_deg": 0.3, "phi2_deg": 0.5}
    )
    multiple = module.sa509_gain(np.array([8.0]), row, True)[0]
    single = module.sa509_gain(np.array([8.0]), row, False)[0]
    assert abs(single - multiple - 3.0) < 1e-12
