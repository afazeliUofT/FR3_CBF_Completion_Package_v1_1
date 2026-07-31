from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fr3_cbf.phase1_job_runtime import EvaluatedRun, summarize_method


def test_builder_contract_dimensions():
    cfg = json.loads(
        (
            ROOT / "config/phase1_nibi_job_package_builder_v1.json"
        ).read_text(encoding="utf-8")
    )
    seeds = cfg["channel_seed_mapping"]["campaign_seed_list"]
    assert seeds == list(range(44000, 44030))
    assert cfg["nibi_resource_template"]["array"] == "0-29%8"
    assert cfg["execution_authorized"] is False
    assert cfg["required_ancestor_commit"].startswith("9f3c6ff")
    source = cfg["full_topology_source_bundle"]
    assert source["source_commit"].startswith("3080058")
    assert source["sha256"] == (
        "206c8cc7aa18c3616f70fba6c56b72af8a76267b59f9f446baa019dede0085b5"
    )
    assert len(source["expected_input_sha256"]) == 15


def test_runtime_summarizes_primary_endpoint():
    k = 2
    eligible = np.ones(228, dtype=bool)
    moving = np.full((k, 228), 1.0)
    delivered = np.full((k, 228), 1.0)
    run = EvaluatedRun(
        method_id="synthetic",
        q_db=np.zeros((k, 57, 2)),
        sector_power_scale=np.ones((k, 57)),
        long_ratio=np.full(10, 0.5),
        short_ratio=np.full(10, 0.4),
        delivered_total_rate=delivered,
        delivered_protected_rate=delivered,
        moving_average_rate=moving,
        floor_violation_count=np.zeros(k, dtype=np.int64),
        normalized_shortfall=np.zeros(k),
        sector_backoff_db=np.zeros((k, 57)),
        local_table_build_seconds=np.zeros(k),
        runtime_seconds=1.0,
        extra={},
    )
    summary = summarize_method(run, eligible, np.array([5, 5]))
    expected = float(228 * np.log(1.001))
    assert np.isclose(summary["final_moving_pf_utility"], expected)
    assert np.isclose(
        summary["duration_weighted_mean_moving_pf_utility"], expected
    )
    assert summary["long_violation_seconds"] == 0


def test_reactive_myopic_and_eight_methods_are_present():
    text = (
        ROOT / "src/fr3_cbf/phase1_job_runtime.py"
    ).read_text(encoding="utf-8")
    assert (
        "delayed_myopic_constrained_pf_with_reactive_sector_fallback"
        in text
    )
    assert text.count("methods[") >= 8
    worker = (
        ROOT
        / "job_templates/phase1_nibi_v1/phase1_seed_worker.py"
    ).read_text(encoding="utf-8")
    assert "METHOD_IDS = [" in worker
    assert "run_phase1_methods" in worker
    assert "generate_full_channel" in worker
    assert "CAMPAIGN_METADATA.json" not in worker


def test_submission_templates_are_locked():
    for name in [
        "RUN_PHASE1_NIBI_CAMPAIGN.sh",
        "SUBMIT_PHASE1_LOCKED.sh",
        "MERGE_PHASE1_LOCKED.sh",
    ]:
        path = ROOT / "job_templates/phase1_nibi_v1" / name
        result = subprocess.run(
            ["bash", str(path)], capture_output=True, text=True
        )
        assert result.returncode == 64


def test_builder_rehydrates_reviewed_source_bundle():
    builder = (
        ROOT / "scripts/48_0_build_phase1_nibi_job_package.py"
    ).read_text(encoding="utf-8")
    assert "full_topology_source_bundle" in builder
    assert "TemporaryDirectory" in builder
    assert "FULL_TOPOLOGY_SOURCE_BUNDLE_BINDING.json" in builder
    assert 'copy_tree(exporter / "input"' not in builder
    preflight = (
        ROOT / "wrappers/phase1_nibi_job_package/00_preflight.sh"
    ).read_text(encoding="utf-8")
    assert "REVIEWED FULL-TOPOLOGY SOURCE BUNDLE PREFLIGHT" in preflight
    assert "exporter input directory is missing" not in preflight


def test_owned_sources_parse():
    for path in ROOT.rglob("*.py"):
        if "job_templates" in path.parts or path.parts[-2] in {
            "scripts",
            "tests",
        } or "src" in path.parts:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
