#!/usr/bin/env python3
"""Update project status after freezing the fairness policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN FAIRNESS POLICY AUDIT -->"
END = "<!-- END FAIRNESS POLICY AUDIT -->"


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
        default="config/fairness_policy_audit_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    audit = json.loads(
        (
            ROOT
            / cfg["paths"]["results_dir"]
            / "FAIRNESS_POLICY_AUDIT.json"
        ).read_text(encoding="utf-8")
    )
    primary = audit["primary_policy_common_scale_check"]

    block = f"""{BEGIN}
## Fairness policy frozen before controller implementation

The controller objective is **constrained proportional fairness**, not network
sum rate.

Primary one-seed diagnostic policy:

- nominal serviceability threshold: 0.1 bit/s/Hz;
- eligible users: `{primary['eligible_user_count']}`;
- coverage-limited users: `{primary['coverage_limited_user_count']}`;
- eligible-user floor: `max(0.1 bit/s/Hz, 0.9 R_nominal)`;
- common-scale reference floor violations: `{primary['common_scale_controller_induced_floor_violation_count']}`;
- primary utility: `sum log(R_u + 0.001)`;
- report total-band/protected-band, absolute outage, fifth percentile, minimum,
  geometric mean, Jain index, and indoor/outdoor groups.

No indoor-specific optimization weight is assigned from the one-seed result,
because the nominal indoor/outdoor ordering is counterintuitive and must be
audited over multiple channel/topology seeds.

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
        "## Required controller objective\n\n"
        "1. Incumbent safety is a hard constraint.\n"
        "2. Report users below the nominal serviceability threshold separately "
        "as coverage-limited.\n"
        "3. For eligible users, minimize service-floor violations and normalized "
        "shortfall before maximizing proportional-fair utility.\n"
        "4. Do not use network sum rate as the primary objective or acceptance "
        "metric.\n"
        "5. Report absolute rates, outage, fifth percentile, minimum, geometric "
        "mean, Jain index, and indoor/outdoor groups for total and protected "
        "bands.\n"
        "6. Keep indoor/outdoor weights equal until a multi-seed O2I audit "
        "supports a different weighting.\n",
        encoding="utf-8",
    )
    print("FAIRNESS POLICY STATUS SYNC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
