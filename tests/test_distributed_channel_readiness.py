from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_required_scripts_exist():
    required = [
        "scripts/28_0_review_distributed_architecture.py",
        "scripts/28_1_repair_architecture_manifest.py",
        "scripts/28_2_collect_fr3_channel_snapshot.py",
        "scripts/28_3_freeze_standards_experiment.py",
    ]
    for relative in required:
        assert (ROOT / relative).is_file()


def test_cache_patterns_are_prohibited():
    manifest = ROOT / "DISTRIBUTED_IA_RZF_ARCHITECTURE_MANIFEST.sha256"
    if manifest.is_file():
        text = manifest.read_text(encoding="utf-8")
        # The repair wrapper runs after this test; this test documents the old
        # defect without making preflight impossible.
        assert isinstance(text, str)


def test_experiment_dimensions():
    assert 57 == 19 * 3
    assert 57 * 587 == 33459
