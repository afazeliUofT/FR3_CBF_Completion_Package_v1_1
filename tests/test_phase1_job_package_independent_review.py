from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def review() -> dict:
    return json.loads(
        (
            ROOT
            / "config/phase1_nibi_job_package_independent_review_v1.json"
        ).read_text(encoding="utf-8")
    )


def test_review_binding_and_scope():
    value = review()
    assert value["reviewed_commit"] == (
        "20d65eeb0fcc53f649a4f3f716fa2780406b4810"
    )
    assert value["reviewed_package_id"] == (
        "bd18734787de7396b9de4bf8c0b9ba4d191c6346a7cb83e969499622067a8129"
    )
    assert value["verdict"] == (
        "PASS_FOR_NIBI_DEPLOYMENT_SMOKE_PREPARATION_"
        "NOT_FULL_CAMPAIGN_EXECUTION"
    )
    assert value["campaign_execution_authorized"] is False
    assert value["full_30_seed_execution_authorized"] is False


def test_required_smoke_and_campaign_gates():
    value = review()
    assert len(value["mandatory_before_noncampaign_nibi_smoke"]) >= 5
    assert len(value["mandatory_before_full_30_seed_execution"]) >= 6
    assert value["next_gate"] == (
        "BUILD_REVIEW_AND_RUN_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE"
    )


def test_smoke_scientific_record():
    smoke = review()["scientific_smoke"]
    assert smoke["predictive_long_violation_seconds"] == 0
    assert smoke["predictive_floor_violation_user_seconds"] == 0
    assert smoke["reactive_myopic_long_violation_seconds"] == 0
    assert smoke["unshielded_myopic_long_violation_seconds"] > 0
    assert smoke["virtual_queue_long_violation_seconds"] > 0
    assert smoke["predictive_minus_static_final_pf"] > 0


def test_stage_owned_python_parses():
    for relative in [
        "scripts/49_0_verify_freeze_phase1_job_package_review.py",
        "scripts/49_1_validate_phase1_job_package_independent_review.py",
        "scripts/49_2_sync_phase1_job_package_review_status.py",
        "scripts/49_3_build_phase1_job_package_review_freeze_bundle.py",
        "tests/test_phase1_job_package_independent_review.py",
    ]:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

def test_worker_semantic_contract_is_linewrap_independent():
    path = (
        ROOT
        / "campaign/phase1_nibi_job_package_v1/phase1_seed_worker.py"
    )
    normalized = " ".join(path.read_text(encoding="utf-8").split())
    assert "one cellular channel/topology realization" in normalized
    assert "def generate_channel(" in normalized
    assert (
        "delayed_myopic_constrained_pf_with_reactive_sector_fallback"
        in normalized
    )
    assert "for slot, pass_root in enumerate(pass_roots):" in normalized
