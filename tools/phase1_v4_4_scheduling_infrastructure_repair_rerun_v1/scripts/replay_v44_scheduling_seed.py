#!/usr/bin/env python3
"""Replay candidate-v4.4 scheduling on one preserved failed campaign seed.

This is a post-campaign development replay.  It reuses the exact frozen channel
and all five protected-pass records.  The eight comparator methods must
reproduce exactly.  Candidate v4.4 is allowed to differ only because it adds the
bounded floor-first protected-subband scheduling fallback after v4.3 exhausts
its deployable fixed-beam actions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Any

import numpy as np
import pandas as pd

FAILED_SEEDS = {
    44001, 44007, 44008, 44013, 44017, 44018,
    44024, 44025, 44026, 44027, 44028,
}
EXPECTED_PACKAGE_ID = (
    "8473d5504e69347a69a536c43dcae35bec9519a90bc55de3a0712f9e0fb97889"
)
OLD_CANDIDATE = "candidate_v4_3_floor_feasibility_repair"
NEW_CANDIDATE = "candidate_v4_4_floor_first_protected_subband_scheduling"
STATIC = "static_robust_constrained_pf_with_sector_selective_fallback"
PREDICTIVE = "robust_predictive_constrained_pf_with_sector_selective_fallback"


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _json_default(value: object) -> object:
    """Convert NumPy containers/scalars without changing scientific values."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(
        f"Object of type {value.__class__.__name__} is not JSON serializable"
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        + "\n",
        encoding="utf-8",
    )


def _sum_diag(pass_audits: list[dict[str, Any]], key: str) -> int:
    return int(sum(
        int(audit["candidate_action_diagnostics"].get(key, 0))
        for audit in pass_audits
    ))


def _max_diag(pass_audits: list[dict[str, Any]], key: str) -> float:
    return float(max(
        (
            float(audit["candidate_action_diagnostics"].get(key, 0.0))
            for audit in pass_audits
        ),
        default=0.0,
    ))


