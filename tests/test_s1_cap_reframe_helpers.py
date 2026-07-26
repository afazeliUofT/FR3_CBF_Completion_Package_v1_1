from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "04d_run_s1_cap_reframe.py"
spec = importlib.util.spec_from_file_location("s1_cap_reframe", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_make_grid() -> None:
    grid = module.make_grid(-2.0, 1.0, 0.25, 100)
    assert len(grid) == 13
    assert grid[0] == -2.0
    assert grid[-1] == 1.0


def test_threshold_bracket() -> None:
    candidates = np.array([-2.0, -1.0, 0.0, 1.0])
    passes = np.array([True, True, False, False])
    result = module.threshold_interval(candidates, passes)
    assert result["status"] == "BRACKETED_ON_DECLARED_GRID"
    assert result["highest_passing_candidate_db"] == -1.0
    assert result["first_failing_candidate_db"] == 0.0


def test_threshold_all_and_none() -> None:
    candidates = np.array([-2.0, -1.0])
    assert module.threshold_interval(candidates, np.array([True, True]))["status"] == (
        "ALL_CANDIDATES_PASS_WITHIN_SCREEN_RANGE"
    )
    assert module.threshold_interval(candidates, np.array([False, False]))["status"] == (
        "NO_PASS_WITHIN_SCREEN_RANGE"
    )
