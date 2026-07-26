from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

try:
    from _bootstrap import ROOT
except ImportError:  # pragma: no cover - permits standalone test
    ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def physical_path_id(link_id: str) -> str:
    return str(link_id).split("__", 1)[0]


def bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Disposition P.530 warning links and create the S1 operator-classification request"
    )
    parser.add_argument("--config", default="config/s1_warning_disposition.yaml")
    args = parser.parse_args()

    cfg = read_yaml(resolve(args.config))
    expected = cfg["expected"]
    cap_dir = resolve(cfg["inputs"]["cap_reframe_dir"])
    out_dir = resolve(cfg["outputs"]["result_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "audit": cap_dir / "audit.json",
        "decision": cap_dir / "S1_CAP_REFRAME_DECISION.json",
        "warnings": cap_dir / "model_warning_links.csv",
        "thresholds": cap_dir / "scenario_threshold_intervals.csv",
        "summary": cap_dir / "scenario_lower_cap_summary.csv",
        "details": cap_dir / "reference_link_details_all_candidates.csv.gz",
        "positive_rejection": cap_dir / "positive_always_on_candidate_rejection.csv",
    }
    missing = [str(p) for p in paths.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing cap-reframe evidence: " + ", ".join(missing))

    audit = json.loads(paths["audit"].read_text(encoding="utf-8"))
    decision = json.loads(paths["decision"].read_text(encoding="utf-8"))

    output_name_map = {
        "decision": paths["decision"],
        "model_warning_links": paths["warnings"],
        "scenario_threshold_intervals": paths["thresholds"],
        "scenario_lower_cap_summary": paths["summary"],
        "reference_link_details_all_candidates": paths["details"],
        "positive_always_on_candidate_rejection": paths["positive_rejection"],
    }
    for key, path in output_name_map.items():
        expected_hash = audit["outputs"][key]
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ValueError(f"Hash mismatch for {path}: expected {expected_hash}, got {actual_hash}")

    if bool(audit.get("final_cap_frozen")) or bool(audit.get("final_allocation_selected")):
        raise ValueError("Input audit unexpectedly claims a final cap or allocation was frozen")
    if decision.get("provisional_19_db_always_on_freeze_allowed") is not False:
        raise ValueError("Decision file does not explicitly reject +19 dB as an always-on freeze")

    warnings = pd.read_csv(paths["warnings"])
    thresholds = pd.read_csv(paths["thresholds"])
    summary = pd.read_csv(paths["summary"])
    details = pd.read_csv(paths["details"])
    positive = pd.read_csv(paths["positive_rejection"])

    if len(warnings) != int(expected["warning_record_count"]):
        raise ValueError(f"Expected {expected['warning_record_count']} warning records, found {len(warnings)}")
    warning_ids = set(warnings["link_id"].astype(str))
    path_ids = {physical_path_id(x) for x in warning_ids}
    if len(path_ids) != int(expected["warning_physical_path_count"]):
        raise ValueError(f"Expected one physical warning path, found {len(path_ids)}")

    dmin = float(expected["p530_calculation_lower_length_km"])
    dreg = float(expected["p530_regression_lower_length_km"])
    if not ((warnings["distance_km"] > dmin) & (warnings["distance_km"] < dreg)).all():
        raise ValueError("Warning links are not all in the declared 5.0-7.5 km review interval")
    warnings = warnings.copy()
    warnings["physical_path_id"] = warnings["link_id"].map(physical_path_id)
    warnings["distance_below_regression_lower_edge_km"] = dreg - warnings["distance_km"]
    warnings["distance_below_regression_lower_edge_pct"] = (
        warnings["distance_below_regression_lower_edge_km"] / dreg * 100.0
    )
    warnings["disposition"] = "RETAINED_DOCUMENTED_NONBINDING_REGRESSION_RANGE_LIMITATION"

    expected_links = int(expected["link_count"])
    expected_candidates = int(expected["candidate_count"])
    if details["link_id"].nunique() != expected_links:
        raise ValueError("Reference detail file does not contain the expected number of links")
    if details["candidate_i_over_n_db"].nunique() != expected_candidates:
        raise ValueError("Reference detail file does not contain the expected candidate grid")
    if len(details) != expected_links * expected_candidates:
        raise ValueError("Reference detail row count is not links times candidates")

    edge_rows: list[dict[str, Any]] = []
    scenario_thresholds = thresholds.loc[thresholds["scenario_id"] != "ALL_EIGHT_SCENARIOS"]
    for _, threshold in scenario_thresholds.iterrows():
        scenario_id = str(threshold["scenario_id"])
        scenario_summary = summary.loc[summary["scenario_id"] == scenario_id]
        if scenario_summary.empty:
            raise ValueError(f"No summary rows for {scenario_id}")
        for edge_name, field in [
            ("highest_passing", "highest_passing_candidate_db"),
            ("first_failing", "first_failing_candidate_db"),
        ]:
            candidate = float(threshold[field])
            srow = scenario_summary.loc[
                np.isclose(scenario_summary["candidate_i_over_n_db"], candidate)
            ]
            if len(srow) != 1:
                raise ValueError(f"Expected one summary row for {scenario_id} at {candidate} dB")
            srow = srow.iloc[0]

            drows = details.loc[np.isclose(details["candidate_i_over_n_db"], candidate)]
            if len(drows) != expected_links:
                raise ValueError(f"Expected {expected_links} link rows at {candidate} dB")
            global_row = drows.loc[drows["incremental_outage_pct_worst_month"].idxmax()]
            warning_rows = drows.loc[drows["link_id"].astype(str).isin(warning_ids)]
            warning_row = warning_rows.loc[
                warning_rows["incremental_outage_pct_worst_month"].idxmax()
            ]
            global_value = float(global_row["incremental_outage_pct_worst_month"])
            warning_value = float(warning_row["incremental_outage_pct_worst_month"])
            ratio = global_value / warning_value if warning_value > 0 else float("inf")
            worst_margin_link = str(srow["worst_margin_link_id"])

            edge_rows.append(
                {
                    "scenario_id": scenario_id,
                    "edge": edge_name,
                    "candidate_i_over_n_db": candidate,
                    "scenario_worst_margin_link_id": worst_margin_link,
                    "scenario_worst_margin_link_is_warning": worst_margin_link in warning_ids,
                    "scenario_minimum_allocation_margin_pct": float(srow["minimum_allocation_margin_pct"]),
                    "global_worst_incremental_outage_link_id": str(global_row["link_id"]),
                    "global_worst_link_is_warning": str(global_row["link_id"]) in warning_ids,
                    "global_worst_incremental_outage_pct": global_value,
                    "worst_warning_link_id": str(warning_row["link_id"]),
                    "worst_warning_incremental_outage_pct": warning_value,
                    "global_to_warning_incremental_outage_ratio": ratio,
                }
            )

    edge_audit = pd.DataFrame(edge_rows)
    if edge_audit["scenario_worst_margin_link_is_warning"].any():
        raise ValueError("A warning link sets at least one scenario pass/fail edge")
    if edge_audit["global_worst_link_is_warning"].any():
        raise ValueError("A warning link is the global worst link at a scenario edge")

    reference_candidate = float(expected["positive_reference_candidate_db"])
    plus_ref = details.loc[np.isclose(details["candidate_i_over_n_db"], reference_candidate)]
    plus_ref_valid = plus_ref.loc[~plus_ref["link_id"].astype(str).isin(warning_ids)]
    valid_worst = plus_ref_valid.loc[
        plus_ref_valid["incremental_outage_pct_worst_month"].idxmax()
    ]
    positive_row = positive.loc[
        np.isclose(positive["candidate_i_over_n_db"], reference_candidate)
    ]
    if len(positive_row) != 1:
        raise ValueError("Missing the +10 dB positive-reference decision")
    positive_row = positive_row.iloc[0]
    if bool(positive_row["passes_any_tested_scenario"]):
        raise ValueError("The +10 dB reference unexpectedly passes a tested scenario")
    if str(valid_worst["link_id"]) in warning_ids:
        raise ValueError("The +10 dB valid-range rejection check selected a warning link")
    if float(valid_worst["incremental_outage_pct_worst_month"]) <= float(
        positive_row["largest_tested_scenario_allocation_pct"]
    ):
        raise ValueError("The valid-range +10 dB link does not independently reject the candidate")

    all_eight = thresholds.loc[thresholds["scenario_id"] == "ALL_EIGHT_SCENARIOS"]
    if len(all_eight) != 1:
        raise ValueError("Expected exactly one ALL_EIGHT_SCENARIOS threshold row")
    all_eight = all_eight.iloc[0]

    warnings_out = out_dir / "P530_WARNING_LINKS_RETAINED.csv"
    edges_out = out_dir / "P530_WARNING_THRESHOLD_EDGE_AUDIT.csv"
    decision_out = out_dir / "P530_WARNING_DISPOSITION.json"
    markdown_out = out_dir / "P530_WARNING_DISPOSITION.md"
    warnings.to_csv(warnings_out, index=False)
    edge_audit.to_csv(edges_out, index=False)

    minimum_ratio = float(edge_audit["global_to_warning_incremental_outage_ratio"].min())
    binding_links = sorted(set(edge_audit["scenario_worst_margin_link_id"].astype(str)))
    disposition = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "DISPOSITIONED_AS_RETAINED_NONBINDING_MODEL_RANGE_LIMITATION",
        "warning_record_count": len(warnings),
        "warning_physical_path_count": len(path_ids),
        "warning_physical_path_ids": sorted(path_ids),
        "warning_distance_km": sorted(set(float(x) for x in warnings["distance_km"])),
        "distance_below_7_5_km_km": float(warnings["distance_below_regression_lower_edge_km"].max()),
        "distance_below_7_5_km_pct": float(warnings["distance_below_regression_lower_edge_pct"].max()),
        "p530_interpretation": {
            "calculation_applicability_note": "P.530-19 says multipath fading need only be calculated for paths longer than 5 km; these paths are 7.293638 km.",
            "regression_range_note": "P.530-19 Note 2 states that Equation (7) was derived from links of 7.5-300 km. The four records are retained as a slight extrapolation and reported as a limitation.",
        },
        "all_reported_scenario_edges_set_by_nonwarning_links": True,
        "binding_link_ids_at_all_scenario_edges": binding_links,
        "minimum_global_to_warning_outage_ratio_at_threshold_edges": minimum_ratio,
        "positive_10_db_rejected_by_nonwarning_link": {
            "link_id": str(valid_worst["link_id"]),
            "incremental_outage_pct": float(valid_worst["incremental_outage_pct_worst_month"]),
            "largest_tested_scenario_allocation_pct": float(
                positive_row["largest_tested_scenario_allocation_pct"]
            ),
        },
        "all_eight_sensitivity_interval_db": {
            "highest_passing": float(all_eight["highest_passing_candidate_db"]),
            "first_failing": float(all_eight["first_failing_candidate_db"]),
        },
        "claim_boundary": (
            "This disposition does not validate Equation (7) inside its regression dataset, "
            "does not delete the warning links, and does not select a compliance cap. It proves "
            "only that the warning records do not determine any reported scenario threshold edge."
        ),
        "next_gate": "OPERATOR_OR_ADMINISTRATION_CLASSIFICATION",
        "input_hashes": {name: sha256_file(path) for name, path in paths.items()},
        "output_hashes": {
            "warning_links_retained": sha256_file(warnings_out),
            "threshold_edge_audit": sha256_file(edges_out),
        },
    }
    write_json(decision_out, disposition)

    markdown = "# P.530 Warning Disposition\n\n"
    markdown += f"- Status: **{disposition['status']}**\n"
    markdown += f"- Warning records: **{len(warnings)}**, representing **{len(path_ids)}** physical path.\n"
    markdown += f"- Path length: **{warnings['distance_km'].iloc[0]:.6f} km**, which is **{disposition['distance_below_7_5_km_km']:.6f} km ({disposition['distance_below_7_5_km_pct']:.3f}%)** below the 7.5 km lower edge of the Equation (7) regression dataset.\n"
    markdown += "- All four records are retained. None is deleted or altered.\n"
    markdown += f"- Every reported scenario pass/fail edge is set by non-warning link(s): **{', '.join(binding_links)}**.\n"
    markdown += f"- At the evaluated threshold edges, the binding/global-worst incremental outage is at least **{minimum_ratio:.2f} times** the worst warning-link value.\n"
    markdown += f"- The +10 dB always-on candidate is independently rejected by valid-range link **{valid_worst['link_id']}**.\n"
    markdown += "- This closes the warning as a non-binding documented model-range limitation; it does not select a final cap.\n\n"
    markdown += "## Next gate\n\nObtain operator/administration evidence for network portion, interference-source class, F.1565 parameter choice, and BER-event mapping.\n"
    markdown_out.write_text(markdown, encoding="utf-8")

    # Build a controlled classification template. Prefer the richer allocation-review table if present.
    allocation_review_path = resolve(cfg["inputs"]["allocation_review_csv"])
    if allocation_review_path.is_file():
        source = pd.read_csv(allocation_review_path, dtype={"link_id": str})
    else:
        source = details.sort_values("candidate_i_over_n_db").groupby("link_id", as_index=False).first()

    if "link_id" not in source.columns:
        raise ValueError("Classification source lacks link_id")
    source = source.drop_duplicates("link_id").copy()
    if len(source) != expected_links:
        raise ValueError(f"Expected {expected_links} classification rows, found {len(source)}")

    preferred = [
        "link_id",
        "distance_km",
        "frequency_ghz",
        "tx_digital_capacity_mbps",
        "rx_digital_capacity_mbps",
        "tx_occupied_bandwidth_khz",
        "rx_occupied_bandwidth_khz",
        "tx_modulation",
        "rx_modulation",
        "fade_margin_db",
    ]
    template = source[[c for c in preferred if c in source.columns]].copy()
    required_blank = [
        "network_portion",
        "sharing_class",
        "f1565_parameter_choice",
        "ber_threshold_event_mapping",
        "allocation_scope",
        "allocated_incremental_outage_pct",
        "evidence_reference",
        "reviewer",
        "review_date",
        "review_note",
    ]
    for column in required_blank:
        template[column] = ""
    template_path = resolve(cfg["outputs"]["classification_template"])
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(template_path, index=False)

    request_path = resolve(cfg["outputs"]["classification_request"])
    request_text = """# S1 operator/administration classification request\n\nThe P.530 warning links have been retained and formally shown not to determine any reported threshold edge. The remaining S1 blocker is not numerical precision; it is the missing operational classification.\n\nPlease provide, for each link or for a clearly justified common class:\n\n1. Network portion: `national_access`, `national_shorthaul`, or `national_longhaul`.\n2. Interference source class: `co_primary_interservice_Y10` or `other_source_Z1`.\n3. F.1565 parameter choice: `B=0.075`, `B=0.085`, `C=0.075`, `C=0.085`, `A1=0.01`, or `A1=0.02`, as applicable.\n4. Whether TAFL BER=10^-3 receiver-threshold exceedance is an accepted proxy for the selected G.826/F.1565 performance event; otherwise provide the equipment-specific mapping.\n5. Whether the outage allocation is uniform or link-specific, and the approved numerical allocation.\n6. Evidence reference, reviewer, date, and limitations.\n\nUntil this is supplied, the eight threshold intervals remain conditional sensitivity results and no compliance cap may be frozen.\n"""
    request_path.write_text(request_text, encoding="utf-8")

    disposition["output_hashes"].update(
        {
            "markdown": sha256_file(markdown_out),
            "classification_template": sha256_file(template_path),
            "classification_request": sha256_file(request_path),
        }
    )
    write_json(decision_out, disposition)

    print("P.530 WARNING DISPOSITION: PASS")
    print(f"Warning records retained: {len(warnings)}")
    print(f"Physical warning paths: {len(path_ids)}")
    print(f"Binding link(s) at all scenario edges: {', '.join(binding_links)}")
    print(f"Minimum global-to-warning outage ratio: {minimum_ratio:.6f}")
    print(
        "All-eight conditional interval: "
        f"[{all_eight['highest_passing_candidate_db']}, {all_eight['first_failing_candidate_db']}] dB"
    )
    print("No cap or allocation was selected.")
    print(f"Outputs: {out_dir}")
    print(f"Classification template: {template_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
