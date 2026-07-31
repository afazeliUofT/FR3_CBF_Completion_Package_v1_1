#!/usr/bin/env python3
"""Synchronize project status after building the locked Nibi job package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN IMMUTABLE PHASE1 NIBI JOB PACKAGE -->"
END = "<!-- END IMMUTABLE PHASE1 NIBI JOB PACKAGE -->"


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
        default="config/phase1_nibi_job_package_builder_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    package = ROOT / cfg["paths"]["job_package_dir"]
    contract = json.loads(
        (package / "JOB_PACKAGE_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    smoke = json.loads(
        (
            ROOT
            / cfg["paths"]["local_smoke_dir"]
            / "EXACT_SLOT0_ALL8_METHOD_SMOKE_AUDIT.json"
        ).read_text(encoding="utf-8")
    )

    block = f"""{BEGIN}
## Immutable phase-1 Nibi job-package review candidate

- package ID: `{contract['package_id']}`;
- candidate-v3 SHA-256: `{contract['candidate_v3']['zip_sha256']}`;
- seeds / fixed passes / methods: `30 / 5 / 8`;
- channel-generation jobs: `30`, one channel per seed reused across passes and
  methods;
- reactive-myopic comparator with identical sector fallback: implemented and
  slot-0 smoke-tested;
- exact slot-0 all-eight-method smoke: `{smoke['status']}`;
- submission scripts: locked;
- campaign execution authorized: `NO`.

The package is ready only for independent source/package review. No Nibi job
has been submitted.

**Next gate:** `{cfg['next_gate']}`
{END}"""
    project = ROOT / "PROJECT_STATUS.md"
    current = (
        project.read_text(encoding="utf-8")
        if project.is_file()
        else "# Current Project Status\n"
    )
    project.write_text(
        replace_block(current, block), encoding="utf-8"
    )
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        f"## Gate\n\n`{cfg['next_gate']}`\n\n"
        "1. Keep all Nibi submission scripts locked.\n"
        "2. Independently review the immutable job package, reactive-myopic "
        "implementation, result schemas, merge analysis, manifests, and "
        "authorization checks.\n"
        "3. Return PASS or a precise blocking defect.\n"
        "4. Only after job-package PASS may a separate execution token and "
        "local WSL-to-Nibi orchestrator be prepared.\n"
        "5. No cluster command is authorized by this stage.\n",
        encoding="utf-8",
    )
    print("PHASE-1 NIBI JOB-PACKAGE STATUS SYNC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
