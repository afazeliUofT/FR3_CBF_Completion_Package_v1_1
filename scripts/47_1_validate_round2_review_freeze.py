#!/usr/bin/env python3
"""Strict validation of the external round-2 review freeze."""
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
        default="config/phase1_candidate_v3_round2_review_v1.json",
    )
    args = parser.parse_args()
    config = json.loads(
        (ROOT / args.review).read_text(encoding="utf-8")
    )
    evidence = ROOT / "evidence/phase1_candidate_v3_round2_review"
    verdict = json.loads(
        (evidence / "PHASE1_ROUND2_REVIEW_VERDICT.json").read_text(
            encoding="utf-8"
        )
    )

    assert verdict["status"] == (
        "PASS_PHASE1_CANDIDATE_V3_FOR_IMMUTABLE_"
        "JOB_PACKAGE_PREPARATION_NOT_EXECUTION"
    )
    assert verdict["round2_verdict"] == (
        "PASS_FOR_IMMUTABLE_JOB_PACKAGE_PREPARATION_NOT_EXECUTION"
    )
    assert verdict["candidate_commit"] == (
        "be9053dd18deaeef6ab87597e706ab45092ea8cf"
    )
    assert verdict["candidate_zip_sha256"] == config[
        "candidate_zip_sha256"
    ]
    assert verdict["campaign_execution_authorized"] is False
    assert verdict["execution_lock_exit_code"] == 64
    assert verdict["candidate_manifest_entries_verified"] >= 30
    assert verdict["source_snapshot_entries_verified"] >= 14
    assert len(verdict["mandatory_job_package_gates"]) >= 6

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

    print("PHASE-1 ROUND-2 REVIEW STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "verdict": verdict["round2_verdict"],
                "candidate_commit": verdict["candidate_commit"],
                "execution_authorized": False,
                "next_gate": verdict["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
