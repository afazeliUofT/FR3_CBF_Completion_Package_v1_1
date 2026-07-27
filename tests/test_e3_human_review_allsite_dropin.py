from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sa509_far_sidelobe():
    mod = load_module(
        ROOT / "scripts/24_6_independent_review_e3_first_sector.py",
        "review_mod",
    )
    row = pd.Series(
        {
            "g0_dbi": 59.0,
            "phi0_deg": 0.1,
            "phi1_deg": 0.25,
            "phi2_deg": 0.4,
        }
    )
    phi = np.array([8.0])
    multiple = mod.sa509_gain(phi, row, True)[0]
    single = mod.sa509_gain(phi, row, False)[0]
    assert abs(multiple - (29 - 25 * np.log10(8))) < 1e-12
    assert abs(single - multiple - 3.0) < 1e-12


def test_package_files_exist():
    for rel in [
        "scripts/24_6_independent_review_e3_first_sector.py",
        "scripts/24_7_prepare_e3_all_site_links.py",
        "scripts/24_8_validate_e3_all_site_terrain.py",
        "RUN_E3_ONE_SECTOR_REVIEW_AND_ALL_SITE_TERRAIN_DROPIN.sh",
    ]:
        assert (ROOT / rel).is_file()
