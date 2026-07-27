from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from _bootstrap import ROOT
from fr3_cbf.io import load_yaml, write_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a reviewed S1 engineering-decision YAML")
    parser.add_argument("--candidate-db", type=float, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--decision-note", required=True)
    parser.add_argument("--accept-reviewed-warnings", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("Refusing to freeze without --confirm")
    if len(args.decision_note.strip()) < 20:
        raise SystemExit("Decision note is too short for an auditable engineering decision")

    cfg = load_yaml(ROOT / "config/s1_adequacy.yaml")
    out_dir = ROOT / cfg["output_dir"]
    audit_path = out_dir / "audit.json"
    summary_path = out_dir / "candidate_summary.csv"
    sensitivity_path = out_dir / "sensitivity_summary.csv"
    if not all(p.exists() for p in [audit_path, summary_path, sensitivity_path]):
        raise SystemExit("Real nominal and sensitivity outputs are required before freezing")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("mode") != "real":
        raise SystemExit("Refusing to freeze a candidate from a demo run")

    summary = pd.read_csv(summary_path)
    row = summary[summary["candidate_i_over_n_db"] == args.candidate_db]
    if row.empty or not bool(row.iloc[0]["all_links_pass"]):
        raise SystemExit("Candidate did not pass every nominal link allocation")
    warning_count = int(row.iloc[0]["links_with_warnings"])
    if warning_count and not args.accept_reviewed_warnings:
        raise SystemExit(
            f"Candidate has {warning_count} link-candidate warning records. Review and re-run with --accept-reviewed-warnings only if resolved."
        )

    sens = pd.read_csv(sensitivity_path)
    srow = sens[sens["candidate_i_over_n_db"] == args.candidate_db]
    if srow.empty or not bool(srow.iloc[0]["all_scenarios_pass"]):
        raise SystemExit("Candidate did not pass every predeclared sensitivity scenario")

    decision = {
        "metadata": {
            "status": "PROJECT_ENGINEERING_DECISION",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "reviewer": args.reviewer,
            "decision_note": args.decision_note,
            "not_a_regulatory_rule": True,
        },
        "fixed_service_short_term_engineering_cap": {
            "metric": "I_over_N_dB",
            "limit_db": float(args.candidate_db),
            "evidence": {
                "nominal_all_links_pass": True,
                "sensitivity_all_scenarios_pass": True,
                "reviewed_warnings_accepted": bool(args.accept_reviewed_warnings),
                "audit_file": str(audit_path.relative_to(ROOT)),
                "summary_file": str(summary_path.relative_to(ROOT)),
                "sensitivity_file": str(sensitivity_path.relative_to(ROOT)),
            },
            "claim_boundary": "This value is frozen for the paper configuration only and is not asserted as an in-force mandatory 7-8 GHz criterion.",
        },
    }
    output = ROOT / cfg["freeze_output_yaml"]
    write_yaml(output, decision)
    print(f"Wrote reviewed candidate decision: {output}")
    print("The main regulatory YAML was not overwritten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
