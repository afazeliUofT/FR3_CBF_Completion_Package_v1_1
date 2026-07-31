#!/usr/bin/env python3
"""Strict validation of the job-package independent-review record."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review",
        default="config/phase1_nibi_job_package_independent_review_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.review).read_text(encoding="utf-8"))
    evidence = ROOT / "evidence/phase1_nibi_job_package_independent_review_v1"
    verdict = json.loads(
        (
            evidence
            / "PHASE1_JOB_PACKAGE_INDEPENDENT_REVIEW_VERDICT.json"
        ).read_text(encoding="utf-8")
    )

    assert verdict["status"] == (
        "PASS_PHASE1_JOB_PACKAGE_FOR_NIBI_DEPLOYMENT_SMOKE_"
        "PREPARATION_NOT_FULL_CAMPAIGN_EXECUTION"
    )
    assert verdict["verdict"] == cfg["verdict"]
    assert verdict["reviewed_commit"] == (
        "20d65eeb0fcc53f649a4f3f716fa2780406b4810"
    )
    assert verdict["reviewed_package_id"] == (
        "bd18734787de7396b9de4bf8c0b9ba4d191c6346a7cb83e969499622067a8129"
    )
    assert verdict["campaign_execution_authorized"] is False
    assert verdict["full_30_seed_execution_authorized"] is False
    assert verdict["package_manifest_entries_verified"] >= 70
    assert verdict["new_source_manifest_entries_verified"] == 14
    assert verdict["candidate_snapshot_entries_verified"] == 14
    assert len(verdict["mandatory_before_noncampaign_nibi_smoke"]) >= 5
    assert len(verdict["mandatory_before_full_30_seed_execution"]) >= 6

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    count = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = evidence / relative
        assert path.is_file()
        assert sha256_file(path) == expected
        count += 1
    assert count >= 7

    print("PHASE-1 JOB-PACKAGE INDEPENDENT REVIEW STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "verdict": verdict["verdict"],
                "package_id": verdict["reviewed_package_id"],
                "full_campaign_authorized": False,
                "next_gate": verdict["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
