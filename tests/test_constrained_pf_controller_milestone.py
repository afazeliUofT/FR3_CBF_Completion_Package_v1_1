from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np

from fr3_cbf.constrained_pf_safety import (
    PriceAllocator,
    action_grid,
    predictive_effective_contribution,
)

ROOT = Path(__file__).resolve().parents[1]


def test_config_and_policy():
    cfg = json.loads(
        (
            ROOT
            / "config/constrained_pf_controller_milestone_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert cfg["required_ancestor_commit"].startswith("2ca450f")
    assert cfg["policy"]["serviceability_threshold_bps_hz"] == 0.1
    assert cfg["policy"]["relative_total_band_floor_fraction"] == 0.9
    assert cfg["primary_scenario"]["update_interval_s"] == 5
    assert cfg["primary_scenario"]["message_delay_intervals"] == 1
    assert cfg["primary_scenario"]["slew_db_per_update"] == 3


def test_price_allocator_can_find_safe_action():
    q = action_grid(0, 30, 1)
    cost = np.zeros((57, len(q), len(q)), dtype=float)
    for index, value in enumerate(q):
        cost[:, index, :] += value
        cost[:, :, index] += value
    allocator = PriceAllocator(q, cost, allowance_w=1.0)
    contribution = np.full((57, 2), 0.02)
    action, ratio, feasible, _price = allocator.solve(contribution)
    assert feasible
    assert ratio <= 1.0 + 1e-12
    assert action.shape == (57, 2)


def test_predictive_envelope_matches_reachability():
    contribution = np.zeros((6, 57, 2))
    contribution[3] = 10.0
    effective = predictive_effective_contribution(
        contribution,
        command_index=0,
        delay_intervals=1,
        slew_db_per_update=1.0,
        horizon_intervals=4,
    )
    assert np.allclose(
        effective,
        10.0 * 10.0 ** (-0.2),
    )


def test_stage_owned_python_parses():
    owned = [
        "src/fr3_cbf/constrained_pf_safety.py",
        "scripts/37_0_run_constrained_pf_controller_milestone.py",
        "scripts/37_1_validate_constrained_pf_controller_milestone.py",
        "scripts/37_2_sync_constrained_pf_controller_status.py",
        "scripts/37_3_build_constrained_pf_controller_review_bundle.py",
        "tests/test_constrained_pf_controller_milestone.py",
    ]
    for relative in owned:
        path = ROOT / relative
        ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
