#!/usr/bin/env python3
"""Merge the 11-seed candidate-v4.4 scheduling development replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FAILED_SEEDS = [
    44001, 44007, 44008, 44013, 44017, 44018,
    44024, 44025, 44026, 44027, 44028,
]
ALL_SEEDS = list(range(44000, 44030))
OLD_CANDIDATE = "candidate_v4_3_floor_feasibility_repair"
NEW_CANDIDATE = "candidate_v4_4_floor_first_protected_subband_scheduling"
STATIC = "static_robust_constrained_pf_with_sector_selective_fallback"
PREDICTIVE = "robust_predictive_constrained_pf_with_sector_selective_fallback"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def bootstrap(values: np.ndarray, seed: int, resamples: int = 10000) -> dict[str, Any]:
    values = np.asarray(values, dtype=np.float64)
    if values.shape != (30,):
        raise ValueError(f"bootstrap requires 30 seed-cluster effects, got {values.shape}")
    rng = np.random.default_rng(int(seed))
    index = rng.integers(0, len(values), size=(int(resamples), len(values)))
    means = values[index].mean(axis=1)
    return {
        "point_estimate": float(values.mean()),
        "lower_95": float(np.quantile(means, 0.025)),
        "median_bootstrap_mean": float(np.quantile(means, 0.5)),
        "upper_95": float(np.quantile(means, 0.975)),
        "seed_cluster_standard_deviation": float(values.std(ddof=1)),
        "bootstrap_resamples": int(resamples),
        "bootstrap_seed": int(seed),
    }


def merge_counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    merged: dict[str, int] = {}
    for record in records:
        for name, value in dict(record.get(key, {})).items():
            merged[str(name)] = merged.get(str(name), 0) + int(value)
    return dict(sorted(merged.items(), key=lambda item: int(item[0])))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--campaign-run-root", type=Path, required=True)
    parser.add_argument("--diagnosis-audit", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    task_root = args.task_root.resolve()
    campaign_root = args.campaign_run_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    diagnosis = json.loads(args.diagnosis_audit.read_text(encoding="utf-8"))
    if diagnosis["status"] != "PASS_IMMUTABLE_FAILED_SEED_DIAGNOSIS_AUDIT":
        raise RuntimeError("failed-seed diagnosis audit did not pass")
    if int(diagnosis["diagnosed_unresolved_interval_count"]) != 1736:
        raise RuntimeError("diagnosis unresolved-interval binding mismatch")

    new_frames: list[pd.DataFrame] = []
    seed_records: list[dict[str, Any]] = []
    missing: list[int] = []
    for seed in FAILED_SEEDS:
        result_root = task_root / f"seed_{seed}" / "result"
        summary_path = result_root / "V44_SCHEDULING_SEED_RESULT.json"
        cell_path = result_root / "CELL_SUMMARY.csv"
        if not summary_path.is_file() or not cell_path.is_file():
            missing.append(seed)
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if int(summary["campaign_seed"]) != seed:
            raise RuntimeError(f"seed-summary mismatch: {seed}")
        seed_records.append(summary)
        frame = pd.read_csv(cell_path)
        frame["campaign_seed"] = seed
        new_frames.append(frame)
    if missing:
        raise RuntimeError(f"missing v4.4 seed returns: {missing}")
    if len(seed_records) != len(FAILED_SEEDS):
        raise RuntimeError("v4.4 seed-result count mismatch")

    new_cells = pd.concat(new_frames, ignore_index=True)
    new_cells.to_csv(output / "V44_FAILED_SEED_CELL_SUMMARY.csv", index=False)

    # Construct the all-30 post-adaptation development/stress estimate.  The 19
    # v4.3 hard-pass seeds are a code-path identity reuse: v4.4 invokes the new
    # scheduler only after v4.3 reports an unresolved deployable interval.
    development_rows: list[dict[str, Any]] = []
    seed_effect_rows: list[dict[str, Any]] = []
    failed_set = set(FAILED_SEEDS)
    for seed in ALL_SEEDS:
        original_path = (
            campaign_root / "results" / f"seed_{seed}" / "result" / "CELL_SUMMARY.csv"
        )
        if not original_path.is_file():
            raise RuntimeError(f"original campaign cell summary missing: seed {seed}")
        original = pd.read_csv(original_path)
        if seed in failed_set:
            candidate_rows = new_cells[
                (new_cells["campaign_seed"] == seed)
                & (new_cells["method_id"] == NEW_CANDIDATE)
            ].copy()
            candidate_rows["development_source"] = "EXECUTED_V4_4_FAILED_SEED_REPLAY"
        else:
            candidate_rows = original[original["method_id"] == OLD_CANDIDATE].copy()
            candidate_rows["method_id"] = NEW_CANDIDATE
            candidate_rows["campaign_seed"] = seed
            candidate_rows["development_source"] = "V4_3_EXACT_NOOP_CODE_PATH_REUSE"
        static_rows = original[original["method_id"] == STATIC].sort_values("pass_slot")
        predictive_rows = original[original["method_id"] == PREDICTIVE].sort_values("pass_slot")
        candidate_rows = candidate_rows.sort_values("pass_slot")
        if not (len(candidate_rows) == len(static_rows) == len(predictive_rows) == 5):
            raise RuntimeError(f"pass-row count mismatch: seed {seed}")
        development_rows.extend(dict(row) for _, row in candidate_rows.iterrows())
        seed_effect_rows.append({
            "campaign_seed": seed,
            "candidate_minus_static_final_pf": float(np.mean(
                candidate_rows["final_moving_pf_utility"].to_numpy()
                - static_rows["final_moving_pf_utility"].to_numpy()
            )),
            "candidate_minus_static_duration_mean_pf": float(np.mean(
                candidate_rows["duration_weighted_mean_moving_pf_utility"].to_numpy()
                - static_rows["duration_weighted_mean_moving_pf_utility"].to_numpy()
            )),
            "candidate_minus_predictive_final_pf": float(np.mean(
                candidate_rows["final_moving_pf_utility"].to_numpy()
                - predictive_rows["final_moving_pf_utility"].to_numpy()
            )),
            "candidate_minus_predictive_duration_mean_pf": float(np.mean(
                candidate_rows["duration_weighted_mean_moving_pf_utility"].to_numpy()
                - predictive_rows["duration_weighted_mean_moving_pf_utility"].to_numpy()
            )),
        })

    development = pd.DataFrame(development_rows)
    effects = pd.DataFrame(seed_effect_rows)
    development.to_csv(
        output / "V44_ALL30_DEVELOPMENT_CANDIDATE_CELLS.csv", index=False
    )
    effects.to_csv(output / "V44_ALL30_DEVELOPMENT_SEED_EFFECTS.csv", index=False)

    hard_pass_count = int(sum(bool(v["candidate_hard_gates_pass"]) for v in seed_records))
    bounded_scope_count = int(sum(bool(v["bounded_schedule_scope_pass"]) for v in seed_records))
    original_unresolved = int(sum(
        int(v["original_v4_3_unresolved_intervals"]) for v in seed_records
    ))
    schedule_success = int(sum(int(v["scheduling_success_intervals"]) for v in seed_records))
    schedule_failure = int(sum(int(v["scheduling_failure_intervals"]) for v in seed_records))
    diagnostic_g8 = int(sum(
        int(v["diagnostic_g8_scheduling_feasible_intervals"])
        for v in seed_records
    ))
    if original_unresolved != 1736 or schedule_success + schedule_failure != 1736:
        raise RuntimeError(
            "v4.4 scheduling coverage mismatch: "
            f"original={original_unresolved}, success={schedule_success}, "
            f"failure={schedule_failure}"
        )

    guard_counts = merge_counts(seed_records, "schedule_guard_limit_counts")
    maximum_guard_limit = max((int(v) for v in guard_counts), default=0)
    maximum_guard_count = max(
        int(v["maximum_schedule_guard_sector_count"]) for v in seed_records
    )
    maximum_critical = max(
        int(v["maximum_schedule_critical_sector_count"]) for v in seed_records
    )
    maximum_mutable = max(
        int(v["maximum_schedule_mutable_sector_count"]) for v in seed_records
    )
    maximum_mode_count = max(
        int(v["maximum_schedule_mode_count"]) for v in seed_records
    )
    maximum_nonzero_modes = max(
        int(v["maximum_schedule_nonzero_mode_count"]) for v in seed_records
    )
    maximum_scheduled_fraction = max(
        float(v["maximum_protected_subband_scheduled_fraction"])
        for v in seed_records
    )
    maximum_schedule_solver_seconds = max(
        float(v["maximum_schedule_solver_seconds"]) for v in seed_records
    )

    floor_seconds = int(sum(
        int(v["candidate_floor_violation_user_seconds"]) for v in seed_records
    ))
    floor_intervals = int(sum(
        int(v["candidate_floor_violation_user_intervals"]) for v in seed_records
    ))
    long_seconds = int(sum(
        int(v["candidate_long_eess_violation_seconds"]) for v in seed_records
    ))
    short_seconds = int(sum(
        int(v["candidate_short_eess_violation_seconds"]) for v in seed_records
    ))

    primary = bootstrap(effects["candidate_minus_static_final_pf"].to_numpy(), 20260805)
    secondary = bootstrap(
        effects["candidate_minus_static_duration_mean_pf"].to_numpy(), 20260806
    )
    predictive_final = bootstrap(
        effects["candidate_minus_predictive_final_pf"].to_numpy(), 20260807
    )
    predictive_duration = bootstrap(
        effects["candidate_minus_predictive_duration_mean_pf"].to_numpy(), 20260808
    )

    all_hard = bool(
        hard_pass_count == 11
        and bounded_scope_count == 11
        and schedule_success == 1736
        and schedule_failure == 0
        and diagnostic_g8 == 0
        and floor_seconds == 0
        and floor_intervals == 0
        and long_seconds == 0
        and short_seconds == 0
        and maximum_guard_limit <= 4
        and maximum_guard_count <= 4
        and maximum_critical <= 4
    )
    if all_hard:
        status = "PASS_V4_4_FLOOR_FIRST_PROTECTED_SUBBAND_SCHEDULING_DEVELOPMENT"
        next_decision = (
            "FREEZE_V4_4_BEGIN_TWC_DRAFT_AND_RUN_FRESH_HOLDOUT_IN_PARALLEL"
        )
        next_gate = (
            "FREEZE_V4_4_START_13_PAGE_TWC_DRAFT_AND_RUN_FRESH_HOLDOUT_44030_44059"
        )
    elif diagnostic_g8 > 0 and schedule_failure == diagnostic_g8:
        status = "V4_4_DEPLOYABLE_G4_SCOPE_INSUFFICIENT_DIAGNOSTIC_G8_FEASIBLE"
        next_decision = "REVIEW_COORDINATION_SCOPE_OR_USER_REASSIGNMENT"
        next_gate = "CHOOSE_BOUNDED_GUARD_SCOPE_OR_PROTECTED_SUBBAND_REASSIGNMENT"
    elif schedule_failure > 0:
        status = "V4_4_PROTECTED_SUBBAND_SCHEDULING_DEVELOPMENT_INCOMPLETE"
        next_decision = "PROTECTED_SUBBAND_REASSIGNMENT_OR_ADMISSION_REQUIRED"
        next_gate = "DESIGN_USER_REASSIGNMENT_OR_PREREGISTERED_ADMISSION_FALLBACK"
    else:
        status = "V4_4_SCHEDULING_HARD_OR_SCOPE_GATE_REVIEW_REQUIRED"
        next_decision = "REVIEW_FAILED_HARD_OR_DISTRIBUTED_SCOPE_GATE"
        next_gate = "REVIEW_V4_4_INTERVAL_CERTIFICATES_BEFORE_FREEZE"

    summary = {
        "schema_version": 2,
        "status": status,
        "failed_seed_count": 11,
        "failed_seed_return_count": len(seed_records),
        "failed_seed_hard_gate_pass_count": hard_pass_count,
        "failed_seed_bounded_scope_pass_count": bounded_scope_count,
        "original_v4_3_unresolved_interval_count": original_unresolved,
        "scheduling_success_interval_count": schedule_success,
        "scheduling_failure_interval_count": schedule_failure,
        "diagnostic_g8_scheduling_feasible_interval_count": diagnostic_g8,
        "schedule_guard_limit_counts": guard_counts,
        "maximum_schedule_guard_sector_limit": maximum_guard_limit,
        "maximum_schedule_guard_sector_count": maximum_guard_count,
        "maximum_schedule_critical_sector_count": maximum_critical,
        "maximum_schedule_mutable_sector_count": maximum_mutable,
        "maximum_schedule_mode_count": maximum_mode_count,
        "maximum_schedule_nonzero_mode_count": maximum_nonzero_modes,
        "maximum_protected_subband_scheduled_fraction": maximum_scheduled_fraction,
        "maximum_schedule_solver_seconds": maximum_schedule_solver_seconds,
        "schedule_slots_per_second": 2000,
        "slot_duration_seconds": 0.0005,
        "candidate_floor_violation_user_seconds": floor_seconds,
        "candidate_floor_violation_user_intervals": floor_intervals,
        "candidate_long_eess_violation_seconds": long_seconds,
        "candidate_short_eess_violation_seconds": short_seconds,
        "all30_development_primary_candidate_minus_static": primary,
        "all30_development_secondary_candidate_minus_static": secondary,
        "all30_development_candidate_minus_predictive_final": predictive_final,
        "all30_development_candidate_minus_predictive_duration": predictive_duration,
        "next_repair_decision": next_decision,
        "next_gate": next_gate,
        "current_30_seed_campaign_role": (
            "DEVELOPMENT_AND_STRESS_TEST_AFTER_V4_4_ADAPTATION_NOT_CLEAN_CONFIRMATION"
        ),
        "fresh_holdout_required": True,
        "proposed_fresh_holdout_seeds": list(range(44030, 44060)),
        "information_exchange_locality_certified": False,
        "manuscript_start_policy": (
            "BEGIN_13_PAGE_TWC_DRAFT_IMMEDIATELY_AFTER_ALL_11_DEVELOPMENT_SEEDS_PASS; "
            "RUN_FRESH_HOLDOUT_AND_COMPACT_PRACTICALITY_STUDY_IN_PARALLEL"
        ),
        "claim_boundary": (
            "V4_4_POST_CAMPAIGN_DEVELOPMENT_RESULT_NOT_FRESH_CONFIRMATION_"
            "NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE"
        ),
        "resource_policy": {
            "worker_walltime": "00:10:00",
            "worker_memory_gib": 16,
            "worker_cpus": 8,
            "merge_walltime": "00:05:00",
            "merge_memory_gib": 8,
            "merge_cpus": 4,
            "gpu_requested": False,
            "channel_regenerated": False,
        },
    }
    write_json(output / "V44_SCHEDULING_DEVELOPMENT_SUMMARY.json", summary)
    pd.DataFrame([{
        "campaign_seed": int(v["campaign_seed"]),
        "candidate_hard_gates_pass": bool(v["candidate_hard_gates_pass"]),
        "bounded_schedule_scope_pass": bool(v["bounded_schedule_scope_pass"]),
        "original_v4_3_unresolved_intervals": int(v["original_v4_3_unresolved_intervals"]),
        "scheduling_success_intervals": int(v["scheduling_success_intervals"]),
        "scheduling_failure_intervals": int(v["scheduling_failure_intervals"]),
        "diagnostic_g8_intervals": int(v["diagnostic_g8_scheduling_feasible_intervals"]),
        "maximum_guard_sector_count": int(v["maximum_schedule_guard_sector_count"]),
        "maximum_critical_sector_count": int(v["maximum_schedule_critical_sector_count"]),
        "maximum_mutable_sector_count": int(v["maximum_schedule_mutable_sector_count"]),
        "maximum_scheduled_fraction": float(v["maximum_protected_subband_scheduled_fraction"]),
        "maximum_schedule_solver_seconds": float(v["maximum_schedule_solver_seconds"]),
        "floor_violation_user_seconds": int(v["candidate_floor_violation_user_seconds"]),
        "long_eess_violation_seconds": int(v["candidate_long_eess_violation_seconds"]),
        "short_eess_violation_seconds": int(v["candidate_short_eess_violation_seconds"]),
        "runtime_seconds": float(v["runtime_seconds"]),
    } for v in seed_records]).to_csv(
        output / "V44_FAILED_SEED_HARD_GATE_SUMMARY.csv", index=False
    )

    print(f"V44_SCHEDULING_DEVELOPMENT_STATUS={status}")
    print(f"FAILED_SEED_HARD_GATE_PASS_COUNT={hard_pass_count}")
    print(f"FAILED_SEED_BOUNDED_SCOPE_PASS_COUNT={bounded_scope_count}")
    print(f"ORIGINAL_V4_3_UNRESOLVED_INTERVAL_COUNT={original_unresolved}")
    print(f"SCHEDULING_SUCCESS_INTERVAL_COUNT={schedule_success}")
    print(f"SCHEDULING_FAILURE_INTERVAL_COUNT={schedule_failure}")
    print(f"DIAGNOSTIC_G8_SCHEDULING_FEASIBLE_INTERVAL_COUNT={diagnostic_g8}")
    print(f"SCHEDULE_GUARD_LIMIT_COUNTS={json.dumps(guard_counts, sort_keys=True)}")
    print(f"MAXIMUM_SCHEDULE_GUARD_SECTOR_COUNT={maximum_guard_count}")
    print(f"MAXIMUM_SCHEDULE_CRITICAL_SECTOR_COUNT={maximum_critical}")
    print(f"MAXIMUM_SCHEDULE_MUTABLE_SECTOR_COUNT={maximum_mutable}")
    print(f"MAXIMUM_PROTECTED_SUBBAND_SCHEDULED_FRACTION={maximum_scheduled_fraction}")
    print(f"MAXIMUM_SCHEDULE_SOLVER_SECONDS={maximum_schedule_solver_seconds}")
    print(f"CANDIDATE_FLOOR_VIOLATION_USER_SECONDS={floor_seconds}")
    print(f"CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS={floor_intervals}")
    print(f"CANDIDATE_LONG_EESS_VIOLATION_SECONDS={long_seconds}")
    print(f"CANDIDATE_SHORT_EESS_VIOLATION_SECONDS={short_seconds}")
    print(f"DEVELOPMENT_PRIMARY_POINT_ESTIMATE={primary['point_estimate']}")
    print(f"DEVELOPMENT_PRIMARY_LOWER_95={primary['lower_95']}")
    print(f"NEXT_REPAIR_DECISION={next_decision}")
    print(f"NEXT_GATE={next_gate}")
    return 0 if all_hard else 42


if __name__ == "__main__":
    raise SystemExit(main())
