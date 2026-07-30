#!/usr/bin/env python3
"""Synchronize status and freeze the online-PF milestone evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN ONLINE MOVING-AVERAGE PF LOAD TRANSITIONS -->"
END = "<!-- END ONLINE MOVING-AVERAGE PF LOAD TRANSITIONS -->"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
        default="config/online_pf_load_transition_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    audit = json.loads(
        (results / "ONLINE_PF_LOAD_TRANSITION_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    decision = json.loads(
        (evidence / "ONLINE_PF_LOAD_TRANSITION_GATE_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    if decision["status"] != (
        "PASS_ONLINE_MOVING_AVERAGE_PF_LOAD_TRANSITION_ONE_SEED"
    ):
        raise ValueError("online-PF gate has not passed")

    for name in [
        "ONLINE_PF_CONTROLLER_SUMMARY.csv",
        "ONLINE_PF_TIME_SERIES.csv",
        "LOAD_PHASES.csv",
        "LOAD_STATE_BUILD_AUDIT.csv",
        "ONLINE_PF_THEOREM_CERTIFICATES.json",
        "ONLINE_PF_LOAD_TRANSITION_AUDIT.json",
        "FULL_LOAD_RZF_REPRODUCTION_VALIDATION.json",
    ]:
        shutil.copy2(results / name, evidence / name)
    shutil.copy2(
        ROOT / "docs/DELAYED_REACHABILITY_SAFETY_THEOREM.md",
        evidence / "DELAYED_REACHABILITY_SAFETY_THEOREM.md",
    )
    shutil.copy2(
        ROOT / "config/multi_seed_campaign_spec_v1.json",
        evidence / "MULTI_SEED_CAMPAIGN_SPEC_v1.json",
    )

    by_name = audit["controller_rows"]
    online = by_name["online_predictive_robust_1db"]
    dropped = by_name["online_predictive_robust_1db_two_drops"]
    robust3 = by_name["online_predictive_robust_3db"]
    myopic = by_name["online_myopic_robust_1db"]
    frozen = by_name["frozen_table_predictive_robust_1db"]
    static = by_name["static_robust_1db"]

    block = f"""{BEGIN}
## Online moving-average PF with deterministic load transitions

Validated one-seed load sequence:

- 118 five-second intervals over the 587-second pass;
- active users per phase: 228, 114, 228, 57, 171, 114;
- four recomputed local-RZF/load states;
- 100-second exponential moving-average PF time constant;
- one-update delay and 3 dB/update mode-attenuation slew.

Results:

- online delayed-myopic 1 dB upper-bound violation seconds:
  `{myopic['upper_bound_violation_seconds']}`;
- online predictive 1 dB violation seconds:
  `{online['upper_bound_violation_seconds']}`;
- online predictive 1 dB with two dropped commands:
  `{dropped['upper_bound_violation_seconds']}` violations and
  `{dropped['fail_safe_command_count']}` fail-safe commands;
- online predictive 3 dB violation seconds:
  `{robust3['upper_bound_violation_seconds']}`;
- all predictive active eligible-user floor violations: `0`;
- online 1 dB moving-PF utility: `{online['mean_moving_pf_utility']:.9f}`;
- frozen-table predictive moving-PF utility:
  `{frozen['mean_moving_pf_utility']:.9f}`;
- static robust moving-PF utility: `{static['mean_moving_pf_utility']:.9f}`.

The saturation statement of the finite-pass theorem is repaired by checking the
actual clipped candidate `F(q)=min(q+rho,Q)` against the next envelope. This
remains one seed, one pass, a deterministic load stress test, and an
uncalibrated uncertainty screen.

