#!/usr/bin/env python3
"""Synchronize status after the constrained-PF controller milestone."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN CONSTRAINED PF CONTROLLER MILESTONE -->"
END = "<!-- END CONSTRAINED PF CONTROLLER MILESTONE -->"


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
        default=(
            "config/"
            "constrained_pf_controller_milestone_v1.json"
        ),
    )
    args = parser.parse_args()
    cfg = json.loads(
        (ROOT / args.config).read_text(encoding="utf-8")
    )
    audit = json.loads(
        (
            ROOT
            / cfg["paths"]["results_dir"]
            / "CONSTRAINED_PF_CONTROLLER_AUDIT.json"
        ).read_text(encoding="utf-8")
    )
    rows = audit["controller_results"]
    myopic = rows["delayed_myopic_constrained_pf"]
    predictive = rows[
        "predictive_reachability_constrained_pf"
    ]
    static = rows["static_constrained_pf"]

    block = f"""{BEGIN}
## Constrained proportional-fair controller milestone

Primary frozen scenario:

- update interval: 5 s;
- message/action delay: 1 update;
- attenuation slew: 3 dB/update;
- predictive horizon: 10 updates;
- eligible users: 207;
- coverage-limited users reported separately: 21;
- eligible floor: `max(0.1, 0.9 R_nominal)` bit/s/Hz.

Results:

- delayed-myopic incumbent violation seconds:
  `{myopic['incumbent_violation_seconds']}`;
- predictive incumbent violation seconds:
  `{predictive['incumbent_violation_seconds']}`;
- predictive eligible-user floor violations:
  `{predictive['eligible_floor_violation_user_intervals']}`;
- predictive mean PF utility:
  `{predictive['mean_pf_utility']:.9f}`;
- static-safe mean PF utility:
  `{static['mean_pf_utility']:.9f}`;
- predictive mean eligible-user geometric rate:
  `{predictive['mean_geometric_rate_bps_hz']:.9f}` bit/s/Hz;
- static-safe mean eligible-user geometric rate:
  `{static['mean_geometric_rate_bps_hz']:.9f}` bit/s/Hz.

Network sum rate remains secondary. The milestone is one seed and does not yet
provide a formal delayed-safety theorem, virtual-queue baseline, uncertainty
calibration, or statistical paper evidence.

**Next gate:** `{cfg['next_gate']}`
{END}"""

    project = ROOT / "PROJECT_STATUS.md"
    current = (
        project.read_text(encoding="utf-8")
        if project.is_file()
        else "# Current Project Status\n"
    )
    updated = replace_block(current, block)
    current_gate = f"""## Current gate

`{cfg['next_gate']}`

## Immediate requirements

1. Formalize the delayed/reachability safety guarantee.
2. Add the virtual-queue baseline under the same fairness and actuation rules.
3. Add uncertainty, message age, and an explicit fail-safe.
4. Quantify frozen local-cost-table approximation error.
5. Expand the controller grid before any multi-seed campaign.
"""
    updated = re.sub(
        r"## Current gate\n.*?(?=\n## Open paper gates)",
        current_gate.rstrip(),
        updated,
        flags=re.S,
    )
    project.write_text(
        updated,
        encoding="utf-8",
    )

    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        f"## Gate\n\n`{cfg['next_gate']}`\n\n"
        "## Required sequence\n\n"
        "1. State and prove the finite-horizon delayed/reachability safety "
        "condition matching the implemented predictive filter, including "
        "initialization, forecast error, delay, and slew limits.\n"
        "2. Add a virtual-queue/Lyapunov baseline under the same information, "
        "delay, slew, service-floor, and uncertainty conditions.\n"
        "3. Add coupling-error and message-age uncertainty with an explicit "
        "local fail-safe and no hidden slack.\n"
        "4. Replace frozen nominal local action-cost tables with online local "
        "moving-average PF cost updates, or quantify their approximation gap.\n"
        "5. Expand the delay/slew/update grid and produce the primary "
        "safety-fairness ablation figures.\n"
        "6. Only after these gates pass, launch multi-seed and multi-pass "
        "experiments.\n",
        encoding="utf-8",
    )
    print("CONSTRAINED PF CONTROLLER STATUS SYNC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
