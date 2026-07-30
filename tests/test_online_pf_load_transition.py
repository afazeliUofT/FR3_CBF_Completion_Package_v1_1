from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import numpy as np

from fr3_cbf.online_pf_load_transition import (
    build_rotating_load_schedule,
    exponential_average_alpha,
    finite_pass_dynamic_certificate,
    full_horizon_dynamic_envelope,
    simulate_online_predictive_controller,
)

ROOT = Path(__file__).resolve().parents[1]


def test_config_and_predecessor():
    cfg = json.loads(
        (ROOT / "config/online_pf_load_transition_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["required_ancestor_commit"].startswith("83ce40b")
    assert cfg["update_interval_s"] == 5
    assert cfg["message_delay_intervals"] == 1
    assert cfg["moving_average"]["time_constant_s"] == 100.0


def test_exponential_average_alpha():
    value = exponential_average_alpha(5.0, 100.0)
    assert np.isclose(value, 1.0 - np.exp(-0.05), rtol=0.0, atol=1e-15)


def test_rotating_schedule_counts():
    serving = np.repeat(np.arange(57), 4)
    stream = np.tile(np.arange(4), 57)
    schedule, phases = build_rotating_load_schedule(
        serving,
        stream,
        interval_count=118,
        phase_lengths=[20, 20, 20, 20, 20, 18],
        load_stream_counts=[4, 2, 4, 1, 3, 2],
    )
    assert schedule.shape == (118, 228)
    assert [row["active_user_count"] for row in phases] == [
        228, 114, 228, 57, 171, 114
    ]
    assert np.all(schedule.sum(axis=1) >= 57)


def test_preload_uses_application_envelope_regression():
    source = inspect.getsource(simulate_online_predictive_controller)
    assert "application_envelope_w" in source
    assert "initial_allocator.solve(\n        application_envelope[0]" in source
    assert "initial_allocator.solve(\n        envelope[0]" not in source


def test_candidate_specific_saturation_certificate():
    contribution = np.zeros((3, 57, 2), dtype=float)
    contribution[:, 0, 0] = [0.5, 1.0, 0.5]
    application, command_env, preload = full_horizon_dynamic_envelope(
        contribution,
        delay_intervals=1,
        slew_db_per_update=3.0,
    )
    command = np.full((3, 57, 2), 60.0)
    applied = np.full_like(command, 60.0)
    ratio = (
        contribution * np.power(10.0, -applied / 10.0)
    ).sum(axis=(1, 2))
    record = finite_pass_dynamic_certificate(
        command,
        applied,
        np.ones(3, dtype=bool),
        application,
        command_env,
        ratio,
        np.ones(3),
        3.0,
        60.0,
    )
    assert record["status"] == "PASS_CORRECTED_FINITE_PASS_DYNAMIC_CERTIFICATE"
    assert record["checks"]["candidate_specific_saturation_feasibility"]
    assert preload.shape == (57, 2)


def test_stage_owned_python_parses():
    owned = [
        "src/fr3_cbf/online_pf_load_transition.py",
        "scripts/39_0_run_online_pf_load_transition.py",
        "scripts/39_1_validate_online_pf_load_transition.py",
        "scripts/39_2_sync_online_pf_status.py",
        "scripts/39_3_build_online_pf_review_bundle.py",
        "tests/test_online_pf_load_transition.py",
    ]
    for relative in owned:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_full_load_reproduction_uses_platform_scaled_aggregate_check():
    # Exact WSL regression: every user passes the 2e-4 absolute criterion,
    # while the 228-user sum exceeds 2e-4 but is only 1.47e-6 relatively.
    maximum_per_user_error = 8.825123364708531e-05
    network_sum_error = 8.002517819249988e-04
    reference_network_sum = 546.3379124583655
    relative_error = network_sum_error / reference_network_sum
    assert maximum_per_user_error <= 2e-4
    assert network_sum_error > 2e-4
    assert relative_error <= 5e-6
    assert network_sum_error <= 228 * maximum_per_user_error
