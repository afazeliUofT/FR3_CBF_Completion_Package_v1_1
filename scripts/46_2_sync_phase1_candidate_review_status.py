#!/usr/bin/env python3
"""Synchronize project status for the revised candidate v3."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN PHASE1 INDEPENDENT REVIEW ROUND1 -->"
END = "<!-- END PHASE1 INDEPENDENT REVIEW ROUND1 -->"


def replace_block(text: str, block: str) -> str:
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        stop = text.index(END, start) + len(END)
        return text[:start] + block + text[stop:]
    return block + "\n\n" + text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        default="config/phase1_campaign_contract_v3.json",
    )
    args = parser.parse_args()
    contract = json.loads(
        (ROOT / args.contract).read_text(encoding="utf-8")
    )

    block = f"""{BEGIN}
## Phase-1 independent review round 1

Candidate v2 at commit `f26af9f3ff595f6b6ae9b468c79683e53bc8b450`
passed architecture, five-pass provenance, manifest, and execution-lock checks,
but received:

`REQUIRES_REVISION_BEFORE_INDEPENDENT_PASS`

Candidate v3 now freezes:

- one primary declared envelope: 65 dB null cap and 3 dB uplift;
- exact method information/fallback classes;
- a reactive-myopic comparator with the same emergency fallback;
- exact variable-pass-length load semantics;
- a seed-cluster paired statistical plan with passes treated as fixed blocks;
- immutable source/config snapshots;
- one-channel-generation-per-seed compute DAG.

Campaign execution remains unauthorized.

**Next gate:** `{contract['next_gate']}`
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
        f"## Gate\n\n`{contract['next_gate']}`\n\n"
        "1. Keep campaign execution unauthorized.\n"
        "2. Independently review phase-1 candidate v3 against the round-1 "
        "blocking defects and the v3 method/statistical contracts.\n"
        "3. Return PASS or a precise remaining blocker.\n"
        "4. Only after independent PASS may an immutable Nibi job-array "
        "package be prepared.\n"
        "5. A separate execution authorization token is still required after "
        "job-package review.\n",
        encoding="utf-8",
    )

    print("PHASE-1 CANDIDATE V3 STATUS SYNC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