**Next gate:** `{cfg['next_gate']}`
{END}"""
    project = ROOT / "PROJECT_STATUS.md"
    project_text = (
        project.read_text(encoding="utf-8")
        if project.is_file()
        else "# Current Project Status\n"
    )
    project_text = replace_block(project_text, block)

    # Repair the older summary/current-gate sections so the status file has
    # one authoritative next gate rather than contradictory historical text.
    summary_start = project_text.find("## Status in one sentence")
    frozen_start = project_text.find("## Frozen successful gate", summary_start)
    if summary_start >= 0 and frozen_start > summary_start:
        summary = (
            "## Status in one sentence\n\n"
            "The public/modelled propagation and full-topology platform, "
            "constrained-PF predictive controller, finite-pass robust safety "
            "certificate, virtual-queue comparison, and deterministic "
            "online-PF load-transition milestone have passed as one-seed "
            "non-paper evidence. Calibrated uncertainty and the statistical "
            "multi-seed/multi-pass campaign remain open.\n\n"
        )
        project_text = (
            project_text[:summary_start]
            + summary
            + project_text[frozen_start:]
        )

    gate_start = project_text.find("## Current gate")
    open_start = project_text.find("## Open paper gates", gate_start)
    if gate_start >= 0 and open_start > gate_start:
        current = (
            "## Current gate\n\n"
            f"`{cfg['next_gate']}`\n\n"
            "## Immediate requirements\n\n"
            "1. Calibrate coupling, pointing, array, and ephemeris upper errors.\n"
            "2. Resolve the exact long-term regulatory functional.\n"
            "3. Independently review the immutable multi-seed campaign package before submission.\n"
            "4. Add stochastic traffic, layout rotations, O2I, finite-network, and practical-array sensitivity.\n"
            "5. Run paired multi-seed/multi-pass statistics only after those gates pass.\n\n"
        )
        project_text = (
            project_text[:gate_start]
            + current
            + project_text[open_start:]
        )

    project.write_text(project_text, encoding="utf-8")

    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        f"## Gate\n\n`{cfg['next_gate']}`\n\n"
        "## Required sequence\n\n"
        "1. Calibrate coupling, pointing, array, and ephemeris upper errors from held-out data or a declared deterministic engineering set; do not use the 1/3 dB smoke margins as paper evidence.\n"
        "2. Resolve and implement the exact long-term regulatory functional separately from the certified short-term constraint.\n"
        "3. Freeze one immutable multi-seed/multi-pass experiment package using `config/multi_seed_campaign_spec_v1.json`.\n"
        "4. Include stochastic arrivals/departures in addition to the deterministic rotating-load stress test.\n"
        "5. Include layout rotations, O2I stratification, finite-network sensitivity, a practical 64T64R primary case, and the 128-port digital upper reference.\n"
        "6. Launch the statistical campaign only after independent review of the calibration and campaign package.\n",
        encoding="utf-8",
    )

    state = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_ONLINE_MOVING_AVERAGE_PF_LOAD_TRANSITION_ONE_SEED",
        "paper_result": False,
        "active_user_floor_violations": 0,
        "online_predictive_1db_safe": True,
        "online_predictive_3db_safe": True,
        "two_message_drop_fail_safe_safe": True,
        "theorem_saturation_statement_repaired": True,
        "multi_seed_campaign_status": "SPECIFICATION_ONLY_NOT_SUBMITTED",
        "next_gate": cfg["next_gate"],
    }
    (ROOT / "config/online_pf_load_transition_validated_state_v1.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (evidence / "README.md").write_text(
        "# Online moving-average PF and load-transition milestone\n\n"
        "The validated one-seed milestone recomputes local RZF for deterministic user arrivals/departures, updates moving-average PF weights online, preserves the robust delayed safety certificate under 1 dB and 3 dB upper-coupling smoke margins, and safely handles two dropped commands.\n\n"
        "The result is not a paper result. Uncertainty calibration and the multi-seed/multi-pass campaign remain open.\n",
        encoding="utf-8",
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(f"{sha256_file(path)}  {path.as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("ONLINE PF LOAD-TRANSITION STATUS SYNC: PASS")
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
