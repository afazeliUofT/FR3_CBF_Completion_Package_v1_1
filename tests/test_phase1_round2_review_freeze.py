from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def review() -> dict:
    return json.loads(
        (
            ROOT / "config/phase1_candidate_v3_round2_review_v1.json"
        ).read_text(encoding="utf-8")
    )


def test_verdict_and_execution_boundary():
    value = review()
    assert value["round2_verdict"] == (
        "PASS_FOR_IMMUTABLE_JOB_PACKAGE_PREPARATION_NOT_EXECUTION"
    )
    assert value["campaign_execution_authorized"] is False
    assert value["candidate_commit"].startswith("be9053d")
    assert len(value["mandatory_job_package_gates"]) >= 6


def test_candidate_hashes():
    value = review()
    assert len(value["candidate_zip_sha256"]) == 64
    assert len(value["review_prep_zip_sha256"]) == 64
    assert value["candidate_zip_sha256"] == (
        "f7b47fd3a07e30987b7f0901df1706d6127774d32284e7d3b0da38185d810161"
    )


def test_source_files_parse():
    for relative in [
        "scripts/47_0_verify_freeze_round2_review.py",
        "scripts/47_1_validate_round2_review_freeze.py",
        "scripts/47_2_sync_round2_review_status.py",
        "scripts/47_3_build_round2_review_bundle.py",
        "tests/test_phase1_round2_review_freeze.py",
    ]:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
