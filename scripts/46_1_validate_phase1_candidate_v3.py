#!/usr/bin/env python3
"""Strict validation of phase-1 candidate v3."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(root: Path, manifest: Path) -> None:
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != expected:
            raise ValueError(f"manifest mismatch: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        default="config/phase1_campaign_contract_v3.json",
    )
    args = parser.parse_args()
    contract = json.loads(
        (ROOT / args.contract).read_text(encoding="utf-8")
    )
    candidate = ROOT / "campaign/phase1_candidate_v3"
    metadata = json.loads(
        (candidate / "CAMPAIGN_METADATA.json").read_text(
            encoding="utf-8"
        )
    )
    review = json.loads(
        (candidate / "INDEPENDENT_REVIEW_STATUS.json").read_text(
            encoding="utf-8"
        )
    )
    provenance = json.loads(
        (candidate / "CANDIDATE_PROVENANCE.json").read_text(
            encoding="utf-8"
        )
    )
    embedded_contract = json.loads(
        (candidate / "PHASE1_CAMPAIGN_CONTRACT_V3.json").read_text(
            encoding="utf-8"
        )
    )

    assert embedded_contract == contract
    assert metadata["status"] == (
        "REVISED_COMPLETE_FIVE_PASS_REVIEW_CANDIDATE_V3_"
        "NOT_AUTHORIZED_FOR_EXECUTION"
    )
    assert metadata["execution_authorized"] is False
    assert metadata["independent_review_status"] == "PENDING_ROUND2"
    assert review["status"] == "PENDING_ROUND2"
    assert review["round1_verdict"] == "REQUIRES_REVISION"
    assert review["execution_authorized"] is False
    assert provenance["candidate_v2_commit"] == (
        "f26af9f3ff595f6b6ae9b468c79683e53bc8b450"
    )

    primary = contract["primary_scenario"]
    assert primary["architecture_id"] == (
        "generic_64t64r_subarray_6bit"
    )
    assert primary["primary_pattern"] == "SA.509_multiple_entry"
    assert primary["declared_engineering_envelope"][
        "null_depth_cap_db"
    ] == 65.0
    assert primary["declared_engineering_envelope"][
        "residual_normalized_coupling_uplift_db"
    ] == 3.0
    assert primary["timing"]["update_interval_s"] == 5
    assert primary["timing"]["command_delay_intervals"] == 1
    assert primary["timing"]["mode_slew_db_per_update"] == 3
    assert primary["timing"]["predictive_horizon"] == (
        "full_remaining_protected_pass"
    )
    assert primary["moving_average_pf"]["inactive_semantics"] == (
        "backlogged_unscheduled_zero_rate_update"
    )
    assert "N_p=ceil(S_p/5)" in primary["load_schedule"][
        "variable_pass_length_rule"
    ]

    method_ids = [
        row["id"] for row in contract["method_contracts"]
    ]
    assert len(method_ids) == 8
    assert len(set(method_ids)) == 8
    assert (
        "delayed_myopic_constrained_pf_with_reactive_sector_fallback"
        in method_ids
    )
    noncausal = [
        row
        for row in contract["method_contracts"]
        if row["class"] == (
            "noncausal_reference_not_primary_comparator"
        )
    ]
    assert len(noncausal) == 1

    statistics = contract["statistics"]
    assert statistics["resampling_unit"] == (
        "channel_topology_seed_cluster"
    )
    assert statistics["bootstrap_resamples"] == 10000
    assert "Do not bootstrap five passes" in statistics[
        "pass_treatment"
    ]
    assert "No imputation" in statistics["missing_run_policy"]
    assert contract["compute_dag"]["channel_generation_jobs"] == 30
    assert contract["compute_dag"][
        "total_controller_evaluations"
    ] == 1200

    pass_slots = metadata["protected_pass_slots"]
    assert len(pass_slots) == 5
    assert all(
        row["status"] == "IMMUTABLE_PASS_RECORD_READY"
        for row in pass_slots
    )

    source_snapshot = candidate / "source_snapshot"
    verify_manifest(
        source_snapshot,
        source_snapshot / "SOURCE_SNAPSHOT_MANIFEST.sha256",
    )
    verify_manifest(
        candidate,
        candidate / "BUNDLE_MANIFEST.sha256",
    )

    output = (
        candidate
        / "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip"
    )
    checksum = Path(str(output) + ".sha256")
    expected = checksum.read_text(encoding="utf-8").split()[0]
    assert sha256_file(output) == expected
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None

    result = subprocess.run(
        ["bash", str(candidate / "RUN_PHASE1_CAMPAIGN.sh")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 64
    assert "not authorized" in result.stdout.lower()

    print("PHASE-1 CANDIDATE V3 STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "status": metadata["status"],
                "round1_verdict": review["round1_verdict"],
                "round2_status": review["status"],
                "pass_slots": len(pass_slots),
                "method_count": len(method_ids),
                "channel_seed_clusters": 30,
                "execution_authorized": False,
                "next_gate": contract["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
