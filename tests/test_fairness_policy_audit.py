from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_config_is_not_sum_rate():
    cfg = json.loads(
        (ROOT / "config/fairness_policy_audit_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["required_ancestor_commit"].startswith("ec0ac88")
    assert cfg["primary_policy"]["name"] == (
        "constrained_proportional_fairness"
    )
    assert cfg["primary_policy"][
        "relative_total_band_floor_fraction"
    ] == 0.9
    assert cfg["primary_policy"]["indoor_weight"] == 1.0
    assert cfg["primary_policy"]["outdoor_weight"] == 1.0


def test_stage_owned_python_parses():
    owned = [
        "scripts/36_0_run_fairness_policy_audit.py",
        "scripts/36_1_validate_fairness_policy_audit.py",
        "scripts/36_2_sync_fairness_policy_status.py",
        "scripts/36_3_build_fairness_review_bundle.py",
        "tests/test_fairness_policy_audit.py",
    ]
    for relative in owned:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
