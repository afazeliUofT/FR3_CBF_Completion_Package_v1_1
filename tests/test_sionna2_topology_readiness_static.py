from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_adapter_counts():
    cfg = json.loads(
        (ROOT / "config/sionna2_topology_readiness.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["expected"]["site_count"] == 19
    assert cfg["expected"]["sector_count"] == 57
    assert cfg["expected"]["adapter_user_count"] == 57


def test_geographic_to_sionna_yaw_convention():
    # North=0 degrees -> Sionna +x yaw=pi/2.
    assert abs(np.deg2rad((90.0 - 0.0) % 360.0) - np.pi / 2) < 1e-15
    # East=90 degrees -> Sionna +x yaw=0.
    assert abs(np.deg2rad((90.0 - 90.0) % 360.0)) < 1e-15


def test_energy_weighted_delay_ignores_negligible_raw_outlier():
    module = load(
        ROOT / "scripts/30_0_audit_sionna2_delay_and_source.py",
        "delay_audit_module",
    )
    coefficients = np.zeros((1, 1, 1, 1, 1, 2, 1), dtype=np.complex64)
    coefficients[..., 0, :] = 1.0
    coefficients[..., 1, :] = 1e-10
    delays = np.array([[[[1e-7, 4.0]]]], dtype=np.float32)
    summary, _links, _outliers = module.delay_metrics(
        "synthetic",
        coefficients,
        delays,
        relative_floor=1e-12,
        cumulative_fraction=0.999999999,
        raw_outlier_threshold=1e-3,
    )
    assert summary["raw_max_delay_s"] > 1.0
    assert summary["maximum_energy_support_delay_s"] < 1e-6
