#!/usr/bin/env python3
"""Synchronize project status after smoke-package preparation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN NONCAMPAIGN NIBI DEPLOYMENT SMOKE -->"
END = "<!-- END NONCAMPAIGN NIBI DEPLOYMENT SMOKE -->"


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
        default="config/phase1_nibi_deployment_smoke_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    smoke_root = ROOT / cfg["paths"]["smoke_package_dir"]
    contract = json.loads(
        (smoke_root / "SMOKE_PACKAGE_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    binding = json.loads(
        (smoke_root / "SMOKE_ZIP_BINDING.json").read_text(
            encoding="utf-8"
        )
    )

    block = f"""{BEGIN}
## Noncampaign Nibi deployment smoke

- smoke-package ID: `{contract['smoke_package_id']}`;
- smoke ZIP SHA-256: `{binding['zip_sha256']}`;
- excluded smoke seed: `{contract['smoke_seed']}`;
- execution scope: `NONCAMPAIGN_SINGLE_SEED_SMOKE_ONLY`;
- confirmatory analysis included: `NO`;
- 30-seed phase-1 execution authorized: `NO`;
- merge authorized: `NO`.

The reviewed smoke orchestrator may submit exactly one non-array H100 job,
freeze the exact Nibi environment before token creation, and retrieve complete
success or diagnostic provenance.

**Next gate:** `{cfg['next_gate']}`
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
        newline="\n",
    )
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        f"## Gate\n\n`{cfg['next_gate']}`\n\n"
        "1. Execute exactly one smoke-scoped H100 job for excluded seed 43999.\n"
        "2. Retrieve and validate the compact success or diagnostic return.\n"
        "3. Keep all 30 confirmatory seeds and merge locked.\n"
        "4. Independently review the Nibi environment, Slurm record, channel "
        "fingerprints, and all-eight-method smoke output.\n"
        "5. Only after smoke PASS may a full-campaign orchestrator and "
        "campaign-scoped token be prepared.\n",
        encoding="utf-8",
        newline="\n",
    )
    print("NONCAMPAIGN NIBI DEPLOYMENT SMOKE STATUS SYNC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
