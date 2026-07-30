from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np

from fr3_cbf.physical_impairment_sensitivity import (
    mode_leakage,
    quantize_precoder_phase,
    required_uniform_backoff_db,
)

ROOT = Path(__file__).resolve().parents[1]


def test_config_gate_and_campaign_not_authorized():
    cfg = json.loads((ROOT / "config/physical_impairment_sensitivity_v1.json").read_text(encoding="utf-8"))
    assert cfg["required_ancestor_commit"].startswith("6515d52")
    campaign = json.loads((ROOT / "config/phased_campaign_spec_v2.json").read_text(encoding="utf-8"))
    assert campaign["execution_authorized"] is False


def test_backoff_formula():
    assert np.isclose(required_uniform_backoff_db(10.0), 10.0)
    assert required_uniform_backoff_db(0.5) == 0.0


def test_phase_quantization_and_leakage_shapes():
    rng = np.random.default_rng(42)
    w = rng.normal(size=(57,128,4)) + 1j*rng.normal(size=(57,128,4))
    s1 = np.zeros((57,128), dtype=complex); s1[:,:64] = 1.0
    s2 = np.zeros((57,128), dtype=complex); s2[:,64:] = 1.0
    q = quantize_precoder_phase(w, 8)
    leakage = mode_leakage(q, s1, s2)
    assert q.shape == w.shape
    assert leakage.shape == (57,2)
    assert np.all(leakage >= 0)


def test_stage_owned_python_parses():
    for relative in [
        "src/fr3_cbf/physical_impairment_sensitivity.py",
        "scripts/42_0_run_physical_impairment_sensitivity.py",
        "scripts/42_1_validate_physical_impairment_sensitivity.py",
        "scripts/42_2_sync_physical_impairment_status.py",
        "scripts/42_3_build_physical_impairment_review_bundle.py",
        "tests/test_physical_impairment_sensitivity.py",
    ]:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
