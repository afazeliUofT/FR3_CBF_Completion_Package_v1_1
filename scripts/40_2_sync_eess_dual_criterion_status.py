#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BEGIN="<!-- BEGIN EESS DUAL CRITERION CORRECTION -->"
END="<!-- END EESS DUAL CRITERION CORRECTION -->"

def replace(text,block):
    if BEGIN in text and END in text:
        s=text.index(BEGIN); e=text.index(END,s)+len(END)
        return text[:s]+block+text[e:]
    return block+"\n\n"+text

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",default="config/eess_dual_criterion_audit_v1.json")
    a=p.parse_args()
    cfg=json.loads((ROOT/a.config).read_text())
    ev=ROOT/cfg["paths"]["evidence"]
    audit=json.loads((ev/"EESS_DUAL_CRITERION_AUDIT.json").read_text())
    short=audit["case_results"]["short_p0005_multiple"]["required_attenuation_db"]
    long=audit["case_results"]["long_p20_multiple"]["required_attenuation_db"]
    block=f"""{BEGIN}
## EESS dual-criterion correction

The historical controller platform combined P.452 `p=20%` with the
`-133 dBW/10 MHz` short-term threshold. It remains valid as algorithmic
one-seed evidence, but not as a final regulatory test.

The corrected percentile-matched terrestrial single-entry tests are:

- long term: P.452 `p=20%`, threshold `-150 dBW/10 MHz`;
- short term: P.452 `p=0.005%`, threshold `-133 dBW/10 MHz`;
- both criteria must be met.

No new P.452 or channel-generation job is needed. The existing all-sector table
already includes `p=0.005%`.

For the SA.509 multiple-entry aggregate-network pattern, required common
attenuation ranges are:

- short term: `{short['minimum']:.3f}` to `{short['maximum']:.3f}` dB;
- long term: `{long['minimum']:.3f}` to `{long['maximum']:.3f}` dB.

The current 60 dB action grid is insufficient for part of the long-term case.
A provisional 70 dB grid plus an exact hard-null endpoint is required for the
next local controller rerun. The SA.509 single-entry pattern is retained as a
+3 dB sensitivity.

**Next gate:** `{cfg['next_gate']}`
{END}"""
    project=ROOT/"PROJECT_STATUS.md"
    text=project.read_text(encoding="utf-8") if project.is_file() else "# Project Status\n"
    project.write_text(replace(text,block),encoding="utf-8")
    (ROOT/"NEXT_IMMEDIATE_STEP.md").write_text(
        "# Next Immediate Step\n\n"
        f"## Gate\n\n`{cfg['next_gate']}`\n\n"
        "1. Rebuild local coupling for P.452 p=0.005% short-term and p=20% long-term.\n"
        "2. Use exact -133 and -150 dBW/10 MHz thresholds; keep uncertainty margins separate.\n"
        "3. Extend the provisional action grid to 70 dB and include a hard-null endpoint.\n"
        "4. Rerun constrained online-PF static, myopic, virtual-queue, and predictive controllers under both criteria.\n"
        "5. Report SA.509 multiple-entry primary and single-entry +3 dB sensitivity.\n"
        "6. Do not launch multi-seed jobs until corrected one-seed fairness and recursive feasibility pass.\n",
        encoding="utf-8")
    print("EESS DUAL-CRITERION STATUS SYNC: PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
