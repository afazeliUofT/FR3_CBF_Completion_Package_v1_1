#!/usr/bin/env python3
"""Independent review of the distributed local-precoding architecture audit."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from _bootstrap import ROOT


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/distributed_channel_readiness.yaml"
    )
    args = parser.parse_args()

    cfg_path = ROOT / args.config
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    inp = {key: ROOT / value for key, value in cfg["inputs"].items()}
    out = ROOT / cfg["outputs"]["work_dir"]
    out.mkdir(parents=True, exist_ok=True)

    required = [
        inp["architecture_decision_json"],
        inp["prototype_audit_json"],
        inp["prototype_validation_json"],
        inp["prototype_time_summary_csv"],
        inp["architecture_source"],
        inp["prototype_source"],
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    architecture = json.loads(
        inp["architecture_decision_json"].read_text(encoding="utf-8")
    )
    audit = json.loads(inp["prototype_audit_json"].read_text(encoding="utf-8"))
    validation = json.loads(
        inp["prototype_validation_json"].read_text(encoding="utf-8")
    )
    summary = pd.read_csv(inp["prototype_time_summary_csv"])
    source = inp["prototype_source"].read_text(encoding="utf-8")

    expected = cfg["expected"]
    assert architecture["status"] == "FROZEN_DISTRIBUTED_ARCHITECTURE_NOT_PAPER_RESULT"
    assert audit["status"] == "PASS_PROTOTYPE_ONLY"
    assert validation["status"] == "PASS_ARCHITECTURE_AND_SOFTWARE_PROTOTYPE_ONLY"
    assert audit["sector_count"] == int(expected["sector_count"])
    assert audit["protected_sample_count"] == int(expected["protected_sample_count"])
    assert audit["sector_time_row_count"] == int(expected["prototype_sector_time_rows"])
    assert len(summary) == int(expected["protected_sample_count"])
    assert summary["local_budget_violation_count"].eq(0).all()
    assert np.isclose(
        float(validation["minimum_rate_retention_fraction"]),
        float(expected["minimum_rate_retention_fraction"]),
        atol=1e-12,
        rtol=0,
    )

    # The prototype recomputes budgets at every protected sample. The declared
    # slow update period is architecture intent, not a tested property.
    rate_limit_used = "budget_update_period_slots" in source
    inter_cell_rate_used = "inter_cell" in source.lower()
    standards_channel_used = "sionna" in source.lower() or "tr38901" in source.lower()

    if rate_limit_used:
        raise ValueError(
            "Unexpected: the architecture prototype appears to use the declared "
            "budget-update period; independent review must be updated."
        )
    if inter_cell_rate_used:
        raise ValueError(
            "Unexpected: inter-cell rate logic detected; independent review must be updated."
        )
    if standards_channel_used:
        raise ValueError(
            "Unexpected: standards-channel logic detected; independent review must be updated."
        )

    method = cfg["method_naming"]
    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_WITH_REQUIRED_PAPER_EXPERIMENT",
        "claim_boundary": cfg["claim_boundary"]["architecture_review"],
        "method_naming": {
            "recommended_name": method["paper_name"],
            "acronym": method["acronym"],
            "previous_name": method["previous_name"],
            "reason": method["reason"],
        },
        "accepted_properties": cfg["architecture_review"]["accepted"],
        "prototype_not_tested": cfg["architecture_review"]["not_tested_by_prototype"],
        "prototype_findings": {
            "local_budget_violations": int(audit["local_budget_violation_count"]),
            "aggregate_budget_sum_error_w": float(
                validation["maximum_budget_sum_error_w"]
            ),
            "minimum_rate_retention_fraction": float(
                validation["minimum_rate_retention_fraction"]
            ),
            "rate_retention_disposition": cfg["architecture_review"][
                "prototype_interpretation"
            ],
            "budget_recomputed_at_every_protected_sample": True,
            "declared_ten_slot_budget_update_not_tested": True,
            "inter_cell_ue_interference_not_in_rate_proxy": True,
            "standards_channel_model_not_used": True,
        },
        "scientific_conclusion": (
            "The rank-one projection and aggregate budget certificate are sound. "
            "The deterministic prototype validates software only; it does not "
            "establish dynamic-control value, realistic cellular utility, or "
            "standards-aligned performance."
        ),
        "next_gate": cfg["paper_experiment"]["next_gate"],
    }
    write_json(out / "DISTRIBUTED_ARCHITECTURE_INDEPENDENT_REVIEW.json", decision)

    (out / "DISTRIBUTED_ARCHITECTURE_INDEPENDENT_REVIEW.md").write_text(
        "# Independent review of the distributed local-precoding architecture\n\n"
        f"- Status: `{decision['status']}`\n"
        f"- Recommended method name: `{method['paper_name']}` "
        f"(`{method['acronym']}`)\n"
        "- Exact local projection: accepted\n"
        "- Aggregate budget certificate: accepted\n"
        "- Network-wide instantaneous UE CSI: not used\n"
        "- Joint network precoder: not used\n"
        "- Standards-aligned channel evidence: not yet present\n"
        "- Inter-cell rate evidence: not yet present\n"
        "- Rate-limited budget updates: not yet tested\n\n"
        "The reported 99.77% prototype rate retention is an intra-cell-only, "
        "deterministic-channel software result. It must not appear as a TWC "
        "performance result.\n\n"
        f"Next gate: `{decision['next_gate']}`\n",
        encoding="utf-8",
    )

    print("DISTRIBUTED ARCHITECTURE INDEPENDENT REVIEW: PASS")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
