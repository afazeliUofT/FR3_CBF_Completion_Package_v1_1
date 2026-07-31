#!/usr/bin/env python3
"""Build the immutable, execution-locked phase-1 Nibi job package."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import stat
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def copy_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        raise NotADirectoryError(source)
    shutil.copytree(source, target, dirs_exist_ok=True)


def verify_manifest(root: Path, manifest: Path) -> int:
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


def build_manifest(directory: Path, name: str, excluded: set[str]) -> Path:
    manifest = directory / name
    lines = []
    for path in sorted(directory.rglob("*")):
        if (
            path.is_file()
            and path != manifest
            and path.name not in excluded
        ):
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(directory).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/phase1_nibi_job_package_builder_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))

    candidate_zip = ROOT / cfg["candidate_v3"]["zip_path"]
    review_zip = ROOT / cfg["round2_review"]["review_zip_path"]
    if sha256_file(candidate_zip) != cfg["candidate_v3"]["zip_sha256"]:
        raise ValueError("candidate-v3 ZIP hash mismatch")
    if sha256_file(review_zip) != cfg["round2_review"]["review_zip_sha256"]:
        raise ValueError("round-2 review ZIP hash mismatch")
    review_verdict = json.loads(
        (ROOT / cfg["round2_review"]["verdict_path"]).read_text(
            encoding="utf-8"
        )
    )
    if review_verdict["round2_verdict"] != cfg["round2_review"][
        "required_verdict"
    ]:
        raise ValueError("round-2 review does not authorize package preparation")
    if review_verdict["campaign_execution_authorized"] is not False:
        raise ValueError("round-2 review unexpectedly authorizes execution")

    output = ROOT / cfg["paths"]["job_package_dir"]
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    template = ROOT / "job_templates/phase1_nibi_v1"
    copy_tree(template, output)

    candidate_contract = ROOT / cfg["candidate_v3"][
        "canonical_contract_path"
    ]
    shutil.copy2(
        candidate_contract,
        output / "PHASE1_CAMPAIGN_CONTRACT_V3.json",
    )
    shutil.copy2(
        ROOT / cfg["round2_review"]["verdict_path"],
        output / "PHASE1_ROUND2_REVIEW_VERDICT.json",
    )

    candidate_source = ROOT / cfg["candidate_v3"]["source_snapshot_path"]
    copy_tree(candidate_source, output / "source_snapshot")
    candidate_source_manifest = (
        output / "source_snapshot/SOURCE_SNAPSHOT_MANIFEST.sha256"
    )
    for line in candidate_source_manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = output / "source_snapshot" / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"candidate source snapshot mismatch: {relative}")

    runtime_source = ROOT / "src/fr3_cbf/phase1_job_runtime.py"
    if not runtime_source.is_file():
        raise FileNotFoundError(runtime_source)
    runtime_target = output / "src/fr3_cbf/phase1_job_runtime.py"
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime_source, runtime_target)
    snapshot_modules = output / "source_snapshot/src/fr3_cbf"
    for path in sorted(snapshot_modules.glob("*.py")):
        shutil.copy2(path, output / "src/fr3_cbf" / path.name)
    init_source = ROOT / "src/fr3_cbf/__init__.py"
    if init_source.is_file():
        shutil.copy2(init_source, output / "src/fr3_cbf/__init__.py")
    else:
        (output / "src/fr3_cbf/__init__.py").write_text(
            "\"\"\"Phase-1 reviewed FR3 controller runtime.\"\"\"\n",
            encoding="utf-8",
        )

    # Rehydrate the exact reviewed channel-generator inputs directly from the
    # immutable full-topology source bundle. The repository intentionally does
    # not retain an extracted ``nibi/.../input`` directory, so the job-package
    # builder must never depend on that transient working tree.
    full_source_cfg = cfg["full_topology_source_bundle"]
    full_source_bundle = ROOT / full_source_cfg["path"]
    if not full_source_bundle.is_file():
        raise FileNotFoundError(full_source_bundle)
    full_source_sha256 = sha256_file(full_source_bundle)
    if full_source_sha256 != full_source_cfg["sha256"]:
        raise ValueError("full-topology source-bundle SHA-256 mismatch")

    channel_generator = output / "channel_generator"
    channel_generator.mkdir()
    source_bundle_manifest_bytes: bytes
    with TemporaryDirectory(prefix="fr3_fulltopo_source_") as temp_name:
        extracted = Path(temp_name)
        with zipfile.ZipFile(full_source_bundle) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise RuntimeError(
                    f"corrupt full-topology source-bundle member: {bad}"
                )
            archive.extractall(extracted)
        full_source_manifest = extracted / "BUNDLE_MANIFEST.sha256"
        source_manifest_entries = verify_manifest(
            extracted, full_source_manifest
        )
        source_bundle_manifest_bytes = full_source_manifest.read_bytes()
        source_metadata = json.loads(
            (extracted / "BUNDLE_METADATA.json").read_text(encoding="utf-8")
        )
        for key in [
            "review_zip_sha256",
            "executed_input_bundle_sha256",
            "return_bundle_sha256",
        ]:
            if source_metadata.get(key) != full_source_cfg[key]:
                raise ValueError(
                    f"full-topology source metadata mismatch: {key}"
                )

        expected_inputs = full_source_cfg["expected_input_sha256"]
        recovered_inputs: dict[str, str] = {}
        for relative, expected_hash in expected_inputs.items():
            source = extracted / relative
            if not source.is_file():
                raise FileNotFoundError(source)
            actual_hash = sha256_file(source)
            if actual_hash != expected_hash:
                raise ValueError(
                    f"full-topology input hash mismatch: {relative}"
                )
            recovered_inputs[relative] = actual_hash

        for source_name, target_name in [
            ("run_full_topology_export.py", "run_full_topology_export.py"),
            ("export_config.json", "export_config_base.json"),
        ]:
            source = extracted / source_name
            if not source.is_file():
                raise FileNotFoundError(source)
            shutil.copy2(source, channel_generator / target_name)

        copy_tree(extracted / "input", channel_generator / "input")
        provenance = channel_generator / "source_bundle_provenance"
        provenance.mkdir()
        shutil.copy2(
            extracted / "BUNDLE_METADATA.json",
            provenance / "BUNDLE_METADATA.json",
        )
        shutil.copy2(
            full_source_manifest,
            provenance / "BUNDLE_MANIFEST.sha256",
        )
        write_json(
            provenance / "FULL_TOPOLOGY_SOURCE_BUNDLE_BINDING.json",
            {
                "schema_version": 1,
                "source_bundle_path": full_source_cfg["path"],
                "source_bundle_sha256": full_source_sha256,
                "source_commit": full_source_cfg["source_commit"],
                "source_bundle_manifest_entries": source_manifest_entries,
                "review_zip_sha256": full_source_cfg["review_zip_sha256"],
                "executed_input_bundle_sha256": full_source_cfg[
                    "executed_input_bundle_sha256"
                ],
                "return_bundle_sha256": full_source_cfg[
                    "return_bundle_sha256"
                ],
                "input_sha256": recovered_inputs,
                "execution_authorized": False,
            },
        )

    candidate_passes = ROOT / "campaign/phase1_candidate_v3/protected_pass_records"
    copy_tree(candidate_passes, output / "input/protected_pass_records")
    for slot in range(5):
        archive = output / (
            f"input/protected_pass_records/FR3_PROTECTED_PASS_SLOT_{slot}.zip"
        )
        checksum = Path(str(archive) + ".sha256")
        if not archive.is_file() or not checksum.is_file():
            raise FileNotFoundError(archive)
        if checksum.read_text(encoding="utf-8").split()[0] != sha256_file(
            archive
        ):
            raise ValueError(f"pass-slot {slot} checksum mismatch")
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                raise ValueError(f"pass-slot {slot} ZIP is corrupt")

    new_source_paths = [
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
        "README_JOB_PACKAGE.md",
        "src/fr3_cbf/phase1_job_runtime.py",
        "templates/phase1_array.sbatch.template",
        "templates/phase1_merge.sbatch.template",
    ]
    new_source_records = []
    for relative in new_source_paths:
        path = output / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        new_source_records.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    write_json(
        output / "NEW_JOB_SOURCE_RECORD.json",
        {
            "schema_version": 1,
            "files": new_source_records,
            "review_required": True,
        },
    )
    new_manifest = output / "NEW_JOB_SOURCE_MANIFEST.sha256"
    new_manifest.write_text(
        "\n".join(
            f"{row['sha256']}  {row['path']}"
            for row in new_source_records
        )
        + "\n",
        encoding="utf-8",
    )

    package_id_material = b"\n".join(
        [
            candidate_contract.read_bytes(),
            cfg["candidate_v3"]["zip_sha256"].encode(),
            cfg["round2_review"]["review_zip_sha256"].encode(),
            candidate_source_manifest.read_bytes(),
            new_manifest.read_bytes(),
            full_source_cfg["sha256"].encode(),
            source_bundle_manifest_bytes,
            (
                channel_generator
                / "source_bundle_provenance"
                / "FULL_TOPOLOGY_SOURCE_BUNDLE_BINDING.json"
            ).read_bytes(),
        ]
    )
    package_id = hashlib.sha256(package_id_material).hexdigest()
    (output / "PACKAGE_ID.txt").write_text(
        package_id + "\n", encoding="utf-8"
    )

    campaign = json.loads(candidate_contract.read_text(encoding="utf-8"))
    method_ids = [row["id"] for row in campaign["method_contracts"]]
    if len(method_ids) != 8 or len(set(method_ids)) != 8:
        raise ValueError("canonical campaign contract does not have 8 methods")
    contract = {
        "schema_version": 1,
        "status": (
            "IMMUTABLE_PHASE1_NIBI_JOB_PACKAGE_REVIEW_CANDIDATE_"
            "NOT_AUTHORIZED_FOR_EXECUTION"
        ),
        "claim_boundary": cfg["claim_boundary"],
        "package_id": package_id,
        "candidate_v3": cfg["candidate_v3"],
        "round2_review": cfg["round2_review"],
        "full_topology_source_bundle": cfg[
            "full_topology_source_bundle"
        ],
        "campaign_seed_list": cfg["channel_seed_mapping"][
            "campaign_seed_list"
        ],
        "seed_mapping": cfg["channel_seed_mapping"],
        "method_ids": method_ids,
        "compute_dag": campaign["compute_dag"],
        "nibi_resource_template": cfg["nibi_resource_template"],
        "primary_endpoint": (
            "final_moving_average_sum_log_utility"
        ),
        "mandatory_secondary_endpoint": (
            "duration_weighted_mean_moving_pf_utility"
        ),
        "authorization_contract": {
            "authorization_file_required": True,
            "required_authorization_string": "EXECUTE_PHASE1_NIBI_V1",
            "required_package_id": package_id,
            "token_included": False,
        },
        "execution_authorized": False,
        "submission_scripts_locked": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "next_gate": cfg["next_gate"],
    }
    write_json(output / "JOB_PACKAGE_CONTRACT.json", contract)
    write_json(
        output / "AUTHORIZATION_TOKEN_TEMPLATE.json",
        {
            "schema_version": 1,
            "authorization": "NOT_AUTHORIZED",
            "execution_authorized": False,
            "package_id": package_id,
            "candidate_zip_sha256": cfg["candidate_v3"]["zip_sha256"],
            "note": (
                "A future independently issued token must replace this "
                "non-authorizing template."
            ),
        },
    )
    write_json(
        output / "CANDIDATE_AND_REVIEW_BINDING.json",
        {
            "candidate_commit": cfg["candidate_v3"]["commit"],
            "candidate_zip_sha256": cfg["candidate_v3"]["zip_sha256"],
            "round2_review_commit": cfg["round2_review"]["commit"],
            "round2_review_zip_sha256": cfg["round2_review"][
                "review_zip_sha256"
            ],
            "round2_verdict": cfg["round2_review"][
                "required_verdict"
            ],
            "full_topology_source_bundle_sha256": full_source_cfg[
                "sha256"
            ],
            "full_topology_source_commit": full_source_cfg[
                "source_commit"
            ],
            "package_id": package_id,
            "execution_authorized": False,
        },
    )

    executable_names = [
        "phase1_seed_worker.py",
        "validate_seed_result.py",
        "merge_phase1_results.py",
        "validate_merged_results.py",
        "setup_environment.sh",
        "phase1_array_worker.sh",
        "RUN_PHASE1_NIBI_CAMPAIGN.sh",
        "SUBMIT_PHASE1_LOCKED.sh",
        "MERGE_PHASE1_LOCKED.sh",
    ]
    for name in executable_names:
        path = output / name
        path.chmod(
            path.stat().st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )

    excluded = {
        "PACKAGE_MANIFEST.sha256",
        "FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip",
        "FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip.sha256",
    }
    build_manifest(output, "PACKAGE_MANIFEST.sha256", excluded)
    package_zip = output / "FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip"
    with zipfile.ZipFile(
        package_zip,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(output.rglob("*")):
            if (
                path.is_file()
                and path != package_zip
                and path != Path(str(package_zip) + ".sha256")
            ):
                archive.write(path, path.relative_to(output).as_posix())
    with zipfile.ZipFile(package_zip) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("job-package ZIP is corrupt")
    package_sha = sha256_file(package_zip)
    Path(str(package_zip) + ".sha256").write_text(
        f"{package_sha}  {package_zip.name}\n",
        encoding="utf-8",
    )

    print("IMMUTABLE PHASE-1 NIBI JOB PACKAGE BUILD: PASS")
    print("Package ID:", package_id)
    print("Package ZIP:", package_zip)
    print("Package ZIP SHA-256:", package_sha)
    print("Execution authorized: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
