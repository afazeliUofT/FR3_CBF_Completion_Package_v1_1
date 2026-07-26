#!/usr/bin/env python3
"""Audit S1 warnings and bracket lower always-on I/N screening thresholds.

This script is deliberately non-freezing. It uses one allocation-scenario input
for the P.530 physics because incremental outage is invariant to the allocation,
then compares that common result with every predeclared conditional scenario.
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


STATUS = "CONDITIONAL_SENSITIVITY_NOT_FINAL_COMPLIANCE"


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


def bool_cell(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def make_grid(lower: float, upper: float, step: float, maximum: int) -> list[float]:
    if not math.isfinite(lower) or not math.isfinite(upper) or not math.isfinite(step):
        raise ValueError("Screen bounds and step must be finite")
    if step <= 0 or lower >= upper:
        raise ValueError("Require step > 0 and lower < upper")
    count = int(round((upper - lower) / step)) + 1
    if count < 2 or count > maximum:
        raise ValueError(f"Candidate grid has {count} points; allowed range is 2..{maximum}")
    values = [round(lower + i * step, 10) for i in range(count)]
    if not math.isclose(values[-1], upper, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError("Upper bound is not reached exactly by the declared step")
    return values


def threshold_interval(candidates: np.ndarray, passes: np.ndarray) -> dict[str, Any]:
    if candidates.ndim != 1 or passes.ndim != 1 or len(candidates) != len(passes):
        raise ValueError("Threshold inputs must be aligned one-dimensional arrays")
    order = np.argsort(candidates)
    c = candidates[order]
    p = passes[order].astype(bool)
    # For a monotone screen, PASS may change to FAIL at most once.
    seen_fail = False
    for flag in p:
        if not flag:
            seen_fail = True
        elif seen_fail:
            raise AssertionError("Non-monotone scenario PASS pattern detected")
    if not p.any():
        return {
            "status": "NO_PASS_WITHIN_SCREEN_RANGE",
            "highest_passing_candidate_db": None,
            "first_failing_candidate_db": float(c[0]),
            "threshold_interval_lower_db": None,
            "threshold_interval_upper_db": float(c[0]),
        }
    if p.all():
        return {
            "status": "ALL_CANDIDATES_PASS_WITHIN_SCREEN_RANGE",
            "highest_passing_candidate_db": float(c[-1]),
            "first_failing_candidate_db": None,
            "threshold_interval_lower_db": float(c[-1]),
            "threshold_interval_upper_db": None,
        }
    last_pass_index = int(np.flatnonzero(p)[-1])
    first_fail_index = last_pass_index + 1
    return {
        "status": "BRACKETED_ON_DECLARED_GRID",
        "highest_passing_candidate_db": float(c[last_pass_index]),
        "first_failing_candidate_db": float(c[first_fail_index]),
        "threshold_interval_lower_db": float(c[last_pass_index]),
        "threshold_interval_upper_db": float(c[first_fail_index]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit warnings and bracket lower S1 always-on I/N sensitivity thresholds"
    )
    parser.add_argument("--config", default="config/s1_cap_reframe.yaml")
    args = parser.parse_args()

    cfg_path = resolve(args.config)
    cfg = load_yaml(cfg_path)
    matrix_cfg_path = resolve(cfg["inputs"]["allocation_matrix_config"])
    prior_dir = resolve(cfg["inputs"]["prior_matrix_result_dir"])
    out_dir = resolve(cfg["outputs"]["result_dir"])
    matrix_cfg = load_yaml(matrix_cfg_path)

    scenario_dir = resolve(matrix_cfg["outputs"]["scenario_input_dir"])
    manifest_path = scenario_dir / "scenario_manifest.csv"
    scenario_build_audit_path = scenario_dir / "SCENARIO_BUILD_AUDIT.json"
    p530_dir = resolve(matrix_cfg["inputs"]["p530_products_dir"])
    prior_audit_path = prior_dir / "audit.json"
    prior_pass_matrix_path = prior_dir / "scenario_pass_matrix.csv"
    prior_envelope_path = prior_dir / "required_allocation_envelope.csv"

    required_paths = [
        cfg_path,
        matrix_cfg_path,
        manifest_path,
        scenario_build_audit_path,
        prior_audit_path,
        prior_pass_matrix_path,
        prior_envelope_path,
    ]
    for path in required_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    if cfg.get("mode", "real") == "real" and not p530_dir.is_dir():
        raise FileNotFoundError(p530_dir)

    prior_audit = json.loads(prior_audit_path.read_text(encoding="utf-8"))
    prior_pass = pd.read_csv(prior_pass_matrix_path)
    prior_envelope = pd.read_csv(prior_envelope_path)
    original_positive = [float(x) for x in cfg["screen"]["original_positive_candidates_db"]]

    if bool(cfg["screen"].get("require_original_positive_candidates_to_have_failed_prior_matrix", True)):
        missing_columns: list[str] = []
        passing_cells: list[str] = []
        for candidate in original_positive:
            column = f"candidate_{candidate:g}_dB_pass"
            if column not in prior_pass.columns:
                missing_columns.append(column)
                continue
            for idx, value in enumerate(prior_pass[column]):
                if bool_cell(value):
                    passing_cells.append(f"row={idx}, column={column}")
        if missing_columns:
            raise ValueError(f"Prior pass matrix lacks columns: {missing_columns}")
        if passing_cells:
            raise ValueError(
                "This reframe stage requires all original positive candidates to have failed; "
                f"unexpected PASS cells: {passing_cells[:10]}"
            )

    manifest = pd.read_csv(manifest_path, dtype=str)
    expected_scenarios = len(matrix_cfg["scenarios"])
    expected_links = int(cfg["expected_links"])
    if len(manifest) != expected_scenarios:
        raise ValueError(f"Scenario manifest has {len(manifest)} rows; expected {expected_scenarios}")
    if manifest["scenario_id"].nunique() != expected_scenarios:
        raise ValueError("Scenario IDs are not unique")

    manifest = manifest.sort_values("scenario_id").reset_index(drop=True)
    reference_manifest_row = manifest.iloc[0]
    reference_scenario_id = str(reference_manifest_row["scenario_id"])
    reference_input_path = resolve(str(reference_manifest_row["input_csv"]))
    if not reference_input_path.is_file():
        raise FileNotFoundError(reference_input_path)
    expected_reference_hash = str(reference_manifest_row["input_sha256"]).strip().lower()
    if sha256_file(reference_input_path) != expected_reference_hash:
        raise ValueError("Reference scenario input hash mismatch")

    screen_cfg = cfg["screen"]
    candidates = make_grid(
        float(screen_cfg["lower_i_over_n_db"]),
        float(screen_cfg["upper_i_over_n_db"]),
        float(screen_cfg["step_db"]),
        int(screen_cfg["maximum_grid_points"]),
    )

    details, _, physical_audit = evaluate_s1(
        links_csv=reference_input_path,
        candidate_i_over_n_db=candidates,
        mode=str(cfg.get("mode", "real")),
        p530_products_dir=p530_dir,
        global_allocation_pct=None,
        use_all_percentages_method=bool(cfg.get("use_all_percentages_method", True)),
        require_real_grids=bool(cfg.get("require_real_p530_grids", True)),
    )
    if details["link_id"].nunique() != expected_links:
        raise ValueError(
            f"Reference evaluation contains {details['link_id'].nunique()} links; expected {expected_links}"
        )

    # Verify candidate-wise monotonicity of the physical incremental-outage output.
    tol = float(screen_cfg.get("monotonicity_tolerance_pct", 1e-10))
    nonmonotone: list[str] = []
    for link_id, group in details.groupby("link_id"):
        g = group.sort_values("candidate_i_over_n_db")
        diffs = np.diff(g["incremental_outage_pct_worst_month"].to_numpy(float))
        if np.any(diffs < -tol):
            nonmonotone.append(str(link_id))
    if nonmonotone:
        raise AssertionError(f"Incremental outage is non-monotone for links: {nonmonotone[:10]}")

    out_dir.mkdir(parents=True, exist_ok=True)
    details_path = out_dir / "reference_link_details_all_candidates.csv.gz"
    details.to_csv(details_path, index=False, compression="gzip")

    first_candidate = min(candidates)
    warning_rows = details[
        np.isclose(details["candidate_i_over_n_db"].astype(float), first_candidate)
        & (details["warning_count"].astype(int) > 0)
    ].copy()
    warning_columns = [
        "link_id",
        "distance_km",
        "midpoint_lat_deg",
        "midpoint_lon_deg",
        "path_inclination_mrad",
        "mean_terrain_clearance_m",
        "k_percent",
        "dn75_n_units",
        "fade_margin_db",
        "baseline_outage_pct_worst_month",
        "warning_count",
        "warnings",
    ]
    warning_rows = warning_rows[warning_columns].sort_values("link_id")
    warning_rows.to_csv(out_dir / "model_warning_links.csv", index=False)

    envelope_rows: list[dict[str, Any]] = []
    physical_by_candidate: dict[float, pd.DataFrame] = {}
    for candidate, group in details.groupby("candidate_i_over_n_db", sort=True):
        g = group.copy().sort_values("link_id").reset_index(drop=True)
        physical_by_candidate[float(candidate)] = g
        values = g["incremental_outage_pct_worst_month"].astype(float)
        worst_row = g.loc[values.idxmax()]
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
                "worst_link_after_outage_pct": float(worst_row["after_outage_pct_worst_month"]),
                "links_with_model_warnings": int((g["warning_count"].astype(int) > 0).sum()),
            }
        )
    envelope = pd.DataFrame(envelope_rows).sort_values("candidate_i_over_n_db")
    envelope.to_csv(out_dir / "lower_cap_required_allocation_envelope.csv", index=False)

    scenario_summary_rows: list[dict[str, Any]] = []
    allocation_values: list[float] = []
    scenario_inputs: dict[str, pd.DataFrame] = {}
    for _, mrow in manifest.iterrows():
        scenario_id = str(mrow["scenario_id"])
        input_path = resolve(str(mrow["input_csv"]))
        if not input_path.is_file():
            raise FileNotFoundError(input_path)
        if sha256_file(input_path) != str(mrow["input_sha256"]).strip().lower():
            raise ValueError(f"Scenario input hash mismatch: {scenario_id}")
        scenario_df = pd.read_csv(input_path, dtype={"link_id": str})
        if len(scenario_df) != expected_links or scenario_df["link_id"].nunique() != expected_links:
            raise ValueError(f"Scenario {scenario_id} does not contain exactly {expected_links} links")
        allocations = pd.to_numeric(
            scenario_df["allocated_incremental_outage_pct"], errors="coerce"
        )
        if allocations.isna().any() or (allocations <= 0).any():
            raise ValueError(f"Scenario {scenario_id} has missing/non-positive allocations")
        scenario_df = scenario_df[["link_id", "allocated_incremental_outage_pct"]].copy()
        scenario_df["allocated_incremental_outage_pct"] = allocations.astype(float)
        scenario_inputs[scenario_id] = scenario_df.sort_values("link_id").reset_index(drop=True)
        allocation_values.extend(allocations.tolist())

        for candidate in candidates:
            physical = physical_by_candidate[float(candidate)][
                ["link_id", "incremental_outage_pct_worst_month"]
            ]
            merged = physical.merge(scenario_df, on="link_id", how="inner", validate="one_to_one")
            if len(merged) != expected_links:
                raise AssertionError(f"Scenario {scenario_id}: physical/allocation link mismatch")
            margins = (
                merged["allocated_incremental_outage_pct"].astype(float)
                - merged["incremental_outage_pct_worst_month"].astype(float)
            )
            worst_idx = margins.idxmin()
            scenario_summary_rows.append(
                {
                    "scenario_id": scenario_id,
                    "candidate_i_over_n_db": float(candidate),
                    "all_links_pass": bool((margins >= -1e-12).all()),
                    "minimum_allocation_margin_pct": float(margins.min()),
                    "worst_margin_link_id": str(merged.loc[worst_idx, "link_id"]),
                    "worst_link_incremental_outage_pct": float(
                        merged.loc[worst_idx, "incremental_outage_pct_worst_month"]
                    ),
                    "worst_link_allocation_pct": float(
                        merged.loc[worst_idx, "allocated_incremental_outage_pct"]
                    ),
                }
            )

    scenario_summary = pd.DataFrame(scenario_summary_rows).sort_values(
        ["scenario_id", "candidate_i_over_n_db"]
    )
    scenario_summary.to_csv(out_dir / "scenario_lower_cap_summary.csv", index=False)

    threshold_rows: list[dict[str, Any]] = []
    for scenario_id, group in scenario_summary.groupby("scenario_id", sort=True):
        g = group.sort_values("candidate_i_over_n_db")
        interval = threshold_interval(
            g["candidate_i_over_n_db"].to_numpy(float),
            g["all_links_pass"].to_numpy(bool),
        )
        threshold_rows.append({"scenario_id": scenario_id, **interval})

    all_scenario = (
        scenario_summary.groupby("candidate_i_over_n_db", as_index=False)
        .agg(all_scenarios_pass=("all_links_pass", "all"))
        .sort_values("candidate_i_over_n_db")
    )
    all_interval = threshold_interval(
        all_scenario["candidate_i_over_n_db"].to_numpy(float),
        all_scenario["all_scenarios_pass"].to_numpy(bool),
    )
    threshold_rows.append({"scenario_id": "ALL_EIGHT_SCENARIOS", **all_interval})
    thresholds = pd.DataFrame(threshold_rows)
    thresholds.to_csv(out_dir / "scenario_threshold_intervals.csv", index=False)
    all_scenario.to_csv(out_dir / "all_scenario_pass_by_candidate.csv", index=False)

    pivot = scenario_summary.pivot(
        index="scenario_id", columns="candidate_i_over_n_db", values="all_links_pass"
    ).reset_index()
    pivot.columns = [
        "scenario_id" if c == "scenario_id" else f"candidate_{float(c):g}_dB_pass"
        for c in pivot.columns
    ]
    pivot.to_csv(out_dir / "lower_cap_pass_matrix.csv", index=False)

    max_scenario_allocation = float(max(allocation_values))
    original_rows: list[dict[str, Any]] = []
    for candidate in original_positive:
        match = prior_envelope[
            np.isclose(prior_envelope["candidate_i_over_n_db"].astype(float), candidate)
        ]
        if len(match) != 1:
            raise ValueError(f"Prior envelope lacks a unique row for {candidate:g} dB")
        required = float(match.iloc[0]["required_uniform_allocation_pct"])
        original_rows.append(
            {
                "candidate_i_over_n_db": candidate,
                "required_uniform_allocation_pct": required,
                "largest_tested_scenario_allocation_pct": max_scenario_allocation,
                "required_to_largest_allocation_ratio": required / max_scenario_allocation,
                "passes_any_tested_scenario": False,
                "decision": "REJECT_AS_ALWAYS_ON_CANDIDATE_UNDER_ALL_EIGHT_TESTED_SCENARIOS",
            }
        )
    original_rejection = pd.DataFrame(original_rows)
    original_rejection.to_csv(out_dir / "positive_always_on_candidate_rejection.csv", index=False)

    fig, ax = plt.subplots(figsize=(8.4, 5.3))
    ax.plot(
        envelope["candidate_i_over_n_db"],
        envelope["required_uniform_allocation_pct"],
        marker=".",
        linewidth=1.0,
        label="Required all-link allocation envelope",
    )
    scenario_levels = sorted(set(float(x) for x in allocation_values))
    for level in scenario_levels:
        ax.axhline(level, linestyle="--", linewidth=0.7, alpha=0.45)
    ax.set_yscale("log")
    ax.set_xlabel("Candidate always-on I/N (dB)")
    ax.set_ylabel("Worst-month incremental threshold-exceedance (%)")
    ax.set_title("Lower-cap numerical bracket; sensitivity scenarios are not compliance allocations")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "lower_cap_required_allocation_envelope.png", dpi=180)
    plt.close(fig)

    warning_gate_open = len(warning_rows) > 0
    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": STATUS,
        "positive_always_on_candidate_set": original_positive,
        "positive_always_on_candidates_rejected_under_all_eight_tested_scenarios": True,
        "provisional_19_db_always_on_freeze_allowed": False,
        "model_warning_link_count": int(len(warning_rows)),
        "model_warning_gate_open": warning_gate_open,
        "lower_cap_screen_is_final_compliance_decision": False,
        "all_eight_scenario_threshold_interval": all_interval,
        "required_next_actions": [
            "Review and disposition every P.530 model warning without deleting links merely to improve the threshold.",
            "Obtain operator/administration evidence for network portion, source class, and event mapping before freezing a scenario-specific cap.",
            "Only after the warning and classification gates close, run the predeclared P.530 parameter-sensitivity campaign around the supported threshold interval.",
            "Treat +19 dB, if retained at all, only through a separately justified rare-transient/multi-threshold rule; this run rejects it as an always-on cap.",
        ],
    }
    write_json(out_dir / "S1_CAP_REFRAME_DECISION.json", decision)

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": STATUS,
        "config": str(cfg_path.relative_to(ROOT)),
        "config_sha256": sha256_file(cfg_path),
        "allocation_matrix_config": str(matrix_cfg_path.relative_to(ROOT)),
        "allocation_matrix_config_sha256": sha256_file(matrix_cfg_path),
        "scenario_manifest": str(manifest_path.relative_to(ROOT)),
        "scenario_manifest_sha256": sha256_file(manifest_path),
        "prior_matrix_audit_sha256": sha256_file(prior_audit_path),
        "prior_matrix_pass_matrix_sha256": sha256_file(prior_pass_matrix_path),
        "prior_matrix_envelope_sha256": sha256_file(prior_envelope_path),
        "reference_scenario_id": reference_scenario_id,
        "reference_input_sha256": expected_reference_hash,
        "screen_candidates": candidates,
        "candidate_grid_count": len(candidates),
        "expected_links": expected_links,
        "model_warning_link_count": int(len(warning_rows)),
        "physical_audit": physical_audit,
        "final_allocation_selected": False,
        "final_cap_frozen": False,
        "outputs": {
            "reference_link_details_all_candidates": sha256_file(details_path),
            "model_warning_links": sha256_file(out_dir / "model_warning_links.csv"),
            "lower_cap_required_allocation_envelope": sha256_file(
                out_dir / "lower_cap_required_allocation_envelope.csv"
            ),
            "scenario_lower_cap_summary": sha256_file(out_dir / "scenario_lower_cap_summary.csv"),
            "scenario_threshold_intervals": sha256_file(out_dir / "scenario_threshold_intervals.csv"),
            "all_scenario_pass_by_candidate": sha256_file(out_dir / "all_scenario_pass_by_candidate.csv"),
            "lower_cap_pass_matrix": sha256_file(out_dir / "lower_cap_pass_matrix.csv"),
            "positive_always_on_candidate_rejection": sha256_file(
                out_dir / "positive_always_on_candidate_rejection.csv"
            ),
            "decision": sha256_file(out_dir / "S1_CAP_REFRAME_DECISION.json"),
            "plot": sha256_file(out_dir / "lower_cap_required_allocation_envelope.png"),
        },
        "claim_boundary": cfg["metadata"]["claim_boundary"],
    }
    write_json(out_dir / "audit.json", audit)

    print("S1 CAP REFRAME SCREEN: PASS")
    print(f"Links: {expected_links}")
    print(f"Candidate grid: {candidates[0]:g} to {candidates[-1]:g} dB in {screen_cfg['step_db']} dB steps")
    print(f"P.530 model-warning links: {len(warning_rows)}")
    print("\nPOSITIVE ALWAYS-ON CANDIDATE DECISION")
    print(original_rejection.to_string(index=False))
    print("\nSCENARIO THRESHOLD INTERVALS")
    print(thresholds.to_string(index=False))
    print(f"\nOutputs: {out_dir}")
    print("No allocation was selected and no cap was frozen.")
    if warning_gate_open:
        print("WARNING GATE REMAINS OPEN: review model_warning_links.csv before any threshold decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
