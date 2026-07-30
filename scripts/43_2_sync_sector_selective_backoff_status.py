#!/usr/bin/env python3
"""Synchronize project status after the sector-selective fallback audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN DECLARED ENVELOPE SECTOR BACKOFF -->"
END = "<!-- END DECLARED ENVELOPE SECTOR BACKOFF -->"


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
        default="config/sector_selective_backoff_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    audit = json.loads(
        (results / "SECTOR_BACKOFF_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    primary = audit["primary_decisive_screen"]
    selective = primary["sector_selective"]
    uniform = primary["uniform"]
    boundary = audit["boundary_screen_sector_selective"]

    block = "\n".join(
        [
            BEGIN,
            "## Declared-envelope sector-selective protected-tone fallback",
            "",
            "Measured OTA array/CSI calibration remains unavailable. The project",
            "therefore freezes explicit deterministic engineering scenarios rather",
            "than claiming a calibrated physical uncertainty distribution.",
            "",
            "Primary long-term SA.509 single-entry engineering screen:",
            "",
            "- null-depth cap: `65 dB`;",
            "- residual normalized-coupling uplift: `3 dB`;",
            "- sector-selective long-term violation seconds: "
            f"`{selective['long_violation_seconds']}`;",
            "- sector-selective paired short-term violation seconds: "
            f"`{selective['paired_short_violation_seconds']}`;",
            "- sector-selective eligible-user floor violations: "
            f"`{selective['eligible_floor_violation_user_intervals']}`;",
            "- uniform-backoff eligible-user floor violations: "
            f"`{uniform['eligible_floor_violation_user_intervals']}`;",
            "- sector-selective mean PF utility: "
            f"`{selective['mean_moving_pf_utility']:.9f}`;",
            "- uniform-backoff mean PF utility: "
            f"`{uniform['mean_moving_pf_utility']:.9f}`;",
            "- sector-selective mean protected-band retention: "
            f"`{selective['mean_protected_network_retention']:.6%}`;",
            "- uniform-backoff mean protected-band retention: "
            f"`{uniform['mean_protected_network_retention']:.6%}`.",
            "",
            "The 60 dB + 3 dB boundary case is safety-feasible only by using",
            "the explicit sector fail-safe and still causes "
            f"`{boundary['eligible_floor_violation_user_intervals']}` eligible-user "
            "floor violations. This shows that the deterministic scenario matrix",
            "does not replace practical calibration or architecture mapping.",
            "",
            "The multi-seed campaign remains unauthorized.",
            "",
            f"**Next gate:** `{cfg['next_gate']}`",
            END,
        ]
    )

    project_path = ROOT / "PROJECT_STATUS.md"
    project_text = (
        project_path.read_text(encoding="utf-8")
        if project_path.is_file()
        else "# Current Project Status\n"
    )
    project_path.write_text(
        replace_block(project_text, block),
        encoding="utf-8",
    )

    next_step = "\n".join(
        [
            "# Next Immediate Step",
            "",
            "## Gate",
            "",
            f"`{cfg['next_gate']}`",
            "",
            "1. Keep the multi-seed campaign unauthorized.",
            "2. Map the protected-mode and sector-backoff actions to a practical "
            "64T64R or hybrid architecture, including RF-chain count, digital/RF "
            "degrees of freedom, quantization, achievable null floor, and local "
            "fallback latency.",
            "3. Treat the 60/65/67 dB caps and 0/1/3 dB uplifts only as declared "
            "engineering scenarios unless measured or source-referenced data are "
            "obtained.",
            "4. Freeze one immutable phase-1 campaign bundle with the practical "
            "architecture, sector-selective fallback, paired methods, seeds, passes, "
            "metrics, checksums, and stop/go rules.",
            "5. Independently review that bundle before any Nibi submission.",
            "",
        ]
    )
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        next_step,
        encoding="utf-8",
    )

    state = {
        "schema_version": 1,
        "status": (
            "PASS_DECLARED_ENGINEERING_ENVELOPE_SECTOR_BACKOFF_ONE_SEED"
        ),
        "measured_array_csi_calibration": False,
        "declared_engineering_scenarios": True,
        "sector_selective_fallback_implemented": True,
        "primary_long_safe": (
            selective["long_violation_seconds"] == 0
        ),
        "primary_short_safe": (
            selective["paired_short_violation_seconds"] == 0
        ),
        "primary_eligible_floor_violations": selective[
            "eligible_floor_violation_user_intervals"
        ],
        "uniform_primary_floor_violations": uniform[
            "eligible_floor_violation_user_intervals"
        ],
        "campaign_execution_authorized": False,
        "paper_result": False,
        "regulatory_compliance_result": False,
        "next_gate": cfg["next_gate"],
    }
    state_path = ROOT / "config/sector_selective_backoff_state_v1.json"
    state_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("SECTOR-SELECTIVE BACKOFF STATUS SYNC: PASS")
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
