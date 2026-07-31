#!/usr/bin/env python3
"""Verify candidate v3 and freeze the external round-2 review record."""
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


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review",
        default="config/phase1_candidate_v3_round2_review_v1.json",
    )
    args = parser.parse_args()

    review_cfg = json.loads(
        (ROOT / args.review).read_text(encoding="utf-8")
    )
    candidate = ROOT / Path(
        review_cfg["candidate_zip_path"]
    ).parent
    candidate_zip = ROOT / review_cfg["candidate_zip_path"]
    review_zip = ROOT / review_cfg["review_prep_zip_path"]

    if sha256_file(candidate_zip) != review_cfg[
        "candidate_zip_sha256"
    ]:
        raise ValueError("candidate-v3 ZIP SHA-256 mismatch")
    if sha256_file(review_zip) != review_cfg[
        "review_prep_zip_sha256"
    ]:
        raise ValueError("review-prep ZIP SHA-256 mismatch")
    with zipfile.ZipFile(candidate_zip) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("candidate-v3 ZIP is corrupt")
    with zipfile.ZipFile(review_zip) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("review-prep ZIP is corrupt")

    candidate_manifest_count = verify_manifest(
        candidate,
        candidate / "BUNDLE_MANIFEST.sha256",
    )
    source_snapshot = candidate / "source_snapshot"
    source_manifest_count = verify_manifest(
        source_snapshot,
        source_snapshot / "SOURCE_SNAPSHOT_MANIFEST.sha256",
    )

    contract = json.loads(
        (candidate / "PHASE1_CAMPAIGN_CONTRACT_V3.json").read_text(
            encoding="utf-8"
        )
    )
    metadata = json.loads(
        (candidate / "CAMPAIGN_METADATA.json").read_text(
            encoding="utf-8"
        )
    )
    internal_review = json.loads(
        (candidate / "INDEPENDENT_REVIEW_STATUS.json").read_text(
            encoding="utf-8"
        )
    )

    if contract["status"] != (
        "REVISED_PHASE1_REVIEW_CANDIDATE_NOT_AUTHORIZED_FOR_EXECUTION"
    ):
        raise ValueError("candidate-v3 contract status is wrong")
    if contract["execution_authorized"] is not False:
        raise ValueError("candidate-v3 contract unexpectedly authorizes execution")
    if len(contract["fixed_population"]["channel_topology_seeds"]) != 30:
        raise ValueError("candidate-v3 does not have 30 seed clusters")
    if contract["fixed_population"]["protected_pass_slots"] != [
        0, 1, 2, 3, 4
    ]:
        raise ValueError("candidate-v3 pass slots are wrong")
    if len(contract["method_contracts"]) != 8:
        raise ValueError("candidate-v3 method count is wrong")
    if contract["statistics"]["resampling_unit"] != (
        "channel_topology_seed_cluster"
    ):
        raise ValueError("candidate-v3 resampling unit is wrong")
    if contract["compute_dag"]["channel_generation_jobs"] != 30:
        raise ValueError("candidate-v3 compute DAG is wrong")
    if metadata["execution_authorized"] is not False:
        raise ValueError("candidate metadata unexpectedly authorizes execution")
    if internal_review["status"] != "PENDING_ROUND2":
        raise ValueError("internal review status is not the reviewed pending state")

    result = subprocess.run(
        ["bash", str(candidate / "RUN_PHASE1_CAMPAIGN.sh")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 64:
        raise RuntimeError(
            f"candidate execution lock returned {result.returncode}"
        )
    if "not authorized" not in result.stdout.lower():
        raise RuntimeError("candidate execution-lock text is wrong")

    evidence = ROOT / "evidence/phase1_candidate_v3_round2_review"
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True)

    frozen = dict(review_cfg)
    frozen.update(
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "candidate_manifest_entries_verified": candidate_manifest_count,
            "source_snapshot_entries_verified": source_manifest_count,
            "candidate_internal_review_status": internal_review["status"],
            "execution_lock_exit_code": result.returncode,
            "canonical_contract_path": (
                "campaign/phase1_candidate_v3/"
                "PHASE1_CAMPAIGN_CONTRACT_V3.json"
            ),
            "status": (
                "PASS_PHASE1_CANDIDATE_V3_FOR_IMMUTABLE_"
                "JOB_PACKAGE_PREPARATION_NOT_EXECUTION"
            ),
        }
    )
    write_json(
        evidence / "PHASE1_ROUND2_REVIEW_VERDICT.json",
        frozen,
    )
    shutil.copy2(
        ROOT / "docs/PHASE1_INDEPENDENT_REVIEW_ROUND2.md",
        evidence / "PHASE1_INDEPENDENT_REVIEW_ROUND2.md",
    )
    shutil.copy2(
        ROOT / args.review,
        evidence / "PHASE1_ROUND2_REVIEW_CONFIG.json",
    )
    shutil.copy2(
        candidate / "PHASE1_CAMPAIGN_CONTRACT_V3.json",
        evidence / "PHASE1_CAMPAIGN_CONTRACT_V3.json",
    )
    shutil.copy2(
        candidate / "CANDIDATE_PROVENANCE.json",
        evidence / "CANDIDATE_PROVENANCE.json",
    )
    shutil.copy2(
        candidate / "SOURCE_SNAPSHOT_RECORD.json",
        evidence / "SOURCE_SNAPSHOT_RECORD.json",
    )
    shutil.copy2(
        candidate / "INDEPENDENT_REVIEW_STATUS.json",
        evidence / "CANDIDATE_INTERNAL_REVIEW_STATUS.json",
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(evidence).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("PHASE-1 CANDIDATE V3 ROUND-2 REVIEW FREEZE: PASS")
    print(
        json.dumps(
            {
                "verdict": review_cfg["round2_verdict"],
                "candidate_commit": review_cfg["candidate_commit"],
                "candidate_zip_sha256": review_cfg[
                    "candidate_zip_sha256"
                ],
                "candidate_manifest_entries_verified": (
                    candidate_manifest_count
                ),
                "source_snapshot_entries_verified": (
                    source_manifest_count
                ),
                "execution_authorized": False,
                "next_gate": review_cfg["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
