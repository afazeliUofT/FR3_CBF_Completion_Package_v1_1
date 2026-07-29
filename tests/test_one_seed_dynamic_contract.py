from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np

from fr3_cbf.physical_accounting import (
    apply_mode_scales,
    attenuation_db_to_amplitude_scale,
    rotation_matrix_zyx,
    steering_column_from_local_direction,
    user_rates_from_amplitudes,
    world_to_local_direction,
)

ROOT = Path(__file__).resolve().parents[1]


def test_freeze_config_hashes_and_counts():
    cfg = json.loads(
        (ROOT / "config/one_seed_18658301_freeze.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["expected"]["job_id"] == "18658301"
    assert cfg["expected"]["sectors"] == 57
    assert cfg["expected"]["users"] == 228
    assert cfg["expected"]["sector_time_rows"] == 33459
    assert len(cfg["expected"]["review_zip_sha256"]) == 64


def test_rotation_round_trip():
    world = np.array([0.2, 0.9, 0.3])
    yaw, pitch, roll = 0.7, 0.15, -0.04
    local = world_to_local_direction(world, yaw, pitch, roll)
    rotation = rotation_matrix_zyx(yaw, pitch, roll)
    reconstructed = rotation @ local
    reconstructed /= np.linalg.norm(reconstructed)
    world /= np.linalg.norm(world)
    assert np.allclose(reconstructed, world, atol=1e-12)


def test_negative_steering_column_convention():
    positions = np.array([[0.0, 0.0, 0.0], [0.0, 0.5, 0.0]])
    direction = np.array([0.0, 1.0, 0.0])
    carrier = 299_792_458.0
    value = steering_column_from_local_direction(
        positions, direction, carrier
    )
    assert np.allclose(value[0], 1.0 + 0.0j)
    assert np.allclose(value[1], -1.0 + 0.0j, atol=1e-12)


def test_full_inter_cell_rate_helper():
    amplitudes = np.zeros((2, 2, 1), dtype=np.complex128)
    amplitudes[0, 0, 0] = 2.0
    amplitudes[0, 1, 0] = 1.0
    amplitudes[1, 0, 0] = 0.5
    amplitudes[1, 1, 0] = 3.0
    rates = user_rates_from_amplitudes(
        amplitudes,
        np.array([0, 1]),
        np.array([0, 0]),
        noise_power_w=1.0,
    )
    assert np.allclose(
        rates,
        [
            np.log2(1.0 + 4.0 / 2.0),
            np.log2(1.0 + 9.0 / 1.25),
        ],
    )


def test_mode_scale_application():
    a0 = np.ones((2, 3, 1), dtype=np.complex128)
    a1 = 2.0 * np.ones_like(a0)
    a2 = 3.0 * np.ones_like(a0)
    s1 = attenuation_db_to_amplitude_scale(np.array([0.0, 20.0, 40.0]))
    s2 = np.ones(3)
    result = apply_mode_scales(a0, a1, a2, s1, s2)
    assert result.shape == (2, 3, 1)
    assert np.allclose(result[:, 0, :], 6.0)
    assert np.allclose(result[:, 1, :], 4.2)


def test_contracts_contain_decisive_gates():
    dynamic = (
        ROOT / "config/dynamic_safety_experiment_v1.yaml"
    ).read_text(encoding="utf-8")
    export = (
        ROOT / "config/controller_ready_full_topology_export_v1.yaml"
    ).read_text(encoding="utf-8")
    for token in [
        "predictive_cbf",
        "myopic_utility_safety",
        "attenuation_slew_db_per_update",
        "hidden_emergency_slack: prohibited",
    ]:
        assert token in dynamic
    for token in [
        "all 228 users",
        "protected_amp_perpendicular.npy",
        "kappa_time_sector.npy",
        "never silently fall back",
    ]:
        assert token in export


def test_installed_stage_python_parses():
    for relative in [
        "scripts/32_0_freeze_nibi_one_seed_18658301.py",
        "scripts/32_1_validate_one_seed_18658301_freeze.py",
        "scripts/32_2_sync_status_and_contract.py",
        "scripts/32_3_build_one_seed_review_bundle.py",
        "src/fr3_cbf/physical_accounting.py",
    ]:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
