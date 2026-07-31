from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def contract() -> dict:
    return json.loads(
        (
            ROOT / "config/phase1_campaign_contract_v3.json"
        ).read_text(encoding="utf-8")
    )


def test_unique_primary_scenario():
    value = contract()
    primary = value["primary_scenario"]
    assert primary["architecture_id"] == "generic_64t64r_subarray_6bit"
    assert primary["primary_pattern"] == "SA.509_multiple_entry"
    assert primary["declared_engineering_envelope"][
        "null_depth_cap_db"
    ] == 65.0
    assert primary["declared_engineering_envelope"][
        "residual_normalized_coupling_uplift_db"
    ] == 3.0


def test_method_classes_and_reactive_myopic():
    methods = contract()["method_contracts"]
    ids = {row["id"] for row in methods}
    assert len(methods) == 8
    assert (
        "delayed_myopic_constrained_pf_with_reactive_sector_fallback"
        in ids
    )
    assert sum(
        row["class"] == "primary_safe_comparator"
        for row in methods
    ) == 1
    assert sum(
        row["class"] == "noncausal_reference_not_primary_comparator"
        for row in methods
    ) == 1


def test_statistics_treat_passes_as_fixed_blocks():
    statistics = contract()["statistics"]
    assert statistics["resampling_unit"] == (
        "channel_topology_seed_cluster"
    )
    assert statistics["bootstrap_resamples"] == 10000
    assert "Do not bootstrap five passes" in statistics[
        "pass_treatment"
    ]
    assert "No imputation" in statistics["missing_run_policy"]


def test_variable_pass_length_rule_and_compute_dag():
    value = contract()
    assert "N_p=ceil(S_p/5)" in value["primary_scenario"][
        "load_schedule"
    ]["variable_pass_length_rule"]
    assert value["compute_dag"]["channel_generation_jobs"] == 30
    assert value["compute_dag"][
        "total_controller_evaluations"
    ] == 1200


def test_stage_owned_python_parses():
    for relative in [
        "scripts/46_0_build_phase1_candidate_v3.py",
        "scripts/46_1_validate_phase1_candidate_v3.py",
        "scripts/46_2_sync_phase1_candidate_review_status.py",
        "scripts/46_3_build_phase1_candidate_v3_review_bundle.py",
        "tests/test_phase1_candidate_v3_contract.py",
    ]:
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
