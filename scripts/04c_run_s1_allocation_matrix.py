#!/usr/bin/env python3
"""Run the nominal S1 candidate screen across conditional allocation scenarios.

The script also produces an allocation-free required-allocation envelope. The
envelope is the maximum incremental P.530 worst-month threshold-exceedance
percentage across all retained links for each candidate I/N cap. It is a model
output, not an adopted regulatory allowance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from _bootstrap import ROOT
from fr3_cbf.s1 import evaluate_s1


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run nominal S1 screen across conditional F.1565/G.826 allocation scenarios"
    )
    parser.add_argument("--config", default="config/s1_allocation_matrix.yaml")
    args = parser.parse_args()

    cfg_path = resolve(args.config)
    cfg = load_yaml(cfg_path)
    scenario_dir = resolve(cfg["outputs"]["scenario_input_dir"])
    out_dir = resolve(cfg["outputs"]["result_dir"])
    p530_dir = resolve(cfg["inputs"]["p530_products_dir"])
    manifest_path = scenario_dir / "scenario_manifest.csv"
    build_audit_path = scenario_dir / "SCENARIO_BUILD_AUDIT.json"

    for path in [cfg_path, manifest_path, build_audit_path]:
        if not path.is_file():
            raise FileNotFoundError(path)
    if not p530_dir.is_dir():
        raise FileNotFoundError(p530_dir)

    manifest = pd.read_csv(manifest_path, dtype={"scenario_id": str, "input_csv": str})
    expected_scenarios = len(cfg["scenarios"])
    if len(manifest) != expected_scenarios:
        raise ValueError(f"Manifest has {len(manifest)} scenarios; expected {expected_scenarios}")

    candidates = [float(x) for x in cfg["candidate_i_over_n_db"]]
    out_dir.mkdir(parents=True, exist_ok=True)
    scenario_root = out_dir / "scenarios"
    scenario_root.mkdir(parents=True, exist_ok=True)

    master_rows: list[dict[str, Any]] = []
    reference_incremental: pd.DataFrame | None = None
    reference_scenario_id: str | None = None

    for _, mrow in manifest.sort_values("scenario_id").iterrows():
        scenario_id = str(mrow["scenario_id"])
        input_path = resolve(str(mrow["input_csv"]))
        expected_hash = str(mrow["input_sha256"]).strip().lower()
        if not input_path.is_file():
            raise FileNotFoundError(input_path)
        actual_hash = sha256_file(input_path)
        if actual_hash != expected_hash:
            raise ValueError(f"Scenario input hash mismatch for {scenario_id}")

        details, summary, audit = evaluate_s1(
            links_csv=input_path,
            candidate_i_over_n_db=candidates,
            mode="real",
            p530_products_dir=p530_dir,
            global_allocation_pct=None,
            use_all_percentages_method=bool(cfg.get("use_all_percentages_method", True)),
            require_real_grids=bool(cfg.get("require_real_p530_grids", True)),
        )
        scenario_out = scenario_root / scenario_id
        scenario_out.mkdir(parents=True, exist_ok=True)
        details.to_csv(scenario_out / "link_details.csv", index=False)
        summary.to_csv(scenario_out / "candidate_summary.csv", index=False)
        audit.update(
            {
                "scenario_id": scenario_id,
                "scenario_status": "CONDITIONAL_SENSITIVITY_NOT_FINAL_COMPLIANCE",
                "scenario_input_sha256": actual_hash,
            }
        )
        write_json(scenario_out / "audit.json", audit)

        incremental = details[
            ["link_id", "candidate_i_over_n_db", "incremental_outage_pct_worst_month"]
        ].sort_values(["link_id", "candidate_i_over_n_db"]).reset_index(drop=True)
        if reference_incremental is None:
            reference_incremental = incremental
            reference_scenario_id = scenario_id
        else:
            if not incremental[["link_id", "candidate_i_over_n_db"]].equals(
                reference_incremental[["link_id", "candidate_i_over_n_db"]]
            ):
                raise AssertionError("Scenario result keys differ")
            delta = np.max(
                np.abs(
                    incremental["incremental_outage_pct_worst_month"].to_numpy()
                    - reference_incremental["incremental_outage_pct_worst_month"].to_numpy()
                )
            )
            if delta > 1e-12:
                raise AssertionError(
                    f"Incremental outage changed across allocation scenarios; max delta={delta}"
                )

        for _, srow in summary.iterrows():
            master_rows.append(
                {
                    "scenario_id": scenario_id,
                    "sharing_class": mrow["sharing_class"],
                    "network_portion": mrow["network_portion"],
                    "allocation_min_pct": float(mrow["allocation_min_pct"]),
                    "allocation_median_pct": float(mrow["allocation_median_pct"]),
                    "allocation_max_pct": float(mrow["allocation_max_pct"]),
                    "candidate_i_over_n_db": float(srow["candidate_i_over_n_db"]),
                    "all_links_pass": bool(srow["all_links_pass"]),
                    "worst_incremental_outage_pct": float(srow["worst_incremental_outage_pct"]),
                    "minimum_allocation_margin_pct": float(srow["minimum_allocation_margin_pct"]),
                    "links_with_warnings": int(srow["links_with_warnings"]),
                }
            )

    if reference_incremental is None or reference_scenario_id is None:
        raise AssertionError("No scenario was evaluated")

    master = pd.DataFrame(master_rows).sort_values(["scenario_id", "candidate_i_over_n_db"])
    master.to_csv(out_dir / "scenario_candidate_summary.csv", index=False)

    # Allocation-free envelope: the minimum uniform allocation that would be
    # required for every retained link to pass under the current P.530 model.
    first_details = pd.read_csv(
        scenario_root / reference_scenario_id / "link_details.csv"
    )
    envelope_rows: list[dict[str, Any]] = []
    for candidate, group in first_details.groupby("candidate_i_over_n_db"):
        values = group["incremental_outage_pct_worst_month"].astype(float)
        worst_index = values.idxmax()
        worst_row = group.loc[worst_index]
        envelope_rows.append(
            {
                "candidate_i_over_n_db": float(candidate),
                "required_uniform_allocation_pct": float(values.max()),
                "p95_link_incremental_outage_pct": float(values.quantile(0.95)),
                "median_link_incremental_outage_pct": float(values.median()),
                "minimum_link_incremental_outage_pct": float(values.min()),
                "worst_link_id": str(worst_row["link_id"]),
                "worst_link_fade_margin_db": float(worst_row["fade_margin_db"]),
                "worst_link_baseline_outage_pct": float(
                    worst_row["baseline_outage_pct_worst_month"]
                ),
                "worst_link_after_outage_pct": float(
                    worst_row["after_outage_pct_worst_month"]
                ),
                "links_with_model_warnings": int((group["warning_count"] > 0).sum()),
            }
        )
    envelope = pd.DataFrame(envelope_rows).sort_values("candidate_i_over_n_db")
    envelope.to_csv(out_dir / "required_allocation_envelope.csv", index=False)

    # PASS/FAIL pivot is convenient for direct review.
    pivot = master.pivot(
        index="scenario_id", columns="candidate_i_over_n_db", values="all_links_pass"
    ).reset_index()
    pivot.columns = [
        "scenario_id" if c == "scenario_id" else f"candidate_{float(c):g}_dB_pass"
        for c in pivot.columns
    ]
    pivot.to_csv(out_dir / "scenario_pass_matrix.csv", index=False)

    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    ax.plot(
        envelope["candidate_i_over_n_db"],
        envelope["required_uniform_allocation_pct"],
        marker="o",
        label="Required uniform allocation envelope",
    )
    for _, mrow in manifest.iterrows():
        if math.isclose(float(mrow["allocation_min_pct"]), float(mrow["allocation_max_pct"]), rel_tol=0, abs_tol=1e-15):
            ax.axhline(
                float(mrow["allocation_min_pct"]),
                linewidth=0.8,
                linestyle="--",
                alpha=0.5,
                label=str(mrow["scenario_id"]),
            )
    ax.set_yscale("log")
    ax.set_xlabel("Candidate always-on I/N cap (dB)")
    ax.set_ylabel("Worst-month incremental threshold-exceedance (%)")
    ax.set_title("S1 required-allocation envelope and conditional F.1565 scenarios")
    ax.grid(True, which="both", alpha=0.25)
    # Many labels are expected; place outside the axes.
    ax.legend(fontsize=6, loc="upper left", bbox_to_anchor=(1.02, 1.0))
    fig.tight_layout()
    fig.savefig(out_dir / "required_allocation_envelope.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(cfg_path.relative_to(ROOT)),
        "config_sha256": sha256_file(cfg_path),
        "scenario_manifest": str(manifest_path.relative_to(ROOT)),
        "scenario_manifest_sha256": sha256_file(manifest_path),
        "scenario_count": len(manifest),
        "candidate_i_over_n_db": candidates,
        "reference_scenario_for_allocation_free_envelope": reference_scenario_id,
        "incremental_outage_invariant_across_scenarios": True,
        "final_allocation_selected": False,
        "claim_boundary": (
            "PASS means only that the P.530 screening output is below the numerical "
            "allocation of the labelled conditional scenario. It is not a final "
            "regulatory or operator compliance statement."
        ),
        "outputs": {
            "scenario_candidate_summary": sha256_file(out_dir / "scenario_candidate_summary.csv"),
            "required_allocation_envelope": sha256_file(out_dir / "required_allocation_envelope.csv"),
            "scenario_pass_matrix": sha256_file(out_dir / "scenario_pass_matrix.csv"),
        },
    }
    write_json(out_dir / "audit.json", audit)

    print("S1 ALLOCATION MATRIX: PASS")
    print("\nREQUIRED UNIFORM ALLOCATION ENVELOPE")
    print(envelope.to_string(index=False))
    print("\nCONDITIONAL SCENARIO PASS MATRIX")
    print(pivot.to_string(index=False))
    print(f"\nOutputs: {out_dir}")
    print("No final allocation or I/N candidate was frozen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
