from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np

from fr3_cbf.dynamic_readiness import (
    minimal_slew_majorant,
    required_common_attenuation_db,
    simulate_myopic_common_command,
    weakest_mode_preservation_scales,
)

ROOT = Path(__file__).resolve().parents[1]


def test_config_lineage():
    cfg = json.loads(
        (ROOT / "config/full_topology_ingest_v4.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["expected"]["source_h100_job_id"] == "18696267"
    assert cfg["expected"]["validation_cpu_job_id"] == "18704028"
    assert len(cfg["expected"]["full_zip_sha256"]) == 64
    assert len(cfg["expected"]["review_zip_sha256"]) == 64


def test_rate_limit_trap_and_majorant():
    required = np.array([4.0, 3.0, 2.0, 2.0, 4.0, 5.5, 5.5])
    bucket, _command, applied = simulate_myopic_common_command(
        required,
        update_interval_s=1,
        delay_intervals=1,
        slew_db_per_update=1.0,
    )
    predictive = minimal_slew_majorant(bucket, 1.0)
    assert np.max(required - applied) > 0.0
    assert np.all(predictive >= bucket - 1e-12)
    assert np.max(np.abs(np.diff(predictive))) <= 1.0 + 1e-12


def test_required_common_attenuation():
    nominal = np.array([10.0, 100.0])
    allowance = np.array([1.0, 1.0])
    assert np.allclose(
        required_common_attenuation_db(nominal, allowance),
        [10.0, 20.0],
    )


def test_weak_mode_preservation_satisfies_allowance():
    contribution = np.arange(1, 115, dtype=float).reshape(57, 2)
    scale = weakest_mode_preservation_scales(
        contribution,
        allowance_w=100.0,
    )
    assert scale.shape == (57, 2)
    assert np.sum(contribution * scale**2) <= 100.0 + 1e-10
    assert np.any(scale == 1.0)
    assert np.any(scale == 0.0)


def test_stage_owned_python_parses():
    owned = [
        "src/fr3_cbf/dynamic_readiness.py",
        "scripts/34_0_ingest_full_topology_export_v4.py",
        "scripts/34_1_validate_full_topology_ingestion.py",
        "scripts/34_2_sync_full_topology_status.py",
        "scripts/34_3_build_full_topology_review_bundle.py",
        "tests/test_full_topology_dynamic_readiness.py",
    ]
    for relative in owned:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
