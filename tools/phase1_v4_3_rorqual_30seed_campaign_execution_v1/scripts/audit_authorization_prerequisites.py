#!/usr/bin/env python3
"""Independently verify the exact prerequisites for full campaign authorization."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json_from_zip(z: zipfile.ZipFile, name: str) -> dict:
    return json.loads(z.read(name).decode("utf-8"))


def check_manifest(root: Path, manifest: Path) -> None:
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        digest, relative = raw.split(maxsplit=1)
        relative = relative.lstrip(" *")
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != digest:
            raise ValueError(f"manifest mismatch for {relative}: {actual} != {digest}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--package-root", required=True)
    args = p.parse_args()
    root = Path(args.package_root).expanduser().resolve()
    contract = json.loads(
        (root / "config/FULL_CAMPAIGN_AUTHORIZATION_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    imm = root / "immutable_bindings"
    job_zip = imm / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip"
    review_zip = imm / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_INDEPENDENT_REVIEW.zip"
    expected = contract["immutable_bindings"]
    if sha256_file(job_zip) != expected["rorqual_r2_job_package_sha256"]:
        raise ValueError("Rorqual R2 job ZIP binding mismatch")
    if sha256_file(review_zip) != expected["rorqual_r2_review_sha256"]:
        raise ValueError("Rorqual R2 review ZIP binding mismatch")
    for path in (job_zip, review_zip):
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad is not None:
                raise ValueError(f"ZIP CRC failure: {path.name}: {bad}")

    with zipfile.ZipFile(job_zip) as z:
        names = set(z.namelist())
        required = {
            "PACKAGE_ID.txt",
            "PACKAGE_MANIFEST.sha256",
            "JOB_PACKAGE_CONTRACT.json",
            "PHASE1_CAMPAIGN_CONTRACT_V4_3.json",
            "AUTHORIZATION_TOKEN_TEMPLATE.json",
            "phase1_array_worker.sh",
            "phase1_merge_worker.sh",
            "validate_seed_result.py",
            "validate_merged_results.py",
            "validator_contract.py",
        }
        if not required.issubset(names):
            raise ValueError(f"inner job package missing: {sorted(required - names)}")
        job_contract = read_json_from_zip(z, "JOB_PACKAGE_CONTRACT.json")
        campaign = read_json_from_zip(z, "PHASE1_CAMPAIGN_CONTRACT_V4_3.json")
        template = read_json_from_zip(z, "AUTHORIZATION_TOKEN_TEMPLATE.json")
        package_id = z.read("PACKAGE_ID.txt").decode().strip()
        if package_id != expected["rorqual_r2_package_id"]:
            raise ValueError("package ID mismatch")
        if job_contract["package_id"] != package_id:
            raise ValueError("contract package ID mismatch")
        if job_contract["execution_cluster"] != "rorqual":
            raise ValueError("execution cluster is not Rorqual")
        if job_contract["campaign_seed_list"] != list(range(44000, 44030)):
            raise ValueError("campaign seed list mismatch")
        if job_contract["method_count"] != 9 or job_contract["fixed_pass_count"] != 5:
            raise ValueError("method/pass design mismatch")
        if job_contract["total_cells"] != 1350:
            raise ValueError("cell count mismatch")
        if job_contract["execution_authorized"] is not False:
            raise ValueError("locked package unexpectedly authorizes execution")
        if template.get("execution_authorized") is not False or template.get("token_included") is not False:
            raise ValueError("authorization template is not safely locked")
        if campaign["candidate_status"] != "FROZEN_AFTER_CPU_AND_EXCLUDED_H100_EXACT_PASS":
            raise ValueError("candidate freeze status mismatch")
        if campaign["statistics"]["bootstrap_resamples"] != 10000:
            raise ValueError("bootstrap resample count mismatch")
        if campaign["statistics"]["primary_comparator"] != "static_robust_constrained_pf_with_sector_selective_fallback":
            raise ValueError("primary comparator mismatch")

        with tempfile.TemporaryDirectory(prefix="fr3-r2-audit-") as t:
            z.extractall(t)
            extracted = Path(t)
            check_manifest(extracted, extracted / "PACKAGE_MANIFEST.sha256")

    review = json.loads((imm / "INDEPENDENT_REVIEW_VERDICT.json").read_text(encoding="utf-8"))
    smoke = json.loads((imm / "SMOKE_RECLASSIFICATION_VERDICT.json").read_text(encoding="utf-8"))
    build = json.loads((imm / "BUILD_AUDIT.json").read_text(encoding="utf-8"))
    if review["status"] != "PASS_CORRECTED_RORQUAL_NATIVE_LOCKED_30_SEED_CAMPAIGN_PACKAGE_FOR_SEPARATE_AUTHORIZATION_NOT_EXECUTION":
        raise ValueError("independent review status is not PASS")
    if smoke["status"] != expected["excluded_smoke_status"]:
        raise ValueError("excluded smoke reclassification mismatch")
    if smoke["smoke_return_sha256"] != expected["excluded_smoke_return_sha256"]:
        raise ValueError("excluded smoke return binding mismatch")
    if smoke["candidate_hard_gates"] != "PASS" or smoke["candidate_trace_maximum_absolute_error"] != 0.0:
        raise ValueError("excluded smoke hard/trace gates failed")
    if build["source_candidate_changed"] is not False or build["validator_repairs_only"] is not True:
        raise ValueError("candidate source-change boundary violated")
    if contract["campaign_execution_authorized_by_this_package"] is not True:
        raise ValueError("this package does not contain an affirmative campaign decision")

    print("FULL_CAMPAIGN_AUTHORIZATION_PREREQUISITE_AUDIT=PASS")
    print("EXCLUDED_RORQUAL_FINAL_WORKER_SMOKE=PASS_AFTER_VALIDATOR_CONTRACT_REPAIR")
    print("RORQUAL_R2_LOCKED_CAMPAIGN_INDEPENDENT_REVIEW=PASS")
    print("CANDIDATE_SOURCE_CHANGED=NO")
    print("CAMPAIGN_SEED_COUNT=30")
    print("FIXED_PASS_COUNT=5")
    print("METHOD_COUNT=9")
    print("TOTAL_CELLS=1350")
    print("EXECUTION_CLUSTER=rorqual")
    print("CAMPAIGN_EXECUTION_AUTHORIZED=YES_EXACT_PACKAGE_AND_SEEDS_ONLY")
    print("AUTHORIZATION_DECISION_ID=" + contract["authorization_decision_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
