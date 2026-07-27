from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def test_config_is_local_first_and_narval_only():
    cfg = json.loads(
        (ROOT / "config/tr38901_narval_dlp_pilot_prep.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["narval"]["host"] == "narval.alliancecan.ca"
    assert cfg["narval"]["gpus_per_node"] == "a100:1"
    assert cfg["narval"]["cpus_per_task"] == 12
    assert cfg["narval"]["memory"] == "124G"
    assert cfg["pilot"]["channel_user_chunk_size"] == 8
    assert cfg["superseded_nibi_bundle"]["disposition"] == "DO_NOT_RUN"


def test_pilot_dimensions_and_weights():
    cfg = json.loads(
        (ROOT / "config/tr38901_narval_dlp_pilot_prep.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["expected"]["sector_count"] == 57
    assert cfg["expected"]["user_count"] == 228
    assert cfg["expected"]["array_port_count"] == 128
    weights = np.asarray(cfg["pilot"]["frequency_weights"], dtype=float)
    assert len(weights) == 9
    assert abs(weights.sum() - 1.0) < 1e-15


def test_narval_runtime_source_is_a100_and_chunked():
    source = (
        ROOT / "narval/dlp_rzf_pilot_v1/run_gpu_pilot.py"
    ).read_text(encoding="utf-8")
    assert '"A100"' in source
    assert "38 * 1024**3" in source
    assert "channel_user_chunk_size" in source
    assert "coefficients_chunk_stream_sha256" in source
    assert "torch.exp(-1j * phase)" in source


def test_narval_master_requests_recommended_bundle():
    source = (
        ROOT / "narval/dlp_rzf_pilot_v1/"
        "RUN_NARVAL_ONE_SEED_DLP_RZF_PILOT.sh"
    ).read_text(encoding="utf-8")
    assert "--gpus-per-node=a100:1" in source
    assert "--cpus-per-task=12" in source
    assert "--mem=124G" in source
    assert "cluster=narval" in source
    assert "fr3-dlp-narval" in source


def test_packaged_python_sources_parse():
    # Parse only the Python sources installed by this drop-in. Scanning the
    # whole repository would incorrectly traverse the project's .venv and
    # third-party Python test fixtures that intentionally use non-UTF-8 source
    # encodings (for example Big5). Those files are outside this package's
    # audit scope.
    relative_paths = [
        "scripts/31_1_audit_sionna_dual_pol_port_order.py",
        "scripts/31_2_build_narval_dlp_pilot_bundle.py",
        "scripts/31_4_record_sionna_panelarray_api.py",
        "scripts/31_5_audit_sionna_incumbent_local_frame.py",
        "scripts/31_6_validate_narval_bundle_source.py",
        "narval/dlp_rzf_pilot_v1/run_gpu_pilot.py",
        "narval/dlp_rzf_pilot_v1/validate_gpu_pilot.py",
        "tests/test_tr38901_narval_pilot_prep.py",
    ]
    for relative in relative_paths:
        path = ROOT / relative
        assert path.is_file(), relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