def _merge_counter(pass_audits: list[dict[str, Any]], key: str) -> dict[str, int]:
    merged: dict[str, int] = {}
    for audit in pass_audits:
        values = audit["candidate_action_diagnostics"].get(key, {})
        for name, count in dict(values).items():
            merged[str(name)] = merged.get(str(name), 0) + int(count)
    return dict(sorted(merged.items(), key=lambda item: int(item[0])))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--campaign-run-root", type=Path, required=True)
    parser.add_argument("--job-package-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    seed = int(args.seed)
    if seed not in FAILED_SEEDS:
        raise RuntimeError(f"seed outside frozen failed-seed set: {seed}")
    run_root = args.campaign_run_root.resolve()
    job_root = args.job_package_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    contract = json.loads(
        (job_root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8")
    )
    if contract["package_id"] != EXPECTED_PACKAGE_ID:
        raise RuntimeError("job-package ID mismatch")

    # The remote wrapper copies the new modules into a run-specific extraction
    # of the immutable job package.  The reviewed v4.3 ZIP remains unchanged.
    sys.path.insert(0, str(job_root))
    sys.path.insert(0, str(job_root / "src"))
    import phase1_seed_worker as worker  # type: ignore
    from fr3_cbf.candidate_v4_4_scheduling_campaign import (  # type: ignore
        CANDIDATE_METHOD_ID,
        run_candidate_v4_4,
    )

    if CANDIDATE_METHOD_ID != NEW_CANDIDATE:
        raise RuntimeError("candidate-v4.4 method ID mismatch")
    worker.run_candidate_v4_3 = run_candidate_v4_4
    worker.CANDIDATE_METHOD_ID = NEW_CANDIDATE
    worker.METHOD_IDS = tuple(
        NEW_CANDIDATE if value == OLD_CANDIDATE else value
        for value in worker.METHOD_IDS
    )

    seed_root = run_root / "results" / f"seed_{seed}"
    channel_root = seed_root / "channel"
    original_result_root = seed_root / "result"
    original_seed_result_path = original_result_root / "SEED_RESULT.json"
    original_cell_path = original_result_root / "CELL_SUMMARY.csv"
    required_files = (
        channel_root / "CHANNEL_RECORD.json",
        channel_root / "frequency_response.npy",
        original_seed_result_path,
        original_cell_path,
    )
    for required in required_files:
        if not required.is_file():
            raise RuntimeError(f"preserved input missing: {required}")
    original_seed = json.loads(
        original_seed_result_path.read_text(encoding="utf-8")
    )
    if int(original_seed["campaign_seed"]) != seed:
        raise RuntimeError("preserved seed-result mismatch")
    if bool(original_seed["candidate_hard_gates_pass"]):
        raise RuntimeError("development replay must target a failed v4.3 seed")

    channel_record = json.loads(
        (channel_root / "CHANNEL_RECORD.json").read_text(encoding="utf-8")
    )
    if int(channel_record["campaign_seed"]) != seed:
        raise RuntimeError("channel-record seed mismatch")

    started = time.perf_counter()
    data = worker.load_channel(channel_root)
    campaign_contract = json.loads(
        (job_root / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json").read_text(
            encoding="utf-8"
        )
    )
    pass_temp = output / "pass_extract"
    pass_roots = [worker.extract_pass(slot, pass_temp) for slot in range(5)]
    pass_lengths = [
        len(np.load(path / "protected_time_s.npy")) for path in pass_roots
    ]
    (
        architecture,
        _h_effective,
        full_state,
        architecture_audit,
        schedules,
        state_cache,
    ) = worker.create_states(data, campaign_contract, pass_lengths)

    result_root = output / "result"
    result_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    pass_audits: list[dict[str, Any]] = []
    for slot, pass_root in enumerate(pass_roots):
        pass_rows, pass_audit = worker.pass_evaluation(
            slot,
            pass_root,
            data,
            campaign_contract,
            architecture,
            full_state,
            schedules[slot],
            state_cache,
            result_root,
        )
        for row in pass_rows:
            row["campaign_seed"] = seed
            row["development_replay"] = True
        rows.extend(pass_rows)
        pass_audits.append(pass_audit)

    frame = pd.DataFrame(rows)
    frame.to_csv(result_root / "CELL_SUMMARY.csv", index=False)
    write_json(result_root / "PASS_AUDITS.json", pass_audits)

    # Exact comparator reproduction is a source-binding gate. Candidate v4.4
    # is intentionally new; all eight frozen comparators must be unchanged.
    original_cells = pd.read_csv(original_cell_path)
    compare_columns = [
        "final_moving_pf_utility",
        "duration_weighted_mean_moving_pf_utility",
        "long_violation_seconds",
        "short_violation_seconds",
        "eligible_floor_violation_user_seconds",
        "eligible_floor_violation_user_intervals",
    ]
    maximum_comparator_error = 0.0
    for method in sorted(set(original_cells["method_id"]) - {OLD_CANDIDATE}):
        old = original_cells[original_cells["method_id"] == method].sort_values(
            "pass_slot"
        )
        new = frame[frame["method_id"] == method].sort_values("pass_slot")
        if len(old) != 5 or len(new) != 5:
            raise RuntimeError(f"comparator row-count mismatch: {method}")
        for column in compare_columns:
            error = float(np.max(np.abs(
                old[column].to_numpy(dtype=np.float64)
                - new[column].to_numpy(dtype=np.float64)
            )))
            maximum_comparator_error = max(maximum_comparator_error, error)
    if maximum_comparator_error > 1e-12:
        raise RuntimeError(
            "frozen comparator reproduction failed: "
            f"maximum error {maximum_comparator_error:.17g}"
        )

    paired_rows: list[dict[str, Any]] = []
    for pass_slot, group in frame.groupby("pass_slot", sort=True):
        indexed = group.set_index("method_id")
        candidate = indexed.loc[NEW_CANDIDATE]
        static = indexed.loc[STATIC]
        predictive = indexed.loc[PREDICTIVE]
        paired_rows.append({
            "campaign_seed": seed,
            "pass_slot": int(pass_slot),
            "candidate_minus_static_final_pf": float(
                candidate["final_moving_pf_utility"]
                - static["final_moving_pf_utility"]
            ),
            "candidate_minus_static_duration_mean_pf": float(
                candidate["duration_weighted_mean_moving_pf_utility"]
                - static["duration_weighted_mean_moving_pf_utility"]
            ),
            "candidate_minus_predictive_final_pf": float(
                candidate["final_moving_pf_utility"]
                - predictive["final_moving_pf_utility"]
            ),
            "candidate_minus_predictive_duration_mean_pf": float(
                candidate["duration_weighted_mean_moving_pf_utility"]
                - predictive["duration_weighted_mean_moving_pf_utility"]
            ),
        })
    pd.DataFrame(paired_rows).to_csv(
        result_root / "PRIMARY_PAIRED_EFFECTS.csv", index=False
    )

    candidate_cells = frame[frame["method_id"] == NEW_CANDIDATE]
    scheduling_success = _sum_diag(
        pass_audits, "protected_subband_scheduling_success_intervals"
    )
    scheduling_failure = _sum_diag(
        pass_audits, "protected_subband_scheduling_failure_intervals"
    )
    diagnostic_g8 = _sum_diag(
        pass_audits, "diagnostic_g8_scheduling_feasible_intervals"
    )
    original_unresolved = int(sum(
        int(record["candidate_hard_gates"]["unresolved_deployable_intervals"])
        for record in original_seed["pass_audits"]
    ))
    if scheduling_success + scheduling_failure != original_unresolved:
        raise RuntimeError(
            "scheduling invocation count does not reproduce the original "
            f"unresolved interval count: {scheduling_success}+{scheduling_failure} "
            f"!= {original_unresolved}"
        )

    guard_counts = _merge_counter(
        pass_audits, "protected_subband_scheduling_guard_limit_counts"
    )
    maximum_guard_limit = max((int(v) for v in guard_counts), default=0)
    maximum_guard_count = int(_max_diag(
        pass_audits, "maximum_schedule_guard_sector_count"
    ))
    maximum_mutable = int(_max_diag(
        pass_audits, "maximum_schedule_mutable_sector_count"
    ))
    maximum_critical = int(_max_diag(
        pass_audits, "maximum_schedule_critical_sector_count"
    ))
    maximum_mode_count = int(_max_diag(
        pass_audits, "maximum_schedule_mode_count"
    ))
    maximum_nonzero_modes = int(_max_diag(
        pass_audits, "maximum_schedule_nonzero_mode_count"
    ))
    maximum_scheduled_fraction = _max_diag(
        pass_audits, "maximum_protected_subband_scheduled_fraction"
    )
    maximum_schedule_solver_seconds = _max_diag(
        pass_audits, "schedule_solver_seconds_max"
    )

    hard_pass = bool(
        int(candidate_cells["long_violation_seconds"].sum()) == 0
        and int(candidate_cells["short_violation_seconds"].sum()) == 0
        and int(candidate_cells["eligible_floor_violation_user_seconds"].sum()) == 0
        and int(candidate_cells["eligible_floor_violation_user_intervals"].sum()) == 0
        and scheduling_failure == 0
        and diagnostic_g8 == 0
        and all(
            audit["candidate_hard_gates"]["strict_local_scope_gate"] == "PASS"
            and audit["candidate_hard_gates"][
                "strict_post_mode_selected_power_gate"
            ] == "PASS"
            and int(audit["candidate_hard_gates"]["q0_envelope_deployable_actions"]) == 0
            and int(audit["candidate_hard_gates"]["unresolved_deployable_intervals"]) == 0
            and int(audit["candidate_hard_gates"]["network_wide_shutdown_intervals"]) == 0
            for audit in pass_audits
        )
    )
    bounded_scope = bool(
        maximum_guard_limit <= 4
        and maximum_guard_count <= 4
        and maximum_critical <= 4
    )

    # A compact per-pass scheduling table is convenient for scientific review.
    pass_schedule_rows = []
    for audit in pass_audits:
        diag = audit["candidate_action_diagnostics"]
        pass_schedule_rows.append({
            "pass_slot": int(audit["pass_slot"]),
            "scheduling_success_intervals": int(
                diag.get("protected_subband_scheduling_success_intervals", 0)
            ),
            "scheduling_failure_intervals": int(
                diag.get("protected_subband_scheduling_failure_intervals", 0)
            ),
            "diagnostic_g8_feasible_intervals": int(
                diag.get("diagnostic_g8_scheduling_feasible_intervals", 0)
            ),
            "maximum_scheduled_fraction": float(
                diag.get("maximum_protected_subband_scheduled_fraction", 0.0)
            ),
            "maximum_guard_sector_count": int(
                diag.get("maximum_schedule_guard_sector_count", 0)
            ),
            "maximum_mutable_sector_count": int(
                diag.get("maximum_schedule_mutable_sector_count", 0)
            ),
            "maximum_mode_count": int(diag.get("maximum_schedule_mode_count", 0)),
            "schedule_solver_seconds_max": float(
                diag.get("schedule_solver_seconds_max", 0.0)
            ),
        })
    pd.DataFrame(pass_schedule_rows).to_csv(
        result_root / "SCHEDULING_PASS_SUMMARY.csv", index=False
    )

    summary = {
        "schema_version": 2,
        "status": (
            "PASS_V4_4_SCHEDULING_DEVELOPMENT_SEED"
            if hard_pass and bounded_scope
            else "REVIEW_V4_4_SCHEDULING_DEVELOPMENT_SEED"
        ),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_seed": seed,
        "candidate_method_id": NEW_CANDIDATE,
        "candidate_source_changed": True,
        "channel_reused": True,
        "channel_regenerated": False,
        "gpu_requested": False,
        "candidate_hard_gates_pass": hard_pass,
        "bounded_schedule_scope_pass": bounded_scope,
        "original_v4_3_unresolved_intervals": original_unresolved,
        "scheduling_success_intervals": scheduling_success,
        "scheduling_failure_intervals": scheduling_failure,
        "diagnostic_g8_scheduling_feasible_intervals": diagnostic_g8,
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
        "candidate_floor_violation_user_seconds": int(
            candidate_cells["eligible_floor_violation_user_seconds"].sum()
        ),
        "candidate_floor_violation_user_intervals": int(
            candidate_cells["eligible_floor_violation_user_intervals"].sum()
        ),
        "candidate_long_eess_violation_seconds": int(
            candidate_cells["long_violation_seconds"].sum()
        ),
        "candidate_short_eess_violation_seconds": int(
            candidate_cells["short_violation_seconds"].sum()
        ),
        "maximum_frozen_comparator_reproduction_error": maximum_comparator_error,
        "architecture_audit": architecture_audit,
        "pass_audit_file": "PASS_AUDITS.json",
        "runtime_seconds": time.perf_counter() - started,
        "information_exchange_locality_certified": False,
        "claim_boundary": (
            "POST_CAMPAIGN_FAILED_SEED_DEVELOPMENT_STRESS_SET_NOT_FRESH_"
            "V4_4_CONFIRMATION_NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE"
        ),
    }
    write_json(result_root / "V44_SCHEDULING_SEED_RESULT.json", summary)

    result_files: dict[str, dict[str, Any]] = {}
    for path in sorted(result_root.iterdir()):
        if path.is_file():
            result_files[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    write_json(result_root / "RESULT_FILE_MANIFEST.json", result_files)

    if pass_temp.exists():
        shutil.rmtree(pass_temp)

    print(
        "V4_4_SCHEDULING_SEED_STATUS="
        + ("PASS" if hard_pass and bounded_scope else "REVIEW_REQUIRED")
    )
    print(f"CAMPAIGN_SEED={seed}")
    print(f"CANDIDATE_HARD_GATES_PASS={hard_pass}")
    print(f"BOUNDED_SCHEDULE_SCOPE_PASS={bounded_scope}")
    print(f"ORIGINAL_V4_3_UNRESOLVED_INTERVALS={original_unresolved}")
    print(f"SCHEDULING_SUCCESS_INTERVALS={scheduling_success}")
    print(f"SCHEDULING_FAILURE_INTERVALS={scheduling_failure}")
    print(f"DIAGNOSTIC_G8_SCHEDULING_FEASIBLE_INTERVALS={diagnostic_g8}")
    print(f"SCHEDULE_GUARD_LIMIT_COUNTS={json.dumps(guard_counts, sort_keys=True)}")
    print(f"MAXIMUM_SCHEDULE_GUARD_SECTOR_COUNT={maximum_guard_count}")
    print(f"MAXIMUM_SCHEDULE_CRITICAL_SECTOR_COUNT={maximum_critical}")
    print(f"MAXIMUM_SCHEDULE_MUTABLE_SECTOR_COUNT={maximum_mutable}")
    print(f"MAXIMUM_SCHEDULE_MODE_COUNT={maximum_mode_count}")
    print(f"MAXIMUM_PROTECTED_SUBBAND_SCHEDULED_FRACTION={maximum_scheduled_fraction}")
    print(f"MAXIMUM_SCHEDULE_SOLVER_SECONDS={maximum_schedule_solver_seconds}")
    print("CHANNEL_REGENERATION=NO")
    print("GPU_REQUESTED=NO")
    return 0 if hard_pass and bounded_scope else 42


if __name__ == "__main__":
    raise SystemExit(main())
