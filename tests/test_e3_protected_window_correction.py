from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_angular_separation_identical_direction_is_zero():
    module = load_script(
        "protected_summary",
        "scripts/23_3_rebuild_e3_protected_off_axis.py",
    )
    value = module.angular_separation_deg(
        np.array([190.0]),
        np.array([5.0]),
        190.0,
        5.0,
    )[0]
    assert abs(value) < 1e-6


def test_sa509_nominal_gain_at_known_off_axis():
    module = load_script(
        "protected_summary_gain",
        "scripts/23_3_rebuild_e3_protected_off_axis.py",
    )
    params = pd.Series(
        {
            "g0_dbi": 59.037736182688946,
            "phi0_deg": 0.0980190219880998,
            "phi1_deg": 0.2530837261604178,
            "phi2_deg": 0.3967255956482239,
        }
    )
    angle = np.array([8.035691596201232])
    gain = module.sa509_gain(angle, params, multiple_entry=True)[0]
    expected = 29.0 - 25.0 * math.log10(angle[0])
    assert abs(gain - expected) < 1e-12


def test_patch_text_contains_protected_filter():
    module = load_script(
        "source_patcher",
        "scripts/23_2_apply_protected_window_patch.py",
    )
    assert "protected_mask" in module.NEW
    assert "minimum_elevation_deg" in module.NEW
    assert "selected_pass_off_axis_summary_protected.csv" in module.NEW
    assert "track[\"azimuth_deg\"]" in module.OLD
