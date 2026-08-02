#!/usr/bin/env python3
"""Build a corrected, Rorqual-native, execution-locked v4.3 campaign package."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FIXED_ZIP_TIME = (2026, 8, 2, 0, 0, 0)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def verify_sidecar(path: Path, expected: str) -> None:
    sidecar = Path(str(path) + ".sha256")
    parts = sidecar.read_text(encoding="utf-8").split()
    if len(parts) != 2 or parts[1] != path.name:
        raise ValueError(f"nonportable sidecar: {sidecar}")
    actual = sha256_file(path)
    if actual != expected or parts[0] != actual:
        raise ValueError(f"SHA-256 mismatch: {path}")


def deterministic_zip(source: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"ZIP CRC failure: {bad}")


def build_manifest(root: Path, name: str) -> Path:
    manifest = root / name
    lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(f"{sha256_file(path)}  {path.relative_to(root).as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def patch_text(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError(f"patch target not found in {path}: {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-root", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    audit_root = Path(args.audit_root).expanduser().resolve()
    output = Path(args.output_root).expanduser().resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    config = json.loads(
        (PACKAGE_ROOT / "config/REPAIR_REVIEW_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    verdict_path = audit_root / "SMOKE_RECLASSIFICATION_VERDICT.json"
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    if verdict["status"] != (
        "PASS_EXCLUDED_RORQUAL_FINAL_WORKER_SMOKE_AFTER_VALIDATOR_CONTRACT_REPAIR"
    ):
        raise ValueError("smoke reclassification did not pass")

    old_zip = (
        PACKAGE_ROOT
        / "immutable_bindings/locked_campaign"
        / config["legacy_locked_campaign"]["filename"]
    )
    verify_sidecar(old_zip, config["legacy_locked_campaign"]["sha256"])
    with zipfile.ZipFile(old_zip) as archive:
        if archive.testzip() is not None:
            raise ValueError("legacy job package CRC failure")

    root_name = "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_ROOT"
    root = output / root_name
    with zipfile.ZipFile(old_zip) as archive:
        archive.extractall(root)

    # Replace validators with contract-corrected versions and a shared domain module.
    shutil.copy2(PACKAGE_ROOT / "templates/validate_seed_result.py", root)
    shutil.copy2(PACKAGE_ROOT / "templates/validate_merged_results.py", root)
    shutil.copy2(PACKAGE_ROOT / "templates/validator_contract.py", root)
    for name in [
        "validate_seed_result.py",
        "validate_merged_results.py",
        "validator_contract.py",
    ]:
        path = root / name
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    old_contract = json.loads((root / "JOB_PACKAGE_CONTRACT.json").read_text())
    campaign = json.loads((root / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json").read_text())
    candidate_source_manifest_sha = old_contract["candidate_v4_3"][
        "source_manifest_sha256"
    ]
    binding = {
        "revision": "V4_3_RORQUAL_R2_VALIDATOR_CONTRACT_REPAIR",
        "legacy_job_package_sha256": sha256_file(old_zip),
        "smoke_return_sha256": config["smoke_return"]["sha256"],
        "smoke_reclassification_status": verdict["status"],
        "validate_seed_result_sha256": sha256_file(root / "validate_seed_result.py"),
        "validate_merged_results_sha256": sha256_file(
            root / "validate_merged_results.py"
        ),
        "validator_contract_sha256": sha256_file(root / "validator_contract.py"),
        "candidate_source_manifest_sha256": candidate_source_manifest_sha,
        "execution_cluster": "rorqual",
        "campaign_seed_list": list(range(44000, 44030)),
        "fixed_pass_count": 5,
        "method_count": 9,
        "total_cells": 1350,
    }
    package_id = canonical_sha256(binding)
    authorization_string = "EXECUTE_PHASE1_RORQUAL_V4_3_R2"

    old_contract["schema_version"] = 3
    old_contract["package_id"] = package_id
    old_contract["status"] = (
        "IMMUTABLE_PHASE1_V4_3_RORQUAL_R2_JOB_PACKAGE_REVIEWED_"
        "NOT_AUTHORIZED_FOR_EXECUTION"
    )
    old_contract["created_utc"] = "2026-08-02T00:00:00+00:00"
    old_contract["execution_cluster"] = "rorqual"
    old_contract["execution_authorized"] = False
    old_contract["submission_scripts_locked"] = True
    old_contract["merge_scripts_locked"] = True
    old_contract["next_gate"] = (
        "SEPARATE_RORQUAL_30_SEED_CAMPAIGN_AUTHORIZATION_AND_EXECUTION"
    )
    old_contract["claim_boundary"] = (
        "CORRECTED_RORQUAL_NATIVE_LOCKED_CAMPAIGN_PACKAGE_NOT_EXECUTION_"
        "NOT_PAPER_RESULT_NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE"
    )
    old_contract["validator_contract_revision"] = (
        "CANDIDATE_ONLY_NA_SEMANTICS_AND_GEOMETRIC_MEAN_DEFINITION_R2"
    )
    old_contract["smoke_reclassification_binding"] = {
        "job_id": "18132931",
        "return_zip_sha256": config["smoke_return"]["sha256"],
        "status": verdict["status"],
        "validator_contract_repair": True,
    }
    old_contract["descriptive_metric_contract"] = {
        "total_active_eligible_geometric_mean_bps_hz": {
            "definition": "exp(mean(log(x+0.001)))-0.001",
            "scope": "positive delivered total rates of active eligible users",
            "role": "descriptive_not_primary_or_mandatory_secondary_endpoint",
        },
        "excluded_reference_standard_positive_geometric_mean": {
            "definition": "exp(mean(log(x)))",
            "scope": "excluded seed diagnostic only",
            "must_not_be_directly_compared_to_campaign_epsilon_stabilized_metric": True,
        },
    }
    old_contract.pop("nibi_resource_template", None)
    old_contract["rorqual_resource_template"] = {
        "cluster": "rorqual",
        "array": "0-29%8",
        "gpu": "h100:1",
        "cpus_per_task": 16,
        "memory_gib": 124,
        "time_limit": "04:00:00",
        "gpu_account_preference": "def-rsadve_gpu",
        "cpu_merge_account_preference": "def-rsadve_cpu",
        "scratch_link": "/home/rsadve1/links/scratch",
        "home_heavy_storage_prohibited": True,
    }
    old_contract["authorization_contract"].update(
        {
            "required_authorization_string": authorization_string,
            "required_package_id": package_id,
            "token_included": False,
        }
    )
    write_json(root / "JOB_PACKAGE_CONTRACT.json", old_contract)

    campaign["schema_version"] = 5
    campaign["execution_cluster"] = "rorqual"
    campaign["campaign_execution_authorized"] = False
    campaign["paper_result"] = False
    campaign["package_revision"] = "V4_3_RORQUAL_R2"
    campaign["validator_contract_revision"] = (
        "CANDIDATE_ONLY_NA_SEMANTICS_AND_GEOMETRIC_MEAN_DEFINITION_R2"
    )
    campaign["descriptive_metrics"] = old_contract["descriptive_metric_contract"]
    write_json(root / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json", campaign)

    result_schema = json.loads((root / "RESULT_SCHEMA.json").read_text())
    result_schema["schema_version"] = 4
    result_schema["cell_summary_numeric_domain_contract"] = {
        "common_numeric_fields": "finite for every method row",
        "candidate_only_numeric_fields": (
            "finite on candidate rows and blank/NaN on comparator rows"
        ),
        "candidate_only_nan_is_not_data_corruption": True,
    }
    result_schema["descriptive_metric_definitions"] = old_contract[
        "descriptive_metric_contract"
    ]
    write_json(root / "RESULT_SCHEMA.json", result_schema)

    guard = root / "authorization_guard.py"
    patch_text(
        guard,
        'AUTHORIZATION_STRING = "EXECUTE_PHASE1_NIBI_V4_3_V1"',
        f'AUTHORIZATION_STRING = "{authorization_string}"',
    )

    setup = root / "setup_environment.sh"
    patch_text(setup, "PHASE-1 NIBI ENVIRONMENT: PASS", "PHASE-1 RORQUAL ENVIRONMENT: PASS")

    # Rename the visibly Nibi-specific locked entrypoint. It remains non-executable
    # without a separately issued exact-package authorization token.
    old_run = root / "RUN_PHASE1_NIBI_CAMPAIGN.sh"
    if old_run.exists():
        new_run = root / "RUN_PHASE1_RORQUAL_CAMPAIGN.sh"
        old_run.rename(new_run)
        patch_text(
            new_run,
            "Required next gate: excluded final campaign-worker smoke and independent review",
            "Required next gate: separate Rorqual full-campaign authorization",
        )

    token_template = {
        "schema_version": 2,
        "authorization": authorization_string,
        "package_id": package_id,
        "package_manifest_sha256": "FILL_FROM_FINAL_EXTRACTED_PACKAGE",
        "candidate_source_manifest_sha256": candidate_source_manifest_sha,
        "freeze_commit": old_contract["freeze_commit"],
        "execution_stage": "FULL_30_SEED_CONFIRMATORY_CAMPAIGN",
        "allowed_seeds": list(range(44000, 44030)),
        "authorization_expires_utc": "FILL_WITH_FUTURE_UTC_EXPIRY",
        "execution_authorized": False,
        "token_included": False,
        "note": "This is a non-authorizing template. Do not edit it into an execution token.",
    }
    write_json(root / "AUTHORIZATION_TOKEN_TEMPLATE.json", token_template)
    (root / "PACKAGE_ID.txt").write_text(package_id + "\n", encoding="utf-8")
    write_json(root / "RORQUAL_R2_BINDING.json", binding | {"package_id": package_id})
    (root / "README_JOB_PACKAGE.md").write_text(
        "# Candidate v4.3 Rorqual campaign package R2\n\n"
        "This package is execution-locked. It retains the frozen candidate-v4.3 "
        "algorithm and repairs only two validation-contract defects discovered by "
        "the excluded Rorqual final-worker smoke. It targets Rorqual H100 nodes.\n\n"
        "No authorization token is included. Seeds 44000--44029 must not be run "
        "until a separate authorization package is issued.\n",
        encoding="utf-8",
    )

    # Remove obsolete manifest last, then rebuild a complete one.
    for name in ["PACKAGE_MANIFEST.sha256"]:
        path = root / name
        if path.exists():
            path.unlink()
    build_manifest(root, "PACKAGE_MANIFEST.sha256")

    package_zip = output / config["new_locked_campaign"]["package_filename"]
    deterministic_zip(root, package_zip)
    package_sha = sha256_file(package_zip)
    Path(str(package_zip) + ".sha256").write_text(
        f"{package_sha}  {package_zip.name}\n", encoding="utf-8"
    )
    build_audit = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_CORRECTED_RORQUAL_NATIVE_LOCKED_30_SEED_CAMPAIGN_PACKAGE_BUILD",
        "package_id": package_id,
        "package_zip": package_zip.name,
        "package_zip_sha256": package_sha,
        "source_candidate_changed": False,
        "candidate_source_manifest_sha256": candidate_source_manifest_sha,
        "validator_repairs_only": True,
        "execution_cluster": "rorqual",
        "campaign_seed_count": 30,
        "fixed_pass_count": 5,
        "method_count": 9,
        "total_cells": 1350,
        "authorization_token_included": False,
        "campaign_execution_authorized": False,
        "smoke_reclassification_status": verdict["status"],
        "next_gate": "INDEPENDENT_REVIEW_CORRECTED_RORQUAL_NATIVE_LOCKED_PACKAGE",
    }
    write_json(output / "BUILD_AUDIT.json", build_audit)
    print("RORQUAL_R2_LOCKED_CAMPAIGN_BUILD=PASS")
    print(f"RORQUAL_R2_PACKAGE_ID={package_id}")
    print(f"RORQUAL_R2_JOB_PACKAGE_ZIP={package_zip}")
    print(f"RORQUAL_R2_JOB_PACKAGE_ZIP_SHA256={package_sha}")
    print("CANDIDATE_SOURCE_CHANGED=NO")
    print("VALIDATOR_REPAIRS_ONLY=YES")
    print("CAMPAIGN_EXECUTION_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
