#!/usr/bin/env python3
"""Merge all eleven failed-seed diagnoses and choose the next repair class."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import pandas as pd

EXPECTED_SEEDS = [44001, 44007, 44008, 44013, 44017, 44018, 44024, 44025, 44026, 44027, 44028]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--campaign-audit", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    task_root = args.task_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    campaign_audit = json.loads(args.campaign_audit.read_text(encoding="utf-8"))

    seed_summaries: list[dict[str, Any]] = []
    interval_rows: list[dict[str, Any]] = []
    user_frames: list[pd.DataFrame] = []
    classification = Counter()
    missing: list[int] = []
    for seed in EXPECTED_SEEDS:
        seed_dir = task_root / f"seed_{seed}"
        summary_path = seed_dir / "FAILED_SEED_DIAGNOSIS.json"
        detail_path = seed_dir / "INTERVAL_FEASIBILITY_DIAGNOSIS.json"
        user_path = seed_dir / "AFFECTED_USER_DIAGNOSIS.csv"
        if not summary_path.is_file() or not detail_path.is_file() or not user_path.is_file():
            missing.append(seed)
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        details = json.loads(detail_path.read_text(encoding="utf-8"))
        if int(summary["campaign_seed"]) != seed or not bool(summary["channel_reused"]):
            raise RuntimeError(f"invalid diagnosis binding for seed {seed}")
        seed_summaries.append(summary)
        for item in details:
            classification[item["classification"]] += 1
            interval_rows.append({
                "campaign_seed": seed,
                "pass_slot": item["pass_slot"],
                "interval_index": item["interval_index"],
                "interval_seconds": item["interval_seconds"],
                "classification": item["classification"],
                "original_candidate_floor_violation_count": item["original_candidate_floor_violation_count"],
                "current_load_serviceability_mismatch_present": item["current_load_serviceability_mismatch_present"],
                "selected_expanded_local_action": (
                    "NONE"
                    if item["selected_expanded_local_witness"] is None
                    else item["selected_expanded_local_witness"]["scope"]["action_class"]
                ),
                "selected_external_per_user": (
                    None
                    if item["selected_expanded_local_witness"] is None
                    else item["selected_expanded_local_witness"]["scope"]["external_per_user"]
                ),
                "selected_mutable_sector_count": (
                    None
                    if item["selected_expanded_local_witness"] is None
                    else item["selected_expanded_local_witness"]["scope"]["mutable_sector_count"]
                ),
            })
        frame = pd.read_csv(user_path)
        user_frames.append(frame)

    if missing:
        raise RuntimeError(f"missing failed-seed diagnostics: {missing}")
    if [int(v["campaign_seed"]) for v in seed_summaries] != EXPECTED_SEEDS:
        raise RuntimeError("failed-seed diagnostic order mismatch")

    total_intervals = sum(
        int(v["original_unresolved_interval_count"]) for v in seed_summaries
    )
    expanded_certified = sum(
        int(v["expanded_local_certified_interval_count"])
        for v in seed_summaries
    )
    expanded_boundary = sum(
        int(v["expanded_local_boundary_interval_count"])
        for v in seed_summaries
    )
    global_only = sum(
        int(v["strict_global_only_interval_count"])
        for v in seed_summaries
    )
    solver_uncertified = sum(
        int(v["solver_uncertified_interval_count"])
        for v in seed_summaries
    )
    boundary = sum(
        int(v["boundary_only_interval_count"]) for v in seed_summaries
    )
    single_infeasible = sum(
        int(v["fixed_beam_single_user_infeasible_interval_count"])
        for v in seed_summaries
    )
    joint_infeasible = sum(
        int(v["fixed_beam_joint_infeasible_interval_count"])
        for v in seed_summaries
    )
    mismatch = sum(
        int(v["current_load_serviceability_mismatch_interval_count"])
        for v in seed_summaries
    )
    expected_intervals = int(
        campaign_audit["source_supported_facts"][
            "candidate_unresolved_intervals"
        ]
    )
    if total_intervals != expected_intervals:
        raise RuntimeError(
            "diagnosed interval count does not equal campaign unresolved count"
        )
    classified = (
        expanded_certified
        + expanded_boundary
        + global_only
        + solver_uncertified
        + single_infeasible
        + joint_infeasible
    )
    if classified != total_intervals:
        raise RuntimeError(
            f"classification partition mismatch: {classified} != {total_intervals}"
        )

    if expanded_certified == total_intervals:
        decision = "ADAPTIVE_LOCAL_FIXED_BEAM_REPAIR"
        rationale = (
            "All failed intervals have exact witnesses under a bounded expanded "
            "local fixed-beam action with the unchanged floor, EESS constraints, "
            "and strict post-mode sector-power budgets. Implement the smallest "
            "observed adaptive neighbourhood as candidate v4.4 and rerun only "
            "the eleven failed seeds for development closure. The frozen 19 passing "
            "seeds may be reused only to verify no-op identity; a fresh holdout is "
            "required for the final v4.4 generalization claim."
        )
        next_gate = (
            "IMPLEMENT_V4_4_ADAPTIVE_LOCAL_REPAIR_AND_TARGETED_11_SEED_DEVELOPMENT_RERUN"
        )
    elif single_infeasible + joint_infeasible > 0:
        decision = "PROTECTED_SUBBAND_SCHEDULING_REASSIGNMENT_REQUIRED"
        rationale = (
            "At least one interval is solver-certified infeasible for the strict "
            "global fixed-q/fixed-beam stream-power LP. Power redistribution alone "
            "cannot certify the unchanged floor; the next candidate must add a "
            "preregistered protected-subband scheduling or reassignment degree of "
            "freedom. A fairness-policy revision remains unjustified at this stage."
        )
        next_gate = (
            "DESIGN_AND_TEST_FLOOR_FIRST_PROTECTED_SUBBAND_SCHEDULING_ON_11_FAILED_SEEDS_AS_DEVELOPMENT"
        )
    elif solver_uncertified > 0:
        decision = "SOLVER_CERTIFICATE_REFINEMENT_REQUIRED"
        rationale = (
            "No physical infeasibility claim is permitted because at least one "
            "interval remained solver-uncertified. Re-solve only those intervals "
            "with alternate scaling and an independently checked feasibility LP."
        )
        next_gate = "RESOLVE_ONLY_SOLVER_UNCERTIFIED_INTERVALS"
    elif expanded_certified + expanded_boundary == total_intervals:
        decision = "NUMERICAL_INTERIOR_WITNESS_REFINEMENT_REQUIRED"
        rationale = (
            "Every interval is feasible in an expanded local fixed-beam class, but "
            "some witnesses lie on the untightened boundary. Recover a conservative "
            "interior witness without changing the floor or verification tolerance."
        )
        next_gate = "IMPLEMENT_INTERIOR_WITNESS_REFINEMENT_AND_TARGETED_11_SEED_DEVELOPMENT_RERUN"
    else:
        decision = "BROADER_COORDINATION_OR_SCHEDULING_REQUIRED"
        rationale = (
            "The strict global fixed-beam class is feasible in the remaining "
            "intervals, but the tested bounded local scopes are not. Either a "
            "larger distributed coordination neighbourhood or protected-subband "
            "scheduling is required; a fairness-policy revision is not justified."
        )
        next_gate = (
            "DESIGN_MINIMUM_COORDINATION_OR_SCHEDULING_EXTENSION_AND_TARGETED_11_SEED_DEVELOPMENT_RERUN"
        )

    if mismatch > 0:
        policy_note = (
            "Some intervals contain users admitted by full-load eligibility whose current-load nominal rate is below "
            "the absolute 0.1 floor. This is a policy-consistency risk, but policy revision remains a last resort after "
            "the scheduling/reassignment test."
        )
    else:
        policy_note = "No current-load absolute-floor serviceability mismatch was identified."

    decision_record = {
        "schema_version": 1,
        "status": "PASS_COMPLETE_FAILED_SEED_FEASIBILITY_DIAGNOSIS",
        "failed_seed_count": len(seed_summaries),
        "diagnosed_unresolved_interval_count": total_intervals,
        "classification_counts": dict(classification),
        "expanded_local_certified_interval_count": expanded_certified,
        "expanded_local_boundary_interval_count": expanded_boundary,
        "strict_global_only_interval_count": global_only,
        "solver_uncertified_interval_count": solver_uncertified,
        "boundary_only_interval_count": boundary,
        "fixed_beam_single_user_infeasible_interval_count": single_infeasible,
        "fixed_beam_joint_global_infeasible_interval_count": joint_infeasible,
        "current_load_serviceability_mismatch_interval_count": mismatch,
        "next_repair_decision": decision,
        "rationale": rationale,
        "policy_note": policy_note,
        "next_gate": next_gate,
        "candidate_v4_3_source_changed": False,
        "campaign_rerun_performed": False,
        "channel_regeneration_performed": False,
        "fresh_holdout_required_after_any_v4_4_source_change": True,
        "current_30_seed_campaign_role_after_adaptation": "DEVELOPMENT_AND_STRESS_TEST_NOT_CLEAN_V4_4_CONFIRMATION",
        "paper_use_boundary": "DIAGNOSTIC_RESULT_REQUIRES_INDEPENDENT_REVIEW_BEFORE_METHOD_REVISION",
        "walltime_policy": {
            "observed_original_worker_max": campaign_audit["resource_audit"]["observed_worker_elapsed_seconds_max"],
            "future_equivalent_worker_walltime": "00:10:00",
            "diagnostic_worker_walltime": "00:15:00",
            "merge_walltime": "00:05:00"
        }
    }
    (output / "NEXT_REPAIR_DECISION.json").write_text(
        json.dumps(decision_record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    pd.DataFrame(seed_summaries).to_json(output / "FAILED_SEED_DIAGNOSIS_SUMMARY.json", orient="records", indent=2)
    pd.DataFrame(interval_rows).to_csv(output / "INTERVAL_CLASSIFICATION_SUMMARY.csv", index=False)
    if user_frames:
        users = pd.concat(user_frames, ignore_index=True)
        users.to_csv(output / "AFFECTED_USER_DIAGNOSIS_ALL_SEEDS.csv", index=False)
        aggregate = users.groupby(["user_index", "user_id"], dropna=False).agg(
            diagnosed_interval_count=("interval_index", "count"),
            seed_count=("campaign_seed", "nunique"),
            minimum_current_load_nominal_rate=("current_load_nominal_total_rate_bps_hz", "min"),
            minimum_optimistic_total_rate=("optimistic_total_rate_bps_hz", "min"),
            maximum_floor=("floor_bps_hz", "max"),
            serviceability_mismatch_count=("current_load_serviceability_mismatch", "sum"),
        ).reset_index()
        aggregate.to_csv(output / "AFFECTED_USER_AGGREGATE.csv", index=False)

    print("FAILED_SEED_DIAGNOSIS_MERGE=PASS")
    print(f"DIAGNOSTIC_SEED_RETURN_COUNT={len(seed_summaries)}")
    print(f"DIAGNOSED_UNRESOLVED_INTERVAL_COUNT={total_intervals}")
    print(
        f"EXPANDED_LOCAL_CERTIFIED_INTERVAL_COUNT={expanded_certified}"
    )
    print(f"EXPANDED_LOCAL_BOUNDARY_INTERVAL_COUNT={expanded_boundary}")
    print(f"STRICT_GLOBAL_ONLY_INTERVAL_COUNT={global_only}")
    print(f"SOLVER_UNCERTIFIED_INTERVAL_COUNT={solver_uncertified}")
    print(f"FIXED_BEAM_SINGLE_USER_INFEASIBLE_INTERVAL_COUNT={single_infeasible}")
    print(f"FIXED_BEAM_JOINT_GLOBAL_INFEASIBLE_INTERVAL_COUNT={joint_infeasible}")
    print(f"CURRENT_LOAD_SERVICEABILITY_MISMATCH_INTERVAL_COUNT={mismatch}")
    print(f"NEXT_REPAIR_DECISION={decision}")
    print(f"NEXT_GATE={next_gate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
