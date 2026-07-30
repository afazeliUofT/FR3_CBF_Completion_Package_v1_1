#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN PRACTICAL 64T64R ARCHITECTURE -->"
END = "<!-- END PRACTICAL 64T64R ARCHITECTURE -->"

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
        default="config/practical_architecture_mapping_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    gate = json.loads(
        (ROOT / cfg["paths"]["evidence_dir"] / "ARCHITECTURE_GATE_DECISION.json").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (ROOT / cfg["paths"]["results_dir"] / "PRACTICAL_ARCHITECTURE_MAPPING_AUDIT.json").read_text(encoding="utf-8")
    )
    primary = audit["selected_primary"]
    hybrid = audit["hybrid_sensitivity"]
    block = (
        f"{BEGIN}\n"
        "## Generic practical 64T64R architecture mapping\n\n"
        "- selected primary: `generic_64t64r_subarray_6bit`;\n"
        "- 64 RF chains over 128 polarization ports using 32 dual-polarized disjoint subarrays;\n"
        f"- nominal network-sum retention versus 128-port upper reference: `{primary['nominal_sum_rate_retention_vs_128']:.6%}`;\n"
        f"- primary safety violations: `{primary['hard_safety_violation_seconds']}`;\n"
        f"- primary eligible-floor violations: `{primary['eligible_floor_violation_user_intervals']}`;\n"
        f"- minimum digital nullspace dimension: `{primary['minimum_available_digital_nullspace_dimension']}`;\n"
        f"- 32-RF-chain sensitivity floor violations: `{hybrid['eligible_floor_violation_user_intervals']}`.\n\n"
        "This is a generic declared architecture, not a vendor-product or calibrated-hardware model. "
        "The phase-1 campaign review candidate is execution-blocked until four additional protected-pass "
        "records and independent review are available.\n\n"
        f"**Next gate:** `{cfg['next_gate']}`\n"
        f"{END}"
    )
    project = ROOT / "PROJECT_STATUS.md"
    current = project.read_text(encoding="utf-8") if project.exists() else "# Status\n"
    project.write_text(replace_block(current, block), encoding="utf-8")
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        "## Gate\n\n"
        f"`{cfg['next_gate']}`\n\n"
        "1. Keep campaign execution unauthorized.\n"
        "2. Independently review the generic 64T64R mapping and immutable phase-1 candidate bundle.\n"
        "3. Acquire four additional protected-pass records with TLE/source/pattern hashes.\n"
        "4. Replace every missing pass slot and rebuild the immutable campaign bundle.\n"
        "5. Only after independent PASS, prepare the Nibi job-array package.\n",
        encoding="utf-8",
    )
    print("PRACTICAL ARCHITECTURE STATUS SYNC: PASS")
    print(json.dumps(gate, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
