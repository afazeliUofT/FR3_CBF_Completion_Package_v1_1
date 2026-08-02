#!/usr/bin/env python3
"""Audit the exact locked v4.3 campaign package and its independent review."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_basename_sidecar(path: Path, archive: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise ValueError(f"sidecar must contain one line: {path}")
    parts = lines[0].split()
    if len(parts) != 2:
        raise ValueError(f"sidecar must contain hash and basename: {path}")
    digest, name = parts
    if name != archive.name or Path(name).name != name:
        raise ValueError(f"sidecar is not basename-only for {archive.name}")
    actual = sha256_file(archive)
    if digest != actual:
        raise ValueError(f"sidecar mismatch for {archive.name}: {digest} != {actual}")


def verify_manifest(root: Path, manifest: Path) -> int:
    count = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split("  ", 1)
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"manifest mismatch for {relative}: {actual} != {expected}")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(args.package_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    contract = json.loads(
        (root / "config/FINAL_WORKER_SMOKE_CONTRACT.json").read_text(encoding="utf-8")
    )
    locked = root / "immutable_bindings/locked_campaign"
    job = locked / contract["locked_job_package"]["filename"]
    review = locked / contract["independent_review"]["filename"]
    for archive in (job, review):
        if not archive.is_file():
            raise FileNotFoundError(archive)
        sidecar = Path(str(archive) + ".sha256")
        if not sidecar.is_file():
            raise FileNotFoundError(sidecar)
        verify_basename_sidecar(sidecar, archive)
        with zipfile.ZipFile(archive) as bundle:
            bad = bundle.testzip()
            if bad is not None:
                raise RuntimeError(f"CRC failure in {archive.name}: {bad}")

    if sha256_file(job) != contract["locked_job_package"]["sha256"]:
        raise ValueError("locked job ZIP contract mismatch")
    if sha256_file(review) != contract["independent_review"]["sha256"]:
        raise ValueError("locked review ZIP contract mismatch")

    with tempfile.TemporaryDirectory(prefix="fr3-v43-locked-audit-") as tmp_name:
        tmp = Path(tmp_name)
        job_root = tmp / "job"
        review_root = tmp / "review"
        job_root.mkdir()
        review_root.mkdir()
        with zipfile.ZipFile(job) as bundle:
            bundle.extractall(job_root)
        with zipfile.ZipFile(review) as bundle:
            bundle.extractall(review_root)

        manifest_count = verify_manifest(job_root, job_root / "PACKAGE_MANIFEST.sha256")
        review_manifest_count = verify_manifest(
            review_root, review_root / "REVIEW_MANIFEST.sha256"
        )
        job_contract = json.loads(
            (job_root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8")
        )
        campaign = json.loads(
            (job_root / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json").read_text(
                encoding="utf-8"
            )
        )
        verdict = json.loads(
            (review_root / "INDEPENDENT_REVIEW_VERDICT.json").read_text(
                encoding="utf-8"
            )
        )

        expected = contract["locked_job_package"]
        checks = {
            "package_id": job_contract["package_id"] == expected["package_id"],
            "freeze_commit": job_contract["freeze_commit"] == expected["freeze_commit"],
            "candidate_source_manifest": (
                job_contract["candidate_v4_3"]["source_manifest_sha256"]
                == expected["candidate_source_manifest_sha256"]
            ),
            "seed_list": job_contract["campaign_seed_list"] == list(range(44000, 44030)),
            "excluded_seed": int(job_contract["excluded_smoke_seed"]) == 43999,
            "method_count": int(job_contract["method_count"]) == 9,
            "pass_count": int(job_contract["fixed_pass_count"]) == 5,
            "total_cells": int(job_contract["total_cells"]) == 1350,
            "execution_locked": job_contract["execution_authorized"] is False,
            "token_absent": job_contract["authorization_contract"]["token_included"] is False,
            "smoke_stage_permitted": (
                "EXCLUDED_FINAL_WORKER_SMOKE_SEED43999"
                in job_contract["authorization_contract"]["permitted_execution_stages"]
            ),
            "full_stage_not_authorized": campaign["campaign_execution_authorized"] is False,
            "information_exchange_not_overclaimed": (
                campaign["information_exchange_claim_boundary"]
                == "ACTION_SCOPE_LOCALITY_VERIFIED_INFORMATION_EXCHANGE_LOCALITY_NOT_YET_CERTIFIED"
            ),
            "review_pass": verdict["status"]
            == contract["independent_review"]["verdict"],
            "review_no_authorization": verdict["campaign_execution_authorized"] is False,
            "review_cluster_not_contacted": verdict["cluster_contacted"] is False,
            "locked_launcher_run": "execution is locked"
            in (job_root / "RUN_PHASE1_NIBI_CAMPAIGN.sh").read_text(encoding="utf-8"),
            "locked_launcher_submit": "execution is locked"
            in (job_root / "SUBMIT_PHASE1_LOCKED.sh").read_text(encoding="utf-8"),
        }
        failed = [key for key, value in checks.items() if not value]
        if failed:
            raise RuntimeError(f"locked campaign input audit failed: {failed}")

        value = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS_LOCKED_V4_3_CAMPAIGN_INPUT_AND_REVIEW_AUDIT",
            "job_zip_sha256": sha256_file(job),
            "review_zip_sha256": sha256_file(review),
            "job_package_manifest_sha256": sha256_file(
                job_root / "PACKAGE_MANIFEST.sha256"
            ),
            "job_package_manifest_entries": manifest_count,
            "review_manifest_entries": review_manifest_count,
            "package_id": job_contract["package_id"],
            "freeze_commit": job_contract["freeze_commit"],
            "candidate_source_manifest_sha256": job_contract["candidate_v4_3"][
                "source_manifest_sha256"
            ],
            "excluded_seed": int(job_contract["excluded_smoke_seed"]),
            "confirmatory_seed_count": len(job_contract["campaign_seed_list"]),
            "method_count": int(job_contract["method_count"]),
            "pass_count": int(job_contract["fixed_pass_count"]),
            "checks": checks,
            "campaign_execution_authorized": False,
            "next_gate": contract["next_gate_on_pass"],
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("LOCKED_V4_3_CAMPAIGN_INPUT_AUDIT=PASS")
    print(f"LOCKED_JOB_PACKAGE_SHA256={value['job_zip_sha256']}")
    print(f"LOCKED_REVIEW_ZIP_SHA256={value['review_zip_sha256']}")
    print(f"LOCKED_PACKAGE_ID={value['package_id']}")
    print("CAMPAIGN_EXECUTION_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
