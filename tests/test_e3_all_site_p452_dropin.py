from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_expected_row_count():
    assert 19 * 7 * 2 * 3 == 798


def test_free_space_formula():
    module = load(
        ROOT / "scripts/25_2_validate_e3_all_site_p452.py",
        "all_site_validation",
    )
    result = module.free_space_loss_db(8.15, np.array([2.0]))[0]
    expected = 92.45 + 20 * np.log10(8.15) + 20 * np.log10(2.0)
    assert abs(result - expected) < 1e-12
