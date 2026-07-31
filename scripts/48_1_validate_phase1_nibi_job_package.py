#!/usr/bin/env python3
"""Strict local validation of the immutable phase-1 Nibi job package."""
from __future__ import annotations

import argparse
import ast
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


def verify_text_manifest(root: Path, manifest: Path) -> int:
    count = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != expected:
            raise ValueError(f"manifest mismatch: {relative}")
        count += 1
    return count


def expected_lock(path: Path) -> None:
    result = subprocess.run(
        ["bash", str(path)], capture_output=True, text=True
    )
    if result.returncode != 64:
        raise RuntimeError(
            f"execution lock {path.name} returned {result.returncode}"
        )
    if "locked" not in result.stdout.lower() and (
        "not authorized" not in result.stdout.lower()
    ):
        raise RuntimeError(f"execution lock text is wrong: {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/phase1_nibi_job_package_builder_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    package = ROOT / cfg["paths"]["job_package_dir"]

    required = [
        "JOB_PACKAGE_CONTRACT.json",
        "PHASE1_CAMPAIGN_CONTRACT_V3.json",
        "PHASE1_ROUND2_REVIEW_VERDICT.json",
        "CANDIDATE_AND_REVIEW_BINDING.json",
        "PACKAGE_ID.txt",
        "AUTHORIZATION_TOKEN_TEMPLATE.json",
        "NEW_JOB_SOURCE_MANIFEST.sha256",
        "NEW_JOB_SOURCE_RECORD.json",
        "PACKAGE_MANIFEST.sha256",
        "FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip",
        "FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip.sha256",
        "phase1_seed_worker.py",
        "validate_seed_result.py",
        "merge_phase1_results.py",
        "validate_merged_results.py",
        "setup_environment.sh",
        "phase1_array_worker.sh",
        "RUN_PHASE1_NIBI_CAMPAIGN.sh",
        "SUBMIT_PHASE1_LOCKED.sh",
        "MERGE_PHASE1_LOCKED.sh",
        "RESULT_SCHEMA.json",
        "src/fr3_cbf/phase1_job_runtime.py",
        "channel_generator/run_full_topology_export.py",
        "channel_generator/export_config_base.json",
        "channel_generator/source_bundle_provenance/BUNDLE_METADATA.json",
        "channel_generator/source_bundle_provenance/BUNDLE_MANIFEST.sha256",
        "channel_generator/source_bundle_provenance/FULL_TOPOLOGY_SOURCE_BUNDLE_BINDING.json",
    ]
    for name in required:
        if not (package / name).is_file():
            raise FileNotFoundError(package / name)

    contract = json.loads(
        (package / "JOB_PACKAGE_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    campaign = json.loads(
        (package / "PHASE1_CAMPAIGN_CONTRACT_V3.json").read_text(
            encoding="utf-8"
        )
    )
    review = json.loads(
        (package / "PHASE1_ROUND2_REVIEW_VERDICT.json").read_text(
            encoding="utf-8"
        )
    )
    if contract["status"] != (
        "IMMUTABLE_PHASE1_NIBI_JOB_PACKAGE_REVIEW_CANDIDATE_"
        "NOT_AUTHORIZED_FOR_EXECUTION"
    ):
        raise ValueError("job-package status is wrong")
    if contract["execution_authorized"] is not False:
        raise ValueError("job package unexpectedly authorizes execution")
    if contract["submission_scripts_locked"] is not True:
        raise ValueError("submission scripts are not marked locked")
    if len(contract["campaign_seed_list"]) != 30:
        raise ValueError("job package does not contain 30 seeds")
    if len(contract["method_ids"]) != 8:
        raise ValueError("job package does not contain 8 methods")
    if contract["compute_dag"]["channel_generation_jobs"] != 30:
        raise ValueError("job package compute DAG is wrong")
    if contract["compute_dag"]["total_controller_evaluations"] != 1200:
        raise ValueError("job package controller evaluation count is wrong")
    if contract["primary_endpoint"] != (
        "final_moving_average_sum_log_utility"
    ):
        raise ValueError("job package primary endpoint is wrong")
    if campaign["statistics"]["resampling_unit"] != (
        "channel_topology_seed_cluster"
    ):
        raise ValueError("campaign statistics contract is wrong")
    if review["round2_verdict"] != (
        "PASS_FOR_IMMUTABLE_JOB_PACKAGE_PREPARATION_NOT_EXECUTION"
    ):
        raise ValueError("round-2 review verdict is wrong")

    source_binding = json.loads(
        (
            package
            / "channel_generator/source_bundle_provenance/"
            "FULL_TOPOLOGY_SOURCE_BUNDLE_BINDING.json"
        ).read_text(encoding="utf-8")
    )
    source_contract = contract["full_topology_source_bundle"]
    if source_binding["source_bundle_sha256"] != source_contract["sha256"]:
        raise ValueError("full-topology source binding SHA-256 mismatch")
    if source_binding["source_commit"] != source_contract["source_commit"]:
        raise ValueError("full-topology source binding commit mismatch")
    if source_binding["execution_authorized"] is not False:
        raise ValueError("full-topology source binding authorizes execution")
    expected_inputs = source_contract["expected_input_sha256"]
    if source_binding["input_sha256"] != expected_inputs:
        raise ValueError("full-topology input binding does not match contract")
    for relative, expected_hash in expected_inputs.items():
        source = package / "channel_generator" / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        if sha256_file(source) != expected_hash:
            raise ValueError(f"channel-generator input mismatch: {relative}")
    source_metadata = json.loads(
        (
            package
            / "channel_generator/source_bundle_provenance/"
            "BUNDLE_METADATA.json"
        ).read_text(encoding="utf-8")
    )
    for key in [
        "review_zip_sha256",
        "executed_input_bundle_sha256",
        "return_bundle_sha256",
    ]:
        if source_metadata.get(key) != source_contract[key]:
            raise ValueError(f"full-topology source metadata mismatch: {key}")

    package_id = (package / "PACKAGE_ID.txt").read_text(
        encoding="utf-8"
    ).strip()
    if contract["package_id"] != package_id or len(package_id) != 64:
        raise ValueError("package ID mismatch")
    token = json.loads(
        (package / "AUTHORIZATION_TOKEN_TEMPLATE.json").read_text(
            encoding="utf-8"
        )
    )
    if token["execution_authorized"] is not False:
        raise ValueError("included token template authorizes execution")
    if token["authorization"] == "EXECUTE_PHASE1_NIBI_V1":
        raise ValueError("included token template contains execution string")

    source_count = verify_text_manifest(
        package,
        package / "NEW_JOB_SOURCE_MANIFEST.sha256",
    )
    snapshot_count = verify_text_manifest(
        package / "source_snapshot",
        package / "source_snapshot/SOURCE_SNAPSHOT_MANIFEST.sha256",
    )
    package_count = verify_text_manifest(
        package,
        package / "PACKAGE_MANIFEST.sha256",
    )

    for slot in range(5):
        archive = package / (
            f"input/protected_pass_records/FR3_PROTECTED_PASS_SLOT_{slot}.zip"
        )
        checksum = Path(str(archive) + ".sha256")
        if checksum.read_text(encoding="utf-8").split()[0] != sha256_file(
            archive
        ):
            raise ValueError(f"pass {slot} archive checksum mismatch")
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                raise ValueError(f"pass {slot} archive is corrupt")

    package_zip = package / "FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip"
    checksum = Path(str(package_zip) + ".sha256")
    if checksum.read_text(encoding="utf-8").split()[0] != sha256_file(
        package_zip
    ):
        raise ValueError("job-package ZIP checksum mismatch")
    with zipfile.ZipFile(package_zip) as archive:
        if archive.testzip() is not None:
            raise ValueError("job-package ZIP is corrupt")

    for path in package.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for path in [
        package / "setup_environment.sh",
        package / "phase1_array_worker.sh",
        package / "RUN_PHASE1_NIBI_CAMPAIGN.sh",
        package / "SUBMIT_PHASE1_LOCKED.sh",
        package / "MERGE_PHASE1_LOCKED.sh",
    ]:
        result = subprocess.run(
            ["bash", "-n", str(path)], capture_output=True, text=True
        )
        if result.returncode:
            raise RuntimeError(f"Bash syntax failed: {path}: {result.stderr}")

    expected_lock(package / "RUN_PHASE1_NIBI_CAMPAIGN.sh")
    expected_lock(package / "SUBMIT_PHASE1_LOCKED.sh")
    expected_lock(package / "MERGE_PHASE1_LOCKED.sh")

    seed_help = subprocess.run(
        ["python3", str(package / "phase1_seed_worker.py"), "--help"],
        cwd=package,
        capture_output=True,
        text=True,
    )
    if seed_help.returncode != 0:
        raise RuntimeError(seed_help.stderr)

    worker_text = (package / "phase1_seed_worker.py").read_text(
        encoding="utf-8"
    )
    forbidden_legacy = [
        'CAMPAIGN_METADATA.json',
        'primary_design',
        'paired_methods',
    ]
    if any(token in worker_text for token in forbidden_legacy):
        raise ValueError("seed worker appears to parse forbidden legacy metadata")
    if "run_phase1_methods" not in worker_text:
        raise ValueError("seed worker does not use the reviewed method runtime")
    if "generate_full_channel" not in worker_text:
        raise ValueError("seed worker does not generate one full channel")

    print("IMMUTABLE PHASE-1 NIBI JOB PACKAGE STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "package_id": package_id,
                "candidate_zip_sha256": contract["candidate_v3"][
                    "zip_sha256"
                ],
                "seed_count": 30,
                "pass_count": 5,
                "method_count": 8,
                "controller_evaluations": 1200,
                "new_source_manifest_entries": source_count,
                "candidate_snapshot_entries": snapshot_count,
                "full_topology_input_count": len(expected_inputs),
                "full_topology_source_bundle_sha256": source_contract[
                    "sha256"
                ],
                "package_manifest_entries": package_count,
                "execution_authorized": False,
                "next_gate": contract["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
