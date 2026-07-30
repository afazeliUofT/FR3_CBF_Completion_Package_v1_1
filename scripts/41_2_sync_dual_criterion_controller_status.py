#!/usr/bin/env python3
"""Synchronize project status after corrected dual-criterion controller rerun."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN CORRECTED DUAL-CRITERION CONTROLLERS -->"
END = "<!-- END CORRECTED DUAL-CRITERION CONTROLLERS -->"


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
        default="config/dual_criterion_controller_reevaluation_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    audit = json.loads(
        (
            ROOT
            / cfg["paths"]["results_dir"]
            / "DUAL_CRITERION_CONTROLLER_AUDIT.json"
        ).read_text(encoding="utf-8")
    )
    decisive = audit["decisive_results"]
    long_multiple = decisive["long_multiple"]
    long_single = decisive["long_single"]
    short_multiple = decisive["short_multiple"]

    block = f"""{BEGIN}
## Corrected EESS dual-criterion controller reevaluation

The online constrained-PF controller platform has been rerun locally with:

- short term: P.452 `p=0.005%`, `-133 dBW/10 MHz`;
- long term: P.452 `p=20%`, `-150 dBW/10 MHz`;
- SA.509 multiple-entry primary pattern;
- SA.509 single-entry `+3 dB` sensitivity;
- provisional ideal-digital action grid `0--70 dB`;
- exact hard-null upper reference.

Primary long-term multiple-entry result:

- delayed-myopic violation seconds:
  `{long_multiple['myopic_violation_seconds']}`;
- predictive violation seconds:
  `{long_multiple['predictive_violation_seconds']}`;
- predictive PF utility:
  `{long_multiple['predictive_mean_moving_pf_utility']:.9f}`;
- static PF utility:
  `{long_multiple['static_mean_moving_pf_utility']:.9f}`;
- predictive mean protected-band retention:
  `{long_multiple['predictive_mean_protected_retention']:.6%}`;
- predictive minimum eligible-user floor ratio:
  `{long_multiple['predictive_minimum_floor_ratio']:.6f}`.

Single-entry long-term sensitivity:

- delayed-myopic violation seconds:
  `{long_single['myopic_violation_seconds']}`;
- predictive violation seconds:
  `{long_single['predictive_violation_seconds']}`;
- predictive PF utility:
  `{long_single['predictive_mean_moving_pf_utility']:.9f}`.

The long-term normalized constraint elementwise dominates the paired short-term
constraint by at least
`{audit['dominance']['multiple']['minimum_long_dominance_margin_db']:.3f} dB`
in this deterministic percentile-matched model. The short-term runs remain
reported separately for transparency.

All predictive cases and the 70 dB terminal action pass the finite-pass safety
certificate with zero eligible-user floor violations. This remains an ideal
one-seed engineering compatibility result, not regulatory-compliance evidence
or a paper result.

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
    )

    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        "## Gate\n\n"
        f"`{cfg['next_gate']}`\n\n"
        "1. Do not launch the multi-seed campaign yet.\n"
        "2. Convert the ideal 60--70 dB spatial-mode attenuation requirement "
        "into explicit array/CSI/quantization null-depth sensitivity cases.\n"
        "3. Separate source-referenced deterministic engineering bounds from "
        "held-out calibrated uncertainty; do not relabel 1/3 dB smoke tests.\n"
        "4. Quantify whether a practical 64T64R or hybrid architecture can meet "
        "the long-term criterion without hidden power shutdown.\n"
        "5. Freeze a phased paired campaign: primary seed/pass block first, "
        "then rotations, loads, delays, O2I, pattern, and array sensitivities.\n"
        "6. Preserve both inactive-user PF semantics: backlogged-unscheduled "
        "decay and departed-user removal/freeze.\n",
        encoding="utf-8",
    )

    state = {
        "schema_version": 1,
        "status": "PASS_CORRECTED_DUAL_CRITERION_CONTROLLER_ONE_SEED",
        "paper_result": False,
        "regulatory_compliance_result": False,
        "short_term_controller_rerun": True,
        "long_term_controller_rerun": True,
        "single_entry_pattern_sensitivity": True,
        "q70_terminal_safe": True,
        "hard_null_reference_evaluated": True,
        "physical_null_depth_calibrated": False,
        "next_gate": cfg["next_gate"],
    }
    (ROOT / "config/dual_criterion_controller_validated_state_v1.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("CORRECTED DUAL-CRITERION STATUS SYNC: PASS")
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
