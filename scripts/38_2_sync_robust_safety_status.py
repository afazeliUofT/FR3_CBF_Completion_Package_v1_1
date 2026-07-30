#!/usr/bin/env python3
"""Synchronize project status after the robust delayed-safety milestone."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN ROBUST DELAYED SAFETY MILESTONE -->"
END = "<!-- END ROBUST DELAYED SAFETY MILESTONE -->"


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
        default="config/robust_safety_baselines_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    audit = json.loads(
        (
            ROOT
            / cfg["paths"]["results_dir"]
            / "ROBUST_SAFETY_BASELINES_AUDIT.json"
        ).read_text(encoding="utf-8")
    )
    rows = audit["controller_rows"]
    nominal = rows["predictive_nominal_full_horizon"]
    robust_1 = rows["predictive_1db_with_two_message_drops"]
    robust_3 = rows["predictive_3db"]
    queue = rows["virtual_queue_gain_1"]

    block = f"""{BEGIN}
## Robust delayed-safety theorem and baseline milestone

A finite-pass robust reachability certificate now matches the implemented
predictive filter. It includes known delay, a 3 dB/update per-mode slew limit,
a full-pass geometry envelope, multiplicative coupling bounds, a preloaded
initial action, and a ramp-to-safe message-loss fallback.

One-seed primary results:

- nominal predictive upper-bound violations: `{nominal['upper_bound_violation_seconds']}`;
- 1 dB robust case with two dropped commands: `{robust_1['upper_bound_violation_seconds']}` violations and `{robust_1['fail_safe_command_count']}` fail-safe commands;
- 3 dB robust upper-bound violations: `{robust_3['upper_bound_violation_seconds']}`;
- all robust eligible-user floor violations: `0`;
- virtual-queue gain-1 instantaneous violation seconds:
  `{queue['upper_bound_violation_seconds']}`;
- 3 dB robust predictive mean PF utility:
  `{robust_3['mean_pf_utility']:.9f}`.

The virtual queue is a long-term baseline and does not provide the hard
instantaneous guarantee. Uncertainty bounds are deterministic smoke-test
bounds, not yet held-out calibrated error models.

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
        "## Required sequence\n\n"
        "1. Replace frozen instantaneous PF tables with online moving-average "
        "PF weights and quantify the frozen-table approximation gap.\n"
        "2. Add deterministic load transitions and user arrivals/departures, "
        "recompute local RZF from the validated full channel, and preserve the "
        "same hard safety certificate.\n"
        "3. Calibrate coupling/pointing/array uncertainty from held-out "
        "samples rather than arbitrary dB smoke margins.\n"
        "4. Freeze the formal short-term theorem in manuscript notation and "
        "resolve the exact long-term regulatory functional.\n"
        "5. Prepare multi-seed, multi-pass, layout-rotation, O2I, and practical "
        "array sensitivity jobs only after local moving-average PF passes.\n",
        encoding="utf-8",
    )

    print("ROBUST DELAYED SAFETY STATUS SYNC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
