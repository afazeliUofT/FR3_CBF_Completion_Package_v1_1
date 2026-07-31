#!/usr/bin/env python3
"""Verify and freeze the independent review of the phase-1 job package."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(root: Path, manifest: Path) -> int:
    count = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split("  ", 1)
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != expected:
            raise ValueError(f"manifest mismatch: {relative}")
        count += 1
    return count


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def require_text(path: Path, fragments: list[str]) -> None:
    # Supplementary semantic check; immutable source identity is enforced
    # separately by package/source SHA-256 manifests.
    text = path.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())
    for fragment in fragments:
        normalized_fragment = " ".join(fragment.split())
        if normalized_fragment not in normalized_text:
            raise ValueError(
                f"{path}: required semantic fragment missing: {fragment}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review",
        default="config/phase1_nibi_job_package_independent_review_v1.json",
    )
    args = parser.parse_args()

    cfg = json.loads((ROOT / args.review).read_text(encoding="utf-8"))
    package = ROOT / Path(cfg["reviewed_job_package_path"]).parent
    job_zip = ROOT / cfg["reviewed_job_package_path"]
    review_zip = ROOT / cfg["reviewed_review_bundle_path"]

    if sha256_file(job_zip) != cfg["reviewed_job_package_sha256"]:
        raise ValueError("job-package ZIP SHA-256 mismatch")
    if sha256_file(review_zip) != cfg["reviewed_review_bundle_sha256"]:
        raise ValueError("package-review ZIP SHA-256 mismatch")
    for archive in [job_zip, review_zip]:
        with zipfile.ZipFile(archive) as bundle:
            bad = bundle.testzip()
            if bad is not None:
                raise RuntimeError(f"corrupt ZIP member: {bad}")

    contract = json.loads(
        (package / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8")
    )
    if contract["package_id"] != cfg["reviewed_package_id"]:
        raise ValueError("package ID mismatch")
    if contract["status"] != (
        "IMMUTABLE_PHASE1_NIBI_JOB_PACKAGE_REVIEW_CANDIDATE_"
        "NOT_AUTHORIZED_FOR_EXECUTION"
    ):
        raise ValueError("job-package status is wrong")
    if contract["execution_authorized"] is not False:
        raise ValueError("job package unexpectedly authorizes execution")
    if contract["submission_scripts_locked"] is not True:
        raise ValueError("submission scripts are not recorded as locked")
    if contract["candidate_v3"]["zip_sha256"] != cfg["candidate_v3_sha256"]:
        raise ValueError("candidate-v3 binding mismatch")
    if contract["round2_review"]["review_zip_sha256"] != cfg[
        "round2_review_sha256"
    ]:
        raise ValueError("round-2 review binding mismatch")
    if contract["full_topology_source_bundle"]["sha256"] != cfg[
        "full_topology_source_bundle_sha256"
    ]:
        raise ValueError("channel-generator source-bundle binding mismatch")
    if len(contract["campaign_seed_list"]) != 30:
        raise ValueError("campaign seed count is not 30")
    if len(contract["method_ids"]) != 8:
        raise ValueError("method count is not 8")
    if contract["compute_dag"]["channel_generation_jobs"] != 30:
        raise ValueError("channel-generation job count is not 30")
    if contract["compute_dag"]["pass_method_cells"] != 150:
        raise ValueError("seed/pass cell count is not 150")
    if contract["compute_dag"]["total_controller_evaluations"] != 1200:
        raise ValueError("controller evaluation count is not 1200")
    if contract["primary_endpoint"] != (
        "final_moving_average_sum_log_utility"
    ):
        raise ValueError("primary endpoint is wrong")
    if contract["mandatory_secondary_endpoint"] != (
        "duration_weighted_mean_moving_pf_utility"
    ):
        raise ValueError("mandatory secondary endpoint is wrong")

    package_manifest_entries = verify_manifest(
        package, package / "PACKAGE_MANIFEST.sha256"
    )
    new_source_entries = verify_manifest(
        package, package / "NEW_JOB_SOURCE_MANIFEST.sha256"
    )
    snapshot_entries = verify_manifest(
        package / "source_snapshot",
        package / "source_snapshot/SOURCE_SNAPSHOT_MANIFEST.sha256",
    )

    smoke = json.loads(
        (
            ROOT
            / "evidence/phase1_nibi_job_package_v1/"
            "EXACT_SLOT0_ALL8_METHOD_SMOKE_AUDIT.json"
        ).read_text(encoding="utf-8")
    )
    if smoke["status"] != "PASS_EXACT_LOCAL_SLOT0_ALL8_METHOD_SMOKE":
        raise ValueError("exact local smoke status is wrong")
    if smoke["package_id"] != cfg["reviewed_package_id"]:
        raise ValueError("smoke package ID mismatch")
    if smoke["candidate_zip_sha256"] != cfg["candidate_v3_sha256"]:
        raise ValueError("smoke candidate binding mismatch")
    if smoke["reactive_myopic_implemented_and_safe"] is not True:
        raise ValueError("reactive-myopic same-fallback smoke did not pass")
    if smoke["unshielded_myopic_violation_seconds"] <= 0:
        raise ValueError("unshielded myopic negative control did not activate")
    if smoke["virtual_queue_violation_seconds"] <= 0:
        raise ValueError("virtual-queue negative control did not activate")

    require_text(
        package / "phase1_seed_worker.py",
        [
            "one cellular channel/topology realization",
            "def generate_channel(",
            "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
            "for slot, pass_root in enumerate(pass_roots)",
        ],
    )
    require_text(
        package / "merge_phase1_results.py",
        [
            "bootstrap_seed_clusters",
            "predictive_minus_static_final_pf",
            "groupby(\"campaign_seed\")",
        ],
    )
    require_text(
        package / "setup_environment.sh",
        [
            'sionna-no-rt==2.0.1',
            '"torch==2.9.1"',
            '"pandas>=2.2,<3"',
            '"numpy>=2.0,<3"',
            '"scipy>=1.14,<2"',
        ],
    )

    lock_results = {}
    for name in [
        "RUN_PHASE1_NIBI_CAMPAIGN.sh",
        "SUBMIT_PHASE1_LOCKED.sh",
        "MERGE_PHASE1_LOCKED.sh",
    ]:
        result = subprocess.run(
            ["bash", str(package / name)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 64:
            raise RuntimeError(
                f"{name}: expected exit 64, got {result.returncode}"
            )
        lock_results[name] = result.returncode

    evidence = ROOT / "evidence/phase1_nibi_job_package_independent_review_v1"
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True)

    frozen = dict(cfg)
    frozen.update(
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": (
                "PASS_PHASE1_JOB_PACKAGE_FOR_NIBI_DEPLOYMENT_SMOKE_"
                "PREPARATION_NOT_FULL_CAMPAIGN_EXECUTION"
            ),
            "package_manifest_entries_verified": package_manifest_entries,
            "new_source_manifest_entries_verified": new_source_entries,
            "candidate_snapshot_entries_verified": snapshot_entries,
            "execution_lock_exit_codes": lock_results,
            "setup_environment_review": {
                "torch_and_sionna_exactly_versioned": True,
                "numpy_scipy_pandas_currently_range_versioned": True,
                "disposition": (
                    "An exact resolved Nibi environment lock is mandatory "
                    "before any smoke or campaign execution."
                ),
            },
        }
    )
    write_json(
        evidence / "PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_VERDICT.json",
        frozen,
    )
    for source, target in [
        (
            ROOT / args.review,
            evidence / "PHASE1_JOB_PACKAGE_REVIEW_CONFIG.json",
        ),
        (
            ROOT / "docs/PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_V1.md",
            evidence / "PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_V1.md",
        ),
        (
            package / "JOB_PACKAGE_CONTRACT.json",
            evidence / "JOB_PACKAGE_CONTRACT.json",
        ),
        (
            package / "NEW_JOB_SOURCE_RECORD.json",
            evidence / "NEW_JOB_SOURCE_RECORD.json",
        ),
        (
            package / "CANDIDATE_AND_REVIEW_BINDING.json",
            evidence / "CANDIDATE_AND_REVIEW_BINDING.json",
        ),
        (
            ROOT
            / "evidence/phase1_nibi_job_package_v1/"
            "EXACT_SLOT0_ALL8_METHOD_SMOKE_AUDIT.json",
            evidence / "EXACT_SLOT0_ALL8_METHOD_SMOKE_AUDIT.json",
        ),
    ]:
        shutil.copy2(source, target)

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(evidence).as_posix()}"
            )
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("PHASE-1 NIBI JOB-PACKAGE INDEPENDENT REVIEW FREEZE: PASS")
    print(
        json.dumps(
            {
                "verdict": cfg["verdict"],
                "reviewed_commit": cfg["reviewed_commit"],
                "package_id": cfg["reviewed_package_id"],
                "package_manifest_entries": package_manifest_entries,
                "new_source_entries": new_source_entries,
                "snapshot_entries": snapshot_entries,
                "execution_authorized": False,
                "next_gate": cfg["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
