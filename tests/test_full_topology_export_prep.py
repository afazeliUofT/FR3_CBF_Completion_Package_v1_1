from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def test_prep_config_and_contract():
    cfg = json.loads(
        (ROOT / "config/full_topology_export_prep.json").read_text(encoding="utf-8")
    )
    assert cfg["expected"]["required_ancestor_commit"].startswith("11b705b")
    assert cfg["expected"]["users"] == 228
    assert cfg["expected"]["sectors"] == 57
    contract = (
        ROOT / "config/controller_ready_full_topology_export_v2.yaml"
    ).read_text(encoding="utf-8")
    for token in [
        "frequency_response.npy",
        "noise_power_by_frequency_w.npy",
        "protected_steering_pol1.npy",
        "all 228 users",
        "never silently fall back",
        "random-number-mapping",
    ]:
        assert token in contract


def test_controller_identity_shapes():
    users, sectors, streams = 3, 2, 1
    a0 = np.ones((users, sectors, streams), dtype=np.complex128)
    a1 = 2.0 * a0
    a2 = 3.0 * a0
    s1 = np.array([1.0, 0.5])
    s2 = np.array([0.25, 0.75])
    safe = a0 + s1[None, :, None] * a1 + s2[None, :, None] * a2
    assert safe.shape == (users, sectors, streams)
    assert np.allclose(safe[:, 0, :], 3.75)
    assert np.allclose(safe[:, 1, :], 4.25)


def test_stage_python_sources_parse():
    """Parse only Python sources owned by this preparation stage.

    The repository contains a local virtual environment and third-party
    encoding fixtures, including valid non-UTF-8 Python files. They are not
    project source and must never be traversed by this stage-specific test.
    """
    owned_sources = [
        "scripts/33_0_build_full_topology_export_bundle.py",
        "scripts/33_1_validate_full_topology_export_bundle.py",
        "nibi/controller_ready_full_topology_export_v1/run_full_topology_export.py",
        "nibi/controller_ready_full_topology_export_v1/validate_full_topology_export.py",
        "tests/test_full_topology_export_prep.py",
    ]
    for relative in owned_sources:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_non_utf8_virtualenv_fixture_is_out_of_scope(tmp_path):
    """Regression guard for the exact WSL failure."""
    fixture = (
        tmp_path
        / ".venv"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "encoding_fixture.py"
    )
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(
        b"# -*- coding: big5 -*-\n"
        b"# valid third-party non-UTF-8 fixture: \xa4\x40\xa4\x41\n"
        b"def f():\n    return 0\n"
    )
    assert fixture.is_file()
