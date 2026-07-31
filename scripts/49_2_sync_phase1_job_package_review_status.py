#!/usr/bin/env python3
"""Synchronize project status after independent job-package review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN PHASE1 JOB PACKAGE INDEPENDENT REVIEW -->"
END = "<!-- END PHASE1 JOB PACKAGE INDEPENDENT REVIEW -->"


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
        default="config/phase1_nibi_job_package_independent_review_v1.json",
    )
    args = parser.parse_args()
    review = json.loads(
        (ROOT / args.review).read_text(encoding="utf-8")
    )

    block = f"""{BEGIN}
## Phase-1 immutable Nibi job-package independent review

- reviewed commit: `{review['reviewed_commit']}`;
- package ID: `{review['reviewed_package_id']}`;
- job-package SHA-256: `{review['reviewed_job_package_sha256']}`;
- verdict:
  `PASS_FOR_NIBI_DEPLOYMENT_SMOKE_PREPARATION_NOT_FULL_CAMPAIGN_EXECUTION`;
- 30-seed phase-1 execution authorized: `NO`.

The immutable package passes local source, manifest, method, merge, result-schema,
and execution-lock review. Before any confirmatory campaign, a noncampaign Nibi
deployment smoke must freeze the exact environment, use a smoke-scoped token,
and return complete Slurm/environment/package provenance.

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
        "1. Build a separately reviewed smoke-only WSL-to-Nibi orchestrator.\n"
        "2. Use a noncampaign seed outside 44000--44029.\n"
        "3. Freeze and hash the exact Nibi software/GPU environment.\n"
        "4. Issue a smoke-scoped token bound to package, commit, environment, "
        "seed, stage, and expiry.\n"
        "5. Submit exactly one H100 smoke job and retrieve complete provenance.\n"
        "6. Independently review the smoke before building the full-campaign "
        "orchestrator or issuing a 30-seed token.\n",
        encoding="utf-8",
    )
    print("PHASE-1 JOB-PACKAGE REVIEW STATUS SYNC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
