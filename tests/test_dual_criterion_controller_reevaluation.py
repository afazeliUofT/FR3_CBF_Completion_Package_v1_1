from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np

from fr3_cbf.dual_criterion_controller import (
    common_scale_action,
    interval_reduce,
    normalized_short_to_long_ratio,
)

ROOT = Path(__file__).resolve().parents[1]


def test_config_lineage_and_grid():
    cfg = json.loads(
        (
            ROOT
            / "config/dual_criterion_controller_reevaluation_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert cfg["required_ancestor_commit"].startswith("2d4e210")
    assert cfg["action_grid"]["maximum_db"] == 70
    assert cfg["action_grid"]["hard_null_endpoint"] is True
    assert set(cfg["criteria"]) == {
        "short_multiple",
        "long_multiple",
        "short_single",
        "long_single",
    }


def test_interval_reduction():
    values = np.arange(14, dtype=float).reshape(7, 2)
    maximum, lengths = interval_reduce(values, 3, "max")
    minimum, minimum_lengths = interval_reduce(values, 3, "min")
    assert np.array_equal(lengths, [3, 3, 1])
    assert np.array_equal(lengths, minimum_lengths)
    assert np.array_equal(maximum[0], [4.0, 5.0])
    assert np.array_equal(minimum[1], [6.0, 7.0])


def test_common_scale_action_is_exact_for_scalar_sum():
    contribution = np.ones((2, 57, 2), dtype=float)
    allowance = np.array([114.0, 11.4])
    action = common_scale_action(contribution, allowance)
    ratio = (
        contribution * np.power(10.0, -action / 10.0)
    ).sum(axis=(1, 2)) / allowance
    assert np.allclose(ratio, 1.0, rtol=1e-12, atol=1e-12)


def test_long_constraint_dominance_helper():
    short_kappa = np.ones((3, 57)) * 2.0
    long_kappa = np.ones((3, 57))
    short_allowance = np.ones(3) * 10.0
    long_allowance = np.ones(3)
    ratio = normalized_short_to_long_ratio(
        short_kappa,
        short_allowance,
        long_kappa,
        long_allowance,
    )
    assert np.allclose(ratio, 0.2)
    assert np.all(ratio < 1.0)


def test_stage_owned_python_parses():
    owned = [
        "src/fr3_cbf/dual_criterion_controller.py",
        "scripts/41_0_run_dual_criterion_controller_reevaluation.py",
        "scripts/41_1_validate_dual_criterion_controller_reevaluation.py",
        "scripts/41_2_sync_dual_criterion_controller_status.py",
        "scripts/41_3_build_dual_criterion_controller_review_bundle.py",
        "tests/test_dual_criterion_controller_reevaluation.py",
    ]
    for relative in owned:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
