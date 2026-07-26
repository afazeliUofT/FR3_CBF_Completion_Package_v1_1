from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "21_0_prepare_p452_pilot.py"
SPEC = importlib.util.spec_from_file_location("p452_pilot_prepare_pol", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_tafl_a_maps_to_horizontal() -> None:
    plan = MODULE.parse_polarization_plan("A", "A", None)
    assert plan["p452_codes"] == [1]
    assert plan["p452_labels"] == ["H"]
    assert plan["tafl_description"] == "Horizontal"


def test_tafl_b_maps_to_vertical() -> None:
    plan = MODULE.parse_polarization_plan("B", "B", None)
    assert plan["p452_codes"] == [2]
    assert plan["p452_labels"] == ["V"]
    assert plan["tafl_description"] == "Vertical"


def test_tafl_g_evaluates_both_without_aggregation() -> None:
    plan = MODULE.parse_polarization_plan("G", "G", None)
    assert plan["p452_codes"] == [1, 2]
    assert plan["p452_labels"] == ["H", "V"]
    assert plan["mode"] == "tafl_cochannel_dual_evaluate_both"
    assert plan["aggregation"] == "none_pipeline_exports_each_branch"
    assert plan["tafl_description"] == "Co-channel dual polarization"


def test_elliptical_h_is_not_misread_as_horizontal() -> None:
    with pytest.raises(ValueError, match="Elliptical"):
        MODULE.parse_polarization_plan("H", "H", None)


def test_mismatched_endpoint_codes_are_rejected() -> None:
    with pytest.raises(ValueError, match="do not match"):
        MODULE.parse_polarization_plan("G", "A", None)


def test_documented_override_is_explicit() -> None:
    plan = MODULE.parse_polarization_plan("G", "G", "V")
    assert plan["p452_codes"] == [2]
    assert plan["p452_labels"] == ["V"]
    assert plan["mode"] == "documented_override_vertical"
