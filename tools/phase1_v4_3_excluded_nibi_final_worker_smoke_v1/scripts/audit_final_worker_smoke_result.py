#!/usr/bin/env python3
"""Independent audit of the exact final campaign-worker smoke for seed 43999."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

CANDIDATE = "candidate_v4_3_floor_feasibility_repair"
COMPARATORS = [
    "robust_predictive_constrained_pf_with_sector_selective_fallback",
    "static_robust_constrained_pf_with_sector_selective_fallback",
    "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
    "delayed_myopic_constrained_pf_unshielded",
    "virtual_queue_unshielded",
    "uniform_protected_tone_backoff",
    "hard_spatial_null_or_exact_mute",
    "common_scale_instantaneous_noncausal_reference",
]
METHOD_IDS = [CANDIDATE, *COMPARATORS]
SMOKE_STAGE = "EXCLUDED_FINAL_WORKER_SMOKE_SEED43999"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def max_abs(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        raise ValueError(f"array shape mismatch: {a.shape} != {b.shape}")
    if a.dtype.kind in "USO" or b.dtype.kind in "USO":
        return 0.0 if np.array_equal(a, b) else math.inf
    return float(np.max(np.abs(np.asarray(a, float) - np.asarray(b, float))))


def json_safe(value):
    """Convert NumPy/Pandas scalar values into strict JSON-native values."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def compare_frames(
    actual: pd.DataFrame,
    reference: pd.DataFrame,
    key_columns: list[str],
    exact_columns: list[str],
    numeric_columns: list[str],
    tolerance: float,
) -> tuple[dict[str, float], list[str]]:
    actual = actual.sort_values(key_columns).reset_index(drop=True)
    reference = reference.sort_values(key_columns).reset_index(drop=True)
    if actual[key_columns].to_dict("records") != reference[key_columns].to_dict("records"):
        raise ValueError("frame key rows differ")
    failed: list[str] = []
    errors: dict[str, float] = {}
    for column in exact_columns:
        if column not in actual or column not in reference:
            raise KeyError(column)
        if actual[column].tolist() != reference[column].tolist():
            failed.append(column)
    for column in numeric_columns:
        if column not in actual or column not in reference:
            raise KeyError(column)
        error = float(
            np.max(
                np.abs(
                    actual[column].to_numpy(float)
                    - reference[column].to_numpy(float)
                )
            )
        )
        errors[column] = error
        if error > tolerance:
            failed.append(column)
    return errors, failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-root", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--reference-root", required=True)
    parser.add_argument("--authorization-record", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tolerance", type=float, default=1e-10)
    args = parser.parse_args()

    seed_root = Path(args.seed_root).expanduser().resolve()
    result = seed_root / "result"
    channel = seed_root / "channel"
    job_root = Path(args.job_root).expanduser().resolve()
    reference = Path(args.reference_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    tolerance = float(args.tolerance)

    required_result = [
        "SEED_RESULT.json",
        "RESULT_FILE_MANIFEST.json",
        "CELL_SUMMARY.csv",
        "PRIMARY_PAIRED_EFFECTS.csv",
        *[f"PASS_{slot}_METHOD_TRACES.npz" for slot in range(5)],
        *[f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz" for slot in range(5)],
    ]
    for name in required_result:
        if not (result / name).is_file():
            raise FileNotFoundError(result / name)
    for name in ("CHANNEL_RECORD.json", "frequency_response.npy"):
        if not (channel / name).is_file():
            raise FileNotFoundError(channel / name)

    contract = json.loads(
        (job_root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8")
    )
    seed_audit = json.loads(
        (result / "SEED_RESULT.json").read_text(encoding="utf-8")
    )
    channel_record = json.loads(
        (channel / "CHANNEL_RECORD.json").read_text(encoding="utf-8")
    )
    reference_channel = json.loads(
        (reference / "REFERENCE_CHANNEL_RECORD.json").read_text(encoding="utf-8")
    )
    auth = json.loads(
        Path(args.authorization_record).read_text(encoding="utf-8")
    )
    environment = json.loads(Path(args.environment).read_text(encoding="utf-8"))

    result_manifest = json.loads(
        (result / "RESULT_FILE_MANIFEST.json").read_text(encoding="utf-8")
    )
    manifest_gate = True
    for name, record in result_manifest.items():
        path = result / name
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            manifest_gate = False
            break

    basic_checks = {
        "campaign_seed": int(seed_audit["campaign_seed"]) == 43999,
        "array_index_is_excluded": int(seed_audit["array_index"]) == -1,
        "execution_stage": seed_audit["execution_stage"] == SMOKE_STAGE,
        "package_id": seed_audit["package_id"] == contract["package_id"],
        "candidate_source_manifest": seed_audit[
            "candidate_source_manifest_sha256"
        ]
        == contract["candidate_v4_3"]["source_manifest_sha256"],
        "method_ids": seed_audit["method_ids"] == METHOD_IDS,
        "cell_count": int(seed_audit["cell_count"]) == 45,
        "pass_count": len(seed_audit["pass_audits"]) == 5,
        "authorization_stage": auth["execution_stage"] == SMOKE_STAGE,
        "authorization_seed": auth["allowed_seeds"] == [43999],
        "authorization_native_guard": auth["native_authorization_guard"] == "PASS",
        "authorization_not_returned": auth["token_in_return_bundle"] is False,
        "full_campaign_not_authorized": auth[
            "full_campaign_execution_authorized"
        ]
        is False,
        "environment_h100": environment["status"]
        == "PASS_NIBI_H100_FINAL_WORKER_ENVIRONMENT",
        "environment_exact_reference": environment.get(
            "exact_reference_environment_gate"
        ) == "PASS",
        "environment_versions": environment.get("actual_versions")
        == {
            "torch": "2.9.1",
            "sionna-no-rt": "2.0.1",
            "numpy": "2.4.2",
            "scipy": "1.17.0",
            "pandas": "2.3.3",
        },
        "result_manifest": manifest_gate,
    }

    channel_checks = {
        "campaign_seed": int(channel_record["campaign_seed"]) == 43999,
        "user_seed": int(channel_record["user_seed"]) == 87998,
        "channel_seed": int(channel_record["channel_seed"]) == 87999,
        "response_shape": channel_record["channel_generation"]["response_shape"]
        == [228, 57, 128, 9],
        "array_bytes_sha256": channel_record[
            "frequency_response_sha256_array_bytes"
        ]
        == reference_channel["frequency_response_sha256_array_bytes"],
        "npy_file_sha256": sha256_file(channel / "frequency_response.npy")
        == reference_channel["files"]["frequency_response.npy"]["sha256"],
        "user_topology_sha256": channel_record["files"]["USER_TOPOLOGY.csv"][
            "sha256"
        ]
        == reference_channel["files"]["USER_TOPOLOGY.csv"]["sha256"],
        "sector_topology_sha256": channel_record["files"]["SECTOR_TOPOLOGY.csv"][
            "sha256"
        ]
        == reference_channel["files"]["SECTOR_TOPOLOGY.csv"]["sha256"],
        "coefficient_sha256": channel_record["channel_generation"][
            "coefficients_sha256"
        ]
        == reference_channel["channel_generation"]["coefficients_sha256"],
        "delay_sha256": channel_record["channel_generation"]["delays_sha256"]
        == reference_channel["channel_generation"]["delays_sha256"],
    }

    cells = pd.read_csv(result / "CELL_SUMMARY.csv")
    paired = pd.read_csv(result / "PRIMARY_PAIRED_EFFECTS.csv")
    if len(cells) != 45 or sorted(cells["pass_slot"].unique().tolist()) != list(
        range(5)
    ):
        raise ValueError("campaign worker cell design mismatch")
    for _slot, frame in cells.groupby("pass_slot", sort=True):
        if frame["method_id"].tolist() != METHOD_IDS:
            raise ValueError("campaign worker method order mismatch")

    candidate = cells.loc[cells["method_id"] == CANDIDATE].sort_values("pass_slot")
    candidate_hard_checks = {
        "worker_scientific_pass": bool(seed_audit["candidate_hard_gates_pass"]),
        "worker_exit_class": int(seed_audit["scientific_exit_code"]) == 0,
        "long_eess_zero": int(candidate["long_violation_seconds"].sum()) == 0,
        "short_eess_zero": int(candidate["short_violation_seconds"].sum()) == 0,
        "floor_seconds_zero": int(
            candidate["eligible_floor_violation_user_seconds"].sum()
        )
        == 0,
        "floor_intervals_zero": int(
            candidate["eligible_floor_violation_user_intervals"].sum()
        )
        == 0,
        "strict_local_scope": (
            candidate["candidate_strict_local_scope_gate"] == "PASS"
        ).all(),
        "strict_post_mode_power": (
            candidate["candidate_strict_post_mode_power_gate"] == "PASS"
        ).all(),
        "q0_actions_zero": int(
            candidate["candidate_q0_envelope_deployable_actions"].sum()
        )
        == 0,
        "unresolved_zero": int(
            candidate["candidate_unresolved_deployable_intervals"].sum()
        )
        == 0,
        "shutdown_zero": int(
            candidate["candidate_network_wide_shutdown_intervals"].sum()
        )
        == 0,
        "strict_power_ratio": float(
            candidate["candidate_maximum_strict_post_mode_power_ratio"].max()
        )
        <= 1.0 + 1e-10,
        "information_exchange_not_overclaimed": (
            candidate["candidate_information_exchange_locality_certified"] == False
        ).all(),
    }

    reference_comparators = pd.read_csv(
        reference / "REFERENCE_ALL_METHOD_CELL_SUMMARY.csv"
    )
    actual_comparators = cells.loc[cells["method_id"].isin(COMPARATORS)].copy()
    exact_columns = [
        "long_violation_seconds",
        "short_violation_seconds",
        "eligible_floor_violation_user_intervals",
        "eligible_floor_violation_user_seconds",
        "sector_mute_interval_count",
        "intervals_with_any_sector_mute",
        "maximum_muted_sector_count",
        "protected_sample_count",
        "interval_count",
    ]
    numeric_columns = [
        "long_maximum_excess_db",
        "short_maximum_excess_db",
        "total_normalized_floor_shortfall",
        "final_moving_pf_utility",
        "duration_weighted_mean_moving_pf_utility",
        "protected_active_eligible_p05_bps_hz",
        "protected_active_eligible_geometric_mean_bps_hz",
        "total_active_eligible_p05_bps_hz",
        "total_active_eligible_geometric_mean_bps_hz",
    ]
    comparator_errors, comparator_failed = compare_frames(
        actual_comparators,
        reference_comparators,
        ["pass_slot", "method_id"],
        exact_columns,
        numeric_columns,
        tolerance,
    )

    ref_utility = pd.read_csv(
        reference / "REFERENCE_CANDIDATE_UTILITY_SUMMARY.csv"
    ).sort_values("pass_slot")
    candidate_metric_map = {
        "candidate_final_moving_pf_utility": "final_moving_pf_utility",
        "candidate_duration_weighted_mean_moving_pf_utility": (
            "duration_weighted_mean_moving_pf_utility"
        ),
        "candidate_total_active_eligible_p05_bps_hz": (
            "total_active_eligible_p05_bps_hz"
        ),
        "candidate_total_active_eligible_geometric_mean_bps_hz": (
            "total_active_eligible_geometric_mean_bps_hz"
        ),
        "candidate_protected_active_eligible_p05_bps_hz": (
            "protected_active_eligible_p05_bps_hz"
        ),
    }
    candidate_metric_errors: dict[str, float] = {}
    candidate_metric_failed: list[str] = []
    for reference_column, actual_column in candidate_metric_map.items():
        error = float(
            np.max(
                np.abs(
                    ref_utility[reference_column].to_numpy(float)
                    - candidate[actual_column].to_numpy(float)
                )
            )
        )
        candidate_metric_errors[actual_column] = error
        if error > tolerance:
            candidate_metric_failed.append(actual_column)

    paired = paired.sort_values("pass_slot")
    paired_map = {
        "candidate_minus_predictive_final_pf": "candidate_minus_predictive_final_pf",
        "candidate_minus_predictive_duration_mean_pf": (
            "candidate_minus_predictive_duration_mean_pf"
        ),
        "candidate_minus_static_final_pf": "candidate_minus_static_final_pf",
        "candidate_minus_static_duration_mean_pf": (
            "candidate_minus_static_duration_mean_pf"
        ),
    }
    paired_errors: dict[str, float] = {}
    paired_failed: list[str] = []
    for reference_column, actual_column in paired_map.items():
        error = float(
            np.max(
                np.abs(
                    ref_utility[reference_column].to_numpy(float)
                    - paired[actual_column].to_numpy(float)
                )
            )
        )
        paired_errors[actual_column] = error
        if error > tolerance:
            paired_failed.append(actual_column)

    reference_candidate = pd.read_csv(
        reference / "REFERENCE_CANDIDATE_CELL_SUMMARY.csv"
    ).sort_values("pass_slot")
    action_count_checks = {
        "local_grid_counts": candidate[
            "candidate_local_grid_repair_intervals"
        ].astype(int).tolist()
        == reference_candidate["local_frozen_grid_repair_intervals"].astype(int).tolist(),
        "local_stream_counts": candidate[
            "candidate_local_stream_repair_intervals"
        ].astype(int).tolist()
        == reference_candidate["local_stream_repair_intervals"].astype(int).tolist(),
        "unresolved_counts": candidate[
            "candidate_unresolved_deployable_intervals"
        ].astype(int).tolist()
        == reference_candidate["unresolved_intervals"].astype(int).tolist(),
    }

    trace_errors: dict[str, float] = {}
    trace_failures: list[str] = []
    action_class_exact = True
    for slot in range(5):
        ref_trace = load_npz(reference / f"REFERENCE_CANDIDATE_PASS_{slot}_TRACE.npz")
        actual_action = load_npz(result / f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz")
        actual_method = load_npz(result / f"PASS_{slot}_METHOD_TRACES.npz")
        pairs = {
            "candidate_stream_scale": (
                actual_action["candidate_stream_scale"],
                ref_trace["candidate_stream_scale"],
            ),
            "candidate_pre_repair_sector_scale": (
                actual_action["candidate_pre_repair_sector_scale"],
                ref_trace["integrated_pre_repair_sector_scale"],
            ),
            "candidate_maximum_shortfall_trace": (
                actual_action["candidate_maximum_shortfall_trace"],
                ref_trace["candidate_normalized_shortfall"],
            ),
            "interval_lengths": (
                actual_action["interval_lengths"], ref_trace["interval_lengths"]
            ),
            "candidate_long_ratio": (
                actual_method["m0_long_ratio"], ref_trace["candidate_long_ratio"]
            ),
            "candidate_short_ratio": (
                actual_method["m0_short_ratio"], ref_trace["candidate_short_ratio"]
            ),
            "candidate_floor_count": (
                actual_method["m0_floor_count"], ref_trace["candidate_floor_count"]
            ),
            "candidate_shortfall": (
                actual_method["m0_shortfall"],
                ref_trace["candidate_normalized_shortfall"],
            ),
        }
        for name, (actual_array, ref_array) in pairs.items():
            error = max_abs(actual_array, ref_array)
            trace_errors[f"pass_{slot}_{name}"] = error
            if error > tolerance:
                trace_failures.append(f"pass_{slot}_{name}")
        if not np.array_equal(
            actual_action["candidate_action_class"], ref_trace["action_class"]
        ):
            action_class_exact = False
            trace_failures.append(f"pass_{slot}_candidate_action_class")

    basic_pass = all(basic_checks.values())
    channel_pass = all(channel_checks.values())
    hard_pass = all(candidate_hard_checks.values())
    comparator_pass = not comparator_failed
    candidate_reference_pass = (
        not candidate_metric_failed
        and not paired_failed
        and not trace_failures
        and action_class_exact
        and all(action_count_checks.values())
    )
    overall = (
        basic_pass
        and channel_pass
        and hard_pass
        and comparator_pass
        and candidate_reference_pass
    )
    value = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_EXCLUDED_NIBI_FINAL_CAMPAIGN_WORKER_SMOKE_SEED43999"
            if overall
            else "FAIL_EXCLUDED_NIBI_FINAL_CAMPAIGN_WORKER_SMOKE_REVIEW_REQUIRED"
        ),
        "claim_boundary": (
            "EXCLUDED_FINAL_CAMPAIGN_WORKER_SMOKE_NOT_CONFIRMATORY_"
            "NOT_PAPER_RESULT_NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE"
        ),
        "campaign_seed": 43999,
        "package_id": contract["package_id"],
        "basic_checks": basic_checks,
        "channel_checks": channel_checks,
        "candidate_hard_checks": candidate_hard_checks,
        "action_count_checks": action_count_checks,
        "comparator_reference_summary_gate": "PASS" if comparator_pass else "FAIL",
        "comparator_maximum_absolute_error_by_metric": comparator_errors,
        "comparator_failed_metrics": comparator_failed,
        "candidate_reference_trace_gate": (
            "PASS" if candidate_reference_pass else "FAIL"
        ),
        "candidate_metric_maximum_absolute_error": candidate_metric_errors,
        "candidate_metric_failed": candidate_metric_failed,
        "paired_effect_maximum_absolute_error": paired_errors,
        "paired_effect_failed": paired_failed,
        "candidate_action_class_trace_exact": action_class_exact,
        "candidate_trace_maximum_absolute_error": max(trace_errors.values(), default=0.0),
        "candidate_trace_errors": trace_errors,
        "candidate_trace_failures": trace_failures,
        "channel_exact_reference_gate": "PASS" if channel_pass else "FAIL",
        "candidate_hard_gates": "PASS" if hard_pass else "FAIL",
        "candidate_floor_violation_user_seconds": int(
            candidate["eligible_floor_violation_user_seconds"].sum()
        ),
        "candidate_floor_violation_user_intervals": int(
            candidate["eligible_floor_violation_user_intervals"].sum()
        ),
        "candidate_long_eess_violation_seconds": int(
            candidate["long_violation_seconds"].sum()
        ),
        "candidate_short_eess_violation_seconds": int(
            candidate["short_violation_seconds"].sum()
        ),
        "candidate_local_grid_repair_intervals": int(
            candidate["candidate_local_grid_repair_intervals"].sum()
        ),
        "candidate_local_stream_repair_intervals": int(
            candidate["candidate_local_stream_repair_intervals"].sum()
        ),
        "candidate_unresolved_intervals": int(
            candidate["candidate_unresolved_deployable_intervals"].sum()
        ),
        "candidate_network_wide_shutdown_intervals": int(
            candidate["candidate_network_wide_shutdown_intervals"].sum()
        ),
        "candidate_maximum_strict_post_mode_power_ratio": float(
            candidate["candidate_maximum_strict_post_mode_power_ratio"].max()
        ),
        "generated_channel_record_sha256": sha256_file(
            channel / "CHANNEL_RECORD.json"
        ),
        "generated_frequency_response_file_sha256": sha256_file(
            channel / "frequency_response.npy"
        ),
        "generated_frequency_response_array_sha256": channel_record[
            "frequency_response_sha256_array_bytes"
        ],
        "information_exchange_locality_certified": False,
        "full_campaign_execution_authorized": False,
        "next_gate": (
            "INDEPENDENTLY_REVIEW_NIBI_FINAL_WORKER_SMOKE_THEN_ISSUE_"
            "SEPARATE_FULL_CAMPAIGN_AUTHORIZATION"
            if overall
            else "DIAGNOSE_FINAL_CAMPAIGN_WORKER_OR_NIBI_CHANNEL_REPRODUCTION_"
            "BEFORE_ANY_CAMPAIGN_AUTHORIZATION"
        ),
    }
    value = json_safe(value)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"FINAL_WORKER_SMOKE_STATUS={value['status']}")
    print(f"CHANNEL_EXACT_REFERENCE_GATE={value['channel_exact_reference_gate']}")
    print(
        "COMPARATOR_REFERENCE_SUMMARY_GATE="
        + value["comparator_reference_summary_gate"]
    )
    print(f"CANDIDATE_REFERENCE_TRACE_GATE={value['candidate_reference_trace_gate']}")
    print(f"CANDIDATE_HARD_GATES={value['candidate_hard_gates']}")
    print(
        "CANDIDATE_FLOOR_VIOLATION_USER_SECONDS="
        f"{value['candidate_floor_violation_user_seconds']}"
    )
    print(
        "CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS="
        f"{value['candidate_floor_violation_user_intervals']}"
    )
    print(
        "CANDIDATE_LONG_EESS_VIOLATION_SECONDS="
        f"{value['candidate_long_eess_violation_seconds']}"
    )
    print(
        "CANDIDATE_SHORT_EESS_VIOLATION_SECONDS="
        f"{value['candidate_short_eess_violation_seconds']}"
    )
    print(f"NEXT_GATE={value['next_gate']}")
    print("FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO")
    return 0 if overall else 42


if __name__ == "__main__":
    raise SystemExit(main())
