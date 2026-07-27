#!/usr/bin/env python3
"""Freeze the next standards-aligned distributed local-channel experiment."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from _bootstrap import ROOT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/distributed_channel_readiness.yaml"
    )
    args = parser.parse_args()
    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    out = ROOT / cfg["outputs"]["work_dir"]
    out.mkdir(parents=True, exist_ok=True)

    snapshot = ROOT / cfg["outputs"]["source_snapshot_dir"] / "SNAPSHOT_METADATA.json"
    review = out / "DISTRIBUTED_ARCHITECTURE_INDEPENDENT_REVIEW.json"
    if not snapshot.is_file() or not review.is_file():
        raise FileNotFoundError("Architecture review or channel snapshot is missing")

    snapshot_data = json.loads(snapshot.read_text(encoding="utf-8"))
    review_data = json.loads(review.read_text(encoding="utf-8"))
    if snapshot_data["status"] != "PASS_REVIEW_REQUIRED":
        raise ValueError("Source snapshot did not pass")
    if review_data["status"] != "PASS_WITH_REQUIRED_PAPER_EXPERIMENT":
        raise ValueError("Architecture independent review did not pass")

    specification = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN_FOR_CODE_LEVEL_CHANNEL_BASELINE_REVIEW",
        "claim_boundary": cfg["claim_boundary"]["experiment_freeze"],
        "method_name": cfg["method_naming"]["paper_name"],
        "method_acronym": cfg["method_naming"]["acronym"],
        "standards_and_model": cfg["paper_experiment"]["standards"],
        "scenario": {
            key: value
            for key, value in cfg["paper_experiment"].items()
            if key not in {"standards", "next_gate"}
        },
        "hard_requirements_before_paper_run": [
            "Select and pin one validated channel implementation after code/environment review.",
            "Map the selected implementation to ETSI TR 138 901 V19.4.0 assumptions used at 8.15 GHz.",
            "Include inter-cell UE interference in all rate metrics.",
            "Use actual rate-limited budget updates and message delays.",
            "Use identical information and update limits for all controllers.",
            "Re-verify actual transmitted hybrid/codebook beams when applicable.",
            "Retain full-load stress results only as a sensitivity envelope.",
            "Use multiple passes, seeds, load levels, and uncertainty epochs.",
        ],
        "source_snapshot": {
            "metadata": str(snapshot.relative_to(ROOT)),
            "source_root": snapshot_data["source_root"],
            "selected_text_file_count": snapshot_data[
                "selected_text_file_count"
            ],
        },
        "next_gate": cfg["paper_experiment"]["next_gate"],
    }
    (out / "STANDARDS_ALIGNED_DLP_RZF_EXPERIMENT_SPEC.json").write_text(
        json.dumps(specification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    (out / "STANDARDS_ALIGNED_DLP_RZF_EXPERIMENT_SPEC.md").write_text(
        "# Standards-aligned distributed local-channel experiment\n\n"
        f"- Status: `{specification['status']}`\n"
        f"- Proposed method: `{specification['method_name']}` "
        f"(`{specification['method_acronym']}`)\n"
        "- Primary channel scenario: `UMa`\n"
        "- Sensitivity scenario: `UMi street canyon`\n"
        "- Carrier: `8.15 GHz`\n"
        "- Bandwidth: `100 MHz`\n"
        "- Topology: `19 sites / 57 sectors`\n"
        "- Channel reference: `ETSI TR 138 901 V19.4.0 (Release 19)`\n"
        "- Implementation: not frozen until source/environment review\n\n"
        "The next review must decide whether the legacy Sionna 0.19.2 channel "
        "stack can be audited and retained, or whether the experiment should "
        "migrate to Sionna 2.0.1. No performance claim is permitted before that "
        "decision and an executable pilot.\n",
        encoding="utf-8",
    )

    print("STANDARDS-ALIGNED DLP-RZF EXPERIMENT FREEZE: PASS")
    print(json.dumps(specification, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
