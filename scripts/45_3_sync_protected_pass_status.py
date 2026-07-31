#!/usr/bin/env python3
"""Synchronize status after completing all five pass records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN FIVE PROTECTED PASS RECORDS -->"
END = "<!-- END FIVE PROTECTED PASS RECORDS -->"


def replace_block(text: str, block: str) -> str:
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        stop = text.index(END, start) + len(END)
        return text[:start] + block + text[stop:]
    return block + "\n\n" + text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/protected_pass_records_phase1_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    records = ROOT / cfg["paths"]["pass_records_dir"]
    index = json.loads(
        (records / "PASS_RECORD_INDEX.json").read_text(encoding="utf-8")
    )
    block = f"""{BEGIN}
## Five immutable protected-pass records

- pass records ready: `5 / 5`;
- selection: four predeclared consecutive UTC peak dates after slot 0;
- daily rule: highest complete visible pass by peak elevation before any
  controller calculation;
- orbit engine: Skyfield;
- TLE policy: exact archived slot-0 TLE, with age checked against the frozen
  14-day limit;
- criteria per pass: long/short P.452 percentile pairing and both SA.509
  multiple-/single-entry patterns;
- campaign execution authorized: `NO`.

These passes provide temporal geometry diversity under one archived orbital
record. They do not constitute independent ephemeris-error calibration.

**Next gate:** `{cfg['next_gate']}`
{END}"""
    project = ROOT / "PROJECT_STATUS.md"
    text = (
        project.read_text(encoding="utf-8")
        if project.is_file()
        else "# Current Project Status\n"
    )
    project.write_text(
        replace_block(text, block),
        encoding="utf-8",
    )
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        f"## Gate\n\n`{cfg['next_gate']}`\n\n"
        "1. Keep campaign execution unauthorized.\n"
        "2. Independently review the complete five-pass phase-1 candidate.\n"
        "3. Verify architecture mapping, pass provenance, exact safety/floor "
        "accounting, paired methods, statistics, and execution locks.\n"
        "4. Return PASS or a precise blocking defect.\n"
        "5. Only after independent PASS may a separate Nibi job-array package "
        "be prepared; no execution authorization is granted by this stage.\n",
        encoding="utf-8",
    )
    print("PROTECTED-PASS STATUS SYNC: PASS")
    print(json.dumps(index, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
