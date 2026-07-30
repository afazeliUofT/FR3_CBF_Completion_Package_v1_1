from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np

from fr3_cbf.constrained_pf_safety import PriceAllocator, action_grid
from fr3_cbf.robust_delayed_safety import (
    full_horizon_reachability_envelope,
    simulate_full_horizon_predictive,
    theorem_certificate,
)

ROOT = Path(__file__).resolve().parents[1]


def test_config_and_ancestor():
    cfg = json.loads(
        (ROOT / "config/robust_safety_baselines_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["required_ancestor_commit"].startswith("41ec80f")
    assert cfg["primary_scenario"]["message_delay_intervals"] == 1
    assert cfg["primary_scenario"]["slew_db_per_update"] == 3
    assert len(cfg["robust_cases"]) == 4


def test_full_horizon_envelope_recurrence():
    contribution = np.zeros((6, 57, 2), dtype=float)
    contribution[3] = 10.0
    application, command, preload = full_horizon_reachability_envelope(
        contribution,
        delay_intervals=1,
        slew_db_per_update=1.0,
    )
    a = 10.0 ** (-0.1)
    assert np.all(a * application[1:] <= application[:-1] + 1e-15)
    assert np.allclose(command[0], application[1])
    assert np.allclose(preload, application[0])


def test_recursive_certificate_and_message_fail_safe():
    grid = action_grid(0, 60, 1)
    cost = np.zeros((57, len(grid), len(grid)), dtype=float)
    allocator = PriceAllocator(grid, cost, allowance_w=1.0)
    contribution = np.zeros((8, 57, 2), dtype=float)
    contribution[:, :, :] = 0.02
    contribution[4:] *= 2.0
    allowance = np.ones(8)
    run = simulate_full_horizon_predictive(
        allocator,
        contribution,
        allowance,
        delay_intervals=1,
        slew_db_per_update=3.0,
        coupling_upper_margin_db=1.0,
        fail_safe_drop_command_indices=(2, 3),
    )
    certificate = theorem_certificate(
        run,
        allowance,
        slew_db_per_update=3.0,
        maximum_action_db=60.0,
    )
    assert certificate["status"] == (
        "PASS_FINITE_PASS_ROBUST_REACHABILITY_CERTIFICATE"
    )
    assert certificate["fail_safe_use_count"] == 2


def test_stage_owned_python_parses():
    owned = [
        "src/fr3_cbf/robust_delayed_safety.py",
        "scripts/38_0_run_robust_safety_baselines.py",
        "scripts/38_1_validate_robust_safety_baselines.py",
        "scripts/38_2_sync_robust_safety_status.py",
        "scripts/38_3_build_robust_safety_review_bundle.py",
        "tests/test_robust_delayed_safety.py",
    ]
    for relative in owned:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
