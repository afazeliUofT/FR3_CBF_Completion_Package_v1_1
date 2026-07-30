from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np

from fr3_cbf.null_floor_aware_sector_backoff import (
    SectorBackoffPriceAllocator,
    exact_second_ratio,
    interval_sector_envelope,
    power_scale_from_backoff,
)

ROOT = Path(__file__).resolve().parents[1]


def test_config_and_gate() -> None:
    cfg = json.loads(
        (ROOT / "config/sector_selective_backoff_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["required_ancestor_commit"].startswith("d9ebbeb")
    assert cfg["campaign_execution_authorized"] is False
    assert cfg["declared_engineering_envelope"][
        "null_depth_caps_db"
    ] == [60, 65, 67]
    assert cfg["declared_engineering_envelope"][
        "residual_coupling_uplift_db"
    ] == [0, 1, 3]
    assert cfg["fallback"]["exact_sector_mute_endpoint"] is True


def test_power_scale_mute_endpoint() -> None:
    value = power_scale_from_backoff(
        np.array([0.0, 3.0, 10.0, np.inf])
    )
    assert np.isclose(value[0], 1.0)
    assert np.isclose(value[1], 10.0 ** (-0.3))
    assert np.isclose(value[2], 0.1)
    assert value[3] == 0.0


def test_interval_envelope_implies_exact_safety() -> None:
    rng = np.random.default_rng(43001)
    seconds = 12
    interval_s = 5
    intervals = 3
    kappa = rng.uniform(0.1, 2.0, size=(seconds, 57))
    leakage = rng.uniform(0.0, 0.2, size=(intervals, 57, 2))
    allowance = rng.uniform(2.0, 3.0, size=seconds)
    envelope = interval_sector_envelope(
        kappa,
        leakage,
        allowance,
        interval_s,
        coupling_uplift_db=1.0,
    )
    # Scale every interval so the conservative envelope is exactly feasible.
    scale = np.empty((intervals, 57), dtype=float)
    for interval in range(intervals):
        required = max(1.0, float(envelope[interval].sum()))
        scale[interval] = 1.0 / required
    exact = exact_second_ratio(
        kappa,
        leakage,
        scale,
        allowance,
        interval_s,
        coupling_uplift_db=1.0,
    )
    assert np.max(exact) <= 1.0 + 1e-12


def test_price_allocator_uses_mute_and_is_feasible() -> None:
    grid = np.array([0.0, 3.0, 6.0, np.inf])
    allocator = SectorBackoffPriceAllocator(grid)
    cost = np.zeros((57, len(grid)), dtype=float)
    # Backoff carries an increasing local cost; price should still enforce the
    # aggregate envelope and may use the explicit mute endpoint.
    cost[:, 1] = 1.0
    cost[:, 2] = 2.0
    cost[:, 3] = 3.0
    contribution = np.full(57, 0.1, dtype=float)
    backoff, scale, ratio, _price, feasible = allocator.solve(
        cost,
        contribution,
    )
    assert feasible
    assert ratio <= 1.0 + 1e-12
    assert backoff.shape == (57,)
    assert scale.shape == (57,)
    assert np.any(backoff > 0.0)


def test_stage_owned_python_parses() -> None:
    owned = [
        "src/fr3_cbf/null_floor_aware_sector_backoff.py",
        "scripts/43_0_run_sector_selective_backoff.py",
        "scripts/43_1_validate_sector_selective_backoff.py",
        "scripts/43_2_sync_sector_selective_backoff_status.py",
        "scripts/43_3_build_sector_selective_backoff_review_bundle.py",
        "tests/test_sector_selective_backoff.py",
    ]
    for relative in owned:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
