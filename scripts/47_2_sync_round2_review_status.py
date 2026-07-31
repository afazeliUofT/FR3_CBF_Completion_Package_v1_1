#!/usr/bin/env python3
"""Update project status after the candidate-v3 round-2 review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN PHASE1 INDEPENDENT REVIEW ROUND2 -->"
END = "<!-- END PHASE1 INDEPENDENT REVIEW ROUND2 -->"


def replace_block(text: str, block: str) -> str:
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        stop = text.index(END, start) + len(END)
        return text[:start] + block + text[stop:]
    return block + "\n\n" + text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review",
        default="config/phase1_candidate_v3_round2_review_v1.json",
    )
    args = parser.parse_args()
    review = json.loads(
        (ROOT / args.review).read_text(encoding="utf-8")
    )

    block = f"""{BEGIN}
## Phase-1 independent review round 2

Candidate v3:

- commit: `{review['candidate_commit']}`;
- ZIP SHA-256: `{review['candidate_zip_sha256']}`;
- verdict:
  `PASS_FOR_IMMUTABLE_JOB_PACKAGE_PREPARATION_NOT_EXECUTION`;
- campaign execution authorized: `NO`.

The campaign contract, fixed-pass statistical plan, method information classes,
source snapshot, compute DAG, five pass records, and execution locks pass
review. The immutable job package must implement the reactive-myopic fallback,
use the v3 contract as the sole canonical source, preserve channel reuse, and
pass a separate independent review before any execution token is issued.

**Next gate:** `{review['next_gate']}`
{END}"""

    project = ROOT / "PROJECT_STATUS.md"
    current = (
        project.read_text(encoding="utf-8")
        if project.is_file()
        else "# Current Project Status\n"
    )
    project.write_text(
        replace_block(current, block),
        encoding="utf-8",
    )

    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        f"## Gate\n\n`{review['next_gate']}`\n\n"
        "1. Build an immutable, non-executable Nibi job-array package from "
        "candidate-v3 hashes.\n"
        "2. Implement and test the reactive-myopic sector-fallback comparator.\n"
        "3. Generate each of the 30 cellular channel seeds once and reuse it "
        "across all five passes and eight methods.\n"
        "4. Include local smoke tests, result schemas, merge/finalization "
        "scripts, and exact SHA-256 manifests.\n"
        "5. Keep every submission command locked.\n"
        "6. Independently review the job package; only a later explicit token "
        "may authorize Nibi execution.\n",
        encoding="utf-8",
    )
    print("PHASE-1 ROUND-2 REVIEW STATUS SYNC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
