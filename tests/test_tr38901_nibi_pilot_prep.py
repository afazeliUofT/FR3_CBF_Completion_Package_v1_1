from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def test_pilot_dimensions_and_weights():
    cfg = json.loads(
        (ROOT / "config/tr38901_nibi_dlp_pilot_prep.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["expected"]["sector_count"] == 57
    assert cfg["expected"]["users_per_sector"] == 4
    assert cfg["expected"]["user_count"] == 228
    assert cfg["expected"]["array_port_count"] == 128
    weights = np.asarray(cfg["pilot"]["frequency_weights"], dtype=float)
    assert len(weights) == 9
    assert abs(weights.sum() - 1.0) < 1e-15
    assert cfg["pilot"]["protected_frequency_index"] == 4


def test_nibi_source_files_parse():
    for relative in [
        "nibi/dlp_rzf_pilot_v1/run_gpu_pilot.py",
        "nibi/dlp_rzf_pilot_v1/validate_gpu_pilot.py",
        "scripts/31_0_freeze_tr38901_used_subset_mapping.py",
        "scripts/31_1_audit_sionna_dual_pol_port_order.py",
        "scripts/31_2_build_nibi_dlp_pilot_bundle.py",
        "scripts/31_3_sync_pilot_prep_status.py",
    ]:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_dual_pol_budget_accounting_identity():
    nominal = np.array([2.0, 6.0])
    gamma = 4.0
    budgets = gamma * nominal / nominal.sum()
    scales = np.sqrt(budgets / nominal)
    safe = nominal * scales**2
    assert np.allclose(safe, budgets)
    assert abs(safe.sum() - gamma) < 1e-14


def test_panelarray_spacing_keywords_are_sionna_2_api_correct():
    for relative in [
        "scripts/31_1_audit_sionna_dual_pol_port_order.py",
        "nibi/dlp_rzf_pilot_v1/run_gpu_pilot.py",
    ]:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "element_vertical_spacing=0.5" in source
        assert "element_horizontal_spacing=0.5" in source
        assert "\n        vertical_spacing=0.5" not in source
        assert "\n        horizontal_spacing=0.5" not in source


def test_live_api_probe_source_is_packaged():
    source = (
        ROOT / "scripts/31_4_record_sionna_panelarray_api.py"
    ).read_text(encoding="utf-8")
    assert "inspect.signature(PanelArray.__init__)" in source
    assert '"element_vertical_spacing"' in source
    assert '"element_horizontal_spacing"' in source
