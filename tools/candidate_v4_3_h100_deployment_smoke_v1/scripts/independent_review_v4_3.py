#!/usr/bin/env python3
"""Independent audit of the frozen candidate-v4.3 excluded-seed return."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any

import numpy as np
import pandas as pd

EXPECTED_STATUS = (
    "PASS_EXCLUDED_SEED43999_CANDIDATE_V4_3_"
    "ALL5_FLOOR_EESS_AND_STRICT_POWER_GATES"
)
EXPECTED_RETURN_SHA256 = (
    "52fbd777e7816320f5bf05ed39ff6c3dd62573776336e404f1f2306875d98e90"
)
EXPECTED_SOURCE_COMMIT = "b65dc117f1ace492b55bd764f74bf985fbcb9507"
PRED = "robust_predictive_constrained_pf_with_sector_selective_fallback"
STATIC = "static_robust_constrained_pf_with_sector_selective_fallback"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition("=")
        if not sep:
            raise ValueError(f"invalid env line in {path}: {raw!r}")
        values[key] = value
    return values


def verify_manifest(base: Path, manifest: Path) -> None:
    result = subprocess.run(
        ["sha256sum", "-c", str(manifest)],
        cwd=base,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"manifest verification failed: {manifest}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def infer_eligible(trace: np.lib.npyio.NpzFile) -> tuple[np.ndarray, np.ndarray]:
    interval_seconds = float(np.asarray(trace["interval_lengths"])[0])
    alpha = math.exp(-interval_seconds / 100.0)
    first_average = np.asarray(trace["candidate_moving_average_rate"])[0]
    first_rate = np.asarray(trace["candidate_total_rate"])[0]
    initial_average = (first_average - (1.0 - alpha) * first_rate) / alpha
    eligible = initial_average >= 0.1
    return eligible, initial_average


def geometric_mean_positive(values: np.ndarray) -> float:
    samples = np.asarray(values, dtype=np.float64)
    positive = samples[samples > 0.0]
    if positive.size == 0:
        return 0.0
    return float(np.exp(np.mean(np.log(positive))))


def utility_rows(summary: Path) -> tuple[list[dict[str, Any]], np.ndarray]:
    with np.load(
        summary / "CANDIDATE_PASS_0_TRACE.npz", allow_pickle=False
    ) as first:
        eligible, initial = infer_eligible(first)
    if int(np.sum(eligible)) != 205:
        raise AssertionError(f"expected 205 eligible users, found {np.sum(eligible)}")

    reviewed = pd.read_csv(summary / "ALL_METHOD_CELL_SUMMARY.csv")
    rows: list[dict[str, Any]] = []
    for slot in range(5):
        with np.load(
            summary / f"CANDIDATE_PASS_{slot}_TRACE.npz", allow_pickle=False
        ) as trace:
            moving = np.asarray(trace["candidate_moving_average_rate"], np.float64)
            total = np.asarray(trace["candidate_total_rate"], np.float64)
            protected = np.asarray(trace["candidate_protected_rate"], np.float64)
            lengths = np.asarray(trace["interval_lengths"], np.float64)
            utility = np.log(moving[:, eligible] + 0.001).sum(axis=1)
            duration_mean = float(np.average(utility, weights=lengths))
            active = total[:, eligible] > 0.0
            total_samples = total[:, eligible][active]
            protected_samples = protected[:, eligible][active]
            pred = reviewed[
                (reviewed.pass_slot == slot) & (reviewed.method_id == PRED)
            ].iloc[0]
            static = reviewed[
                (reviewed.pass_slot == slot) & (reviewed.method_id == STATIC)
            ].iloc[0]
            row = {
                "pass_slot": slot,
                "candidate_final_moving_pf_utility": float(utility[-1]),
                "candidate_duration_weighted_mean_moving_pf_utility": duration_mean,
                "candidate_total_active_eligible_p05_bps_hz": float(
                    np.percentile(total_samples, 5.0)
                ),
                "candidate_total_active_eligible_geometric_mean_bps_hz": (
                    geometric_mean_positive(total_samples)
                ),
                "candidate_protected_active_eligible_p05_bps_hz": float(
                    np.percentile(protected_samples, 5.0)
                ),
                "candidate_protected_active_eligible_positive_geometric_mean_bps_hz": (
                    geometric_mean_positive(protected_samples)
                ),
                "candidate_protected_active_eligible_zero_fraction": float(
                    np.mean(protected_samples <= 0.0)
                ),
                "candidate_minus_reviewed_predictive_final_pf": float(
                    utility[-1] - pred.final_moving_pf_utility
                ),
                "candidate_minus_reviewed_predictive_duration_mean_pf": float(
                    duration_mean - pred.duration_weighted_mean_moving_pf_utility
                ),
                "candidate_minus_safe_static_final_pf": float(
                    utility[-1] - static.final_moving_pf_utility
                ),
                "candidate_minus_safe_static_duration_mean_pf": float(
                    duration_mean - static.duration_weighted_mean_moving_pf_utility
                ),
            }
            rows.append(row)
    return rows, initial


def load_all_traces(summary: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    minima: list[float] = []
    long_maxima: list[float] = []
    short_maxima: list[float] = []
    total_intervals = 0
    total_seconds = 0
    for slot in range(5):
        with np.load(
            summary / f"CANDIDATE_PASS_{slot}_TRACE.npz", allow_pickle=False
        ) as trace:
            floor_count = np.asarray(trace["candidate_floor_count"])
            shortfall = np.asarray(trace["candidate_normalized_shortfall"])
            long_ratio = np.asarray(trace["candidate_long_ratio"])
            short_ratio = np.asarray(trace["candidate_short_ratio"])
            action = np.asarray(trace["action_class"])
            lengths = np.asarray(trace["interval_lengths"])
            if np.any(floor_count != 0):
                raise AssertionError(f"pass {slot}: nonzero candidate floor count")
            if np.any(shortfall != 0.0):
                raise AssertionError(f"pass {slot}: nonzero normalized shortfall")
            if float(np.max(long_ratio)) > 1.0 + 1e-10:
                raise AssertionError(f"pass {slot}: long EESS ratio exceeds gate")
            if float(np.max(short_ratio)) > 1.0 + 1e-10:
                raise AssertionError(f"pass {slot}: short EESS ratio exceeds gate")
            minima.append(float(np.min(np.asarray(trace["candidate_total_rate"]))))
            long_maxima.append(float(np.max(long_ratio)))
            short_maxima.append(float(np.max(short_ratio)))
            total_intervals += int(len(action))
            total_seconds += int(np.sum(lengths))
            for name, count in zip(*np.unique(action, return_counts=True)):
                counts[str(name)] = counts.get(str(name), 0) + int(count)
    return {
        "action_class_counts": counts,
        "total_intervals": total_intervals,
        "total_physical_seconds": total_seconds,
        "maximum_long_ratio": max(long_maxima),
        "maximum_short_ratio": max(short_maxima),
        "minimum_raw_total_rate_including_inactive": min(minima),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-env", required=True)
    args = parser.parse_args()

    evidence = Path(args.evidence_root).expanduser().resolve()
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8"))
    output_json = Path(args.output_json).expanduser().resolve()
    output_env = Path(args.output_env).expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_env.parent.mkdir(parents=True, exist_ok=True)

    summary = evidence / "summary"
    verify_manifest(summary, summary / "OUTPUT_MANIFEST.sha256")
    source = evidence / "candidate_source"
    verify_manifest(source, source / "SOURCE_PAYLOAD_MANIFEST.sha256")

    metadata = json.loads((evidence / "RETURN_METADATA.json").read_text())
    status = parse_env(summary / "RUN_STATUS.env")
    verdict = json.loads((summary / "SCIENTIFIC_VERDICT.json").read_text())
    actions = pd.read_csv(summary / "CANDIDATE_ACTION_INTERVALS.csv")
    residual_path = summary / "CANDIDATE_RESIDUAL_FLOOR_VIOLATIONS.csv"
    try:
        residual = pd.read_csv(residual_path)
    except pd.errors.EmptyDataError:
        residual = pd.DataFrame()
    cells = pd.read_csv(summary / "CANDIDATE_CELL_SUMMARY.csv")
    affected = pd.read_csv(summary / "AFFECTED_USER_INTERVAL_FEASIBILITY.csv")

    required_equal = {
        "CANDIDATE_STATUS": EXPECTED_STATUS,
        "CANDIDATE_LONG_VIOLATION_SECONDS": "0",
        "CANDIDATE_SHORT_VIOLATION_SECONDS": "0",
        "CANDIDATE_FLOOR_VIOLATION_USER_SECONDS": "0",
        "CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS": "0",
        "NETWORK_WIDE_SHUTDOWN_INTERVALS": "0",
        "STRICT_LOCAL_SCOPE_GATE": "PASS",
        "STRICT_POST_MODE_SELECTED_POWER_GATE": "PASS",
        "Q0_ENVELOPE_DEPLOYABLE_ACTIONS": "0",
        "Q0_HEADROOM_USED_INTERVALS": "0",
        "STRICT_POST_MODE_STREAM_INFEASIBLE_INTERVALS": "0",
        "STRICT_POST_MODE_STREAM_UNCERTIFIED_INTERVALS": "0",
        "CONFIRMATORY_CAMPAIGN_AUTHORIZED": "NO",
    }
    for key, expected in required_equal.items():
        actual = status.get(key)
        if actual != expected:
            raise AssertionError(f"{key}: expected {expected!r}, got {actual!r}")

    if metadata["status"] != "PASS_RETURN_READY":
        raise AssertionError("return metadata is not PASS_RETURN_READY")
    if metadata["source_commit"] != EXPECTED_SOURCE_COMMIT:
        raise AssertionError("candidate source commit mismatch")
    if int(metadata["scientific_exit_code"]) != 0:
        raise AssertionError("scientific exit code is nonzero")
    if metadata["h100_channel_regenerated"]:
        raise AssertionError("CPU diagnostic unexpectedly regenerated the channel")
    if residual.shape[0] != 0:
        raise AssertionError("residual-floor CSV is not empty")
    if cells.shape[0] != 5 or np.any(cells.eligible_floor_violation_user_seconds != 0):
        raise AssertionError("candidate cell summary does not pass all five cells")
    if affected.shape[0] != 104:
        raise AssertionError(f"expected 104 affected intervals, found {affected.shape[0]}")
    if set(affected.user_id) != {"E3_SITE_02_SEC_3_UE_4", "E3_SITE_07_SEC_1_UE_2"}:
        raise AssertionError("affected-user identity mismatch")
    if float(affected.candidate_floor_ratio.min()) <= 1.0:
        raise AssertionError("candidate has no strict positive floor margin")

    allowed_actions = {
        "BASELINE_NOOP",
        "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR",
        "SPARSE_LOCAL_STREAM_POWER_REPAIR",
    }
    if not set(actions.chosen_action_class).issubset(allowed_actions):
        raise AssertionError("unrecognized action class")
    if np.any(actions.candidate_floor_violation_count != 0):
        raise AssertionError("action table contains candidate floor violation")
    if np.any(actions.candidate_long_violation_seconds != 0):
        raise AssertionError("action table contains long EESS violation")
    if np.any(actions.candidate_short_violation_seconds != 0):
        raise AssertionError("action table contains short EESS violation")
    if not np.all(actions.strict_local_scope_gate == "PASS"):
        raise AssertionError("strict action-scope gate failed")
    if np.any(actions.q0_power_headroom_used.astype(bool)):
        raise AssertionError("deployable action uses q0 headroom")

    repair_actions = actions[actions.chosen_action_class != "BASELINE_NOOP"].copy()
    if repair_actions.shape[0] != 104:
        raise AssertionError("repair action count does not equal original affected count")
    if int(repair_actions.interval_seconds.sum()) != 519:
        raise AssertionError("repair physical-second count does not equal 519")
    if int(repair_actions.changed_sector_count.max()) > 4:
        raise AssertionError("unexpected changed-sector count")
    if int(repair_actions.mutable_sector_count.max()) > 5:
        raise AssertionError("mutable-sector scope exceeds contract")

    trace_audit = load_all_traces(summary)
    if trace_audit["action_class_counts"] != {
        "BASELINE_NOOP": 486,
        "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR": 6,
        "SPARSE_LOCAL_STREAM_POWER_REPAIR": 98,
    }:
        raise AssertionError(f"action counts mismatch: {trace_audit['action_class_counts']}")

    utility, initial = utility_rows(summary)
    utility_frame = pd.DataFrame(utility)
    mean_final_delta = float(
        utility_frame.candidate_minus_reviewed_predictive_final_pf.mean()
    )
    mean_duration_delta = float(
        utility_frame.candidate_minus_reviewed_predictive_duration_mean_pf.mean()
    )
    if not np.all(
        utility_frame.candidate_minus_safe_static_duration_mean_pf.to_numpy() > 0.0
    ):
        raise AssertionError("candidate does not beat safe static duration-mean PF in every pass")

    source_text = (
        source / "src/fr3_cbf/floor_feasibility_repair.py"
    ).read_text(encoding="utf-8")
    required_source_fragments = [
        "SOLVER_CONSTRAINT_RESERVE = 1e-8",
        "SOLVER_PRIMAL_FEASIBILITY_TOLERANCE = 1e-9",
        "SOLVER_DUAL_FEASIBILITY_TOLERANCE = 1e-9",
        "strict_post_mode_power_budget",
    ]
    for fragment in required_source_fragments:
        if fragment not in source_text:
            raise AssertionError(f"required source fragment absent: {fragment}")

    review = {
        "schema_version": 1,
        "review_status": "PASS_TO_SINGLE_EXCLUDED_H100_DEPLOYMENT_SMOKE",
        "candidate_version": "v4.3",
        "excluded_seed": 43999,
        "source_supported_facts": {
            "slurm_job_id": metadata["slurm_job_id"],
            "slurm_state": metadata["slurm_state"],
            "slurm_maxrss": metadata["slurm_maxrss"],
            "candidate_status": status["CANDIDATE_STATUS"],
            "long_eess_violation_seconds": 0,
            "short_eess_violation_seconds": 0,
            "floor_violation_user_seconds": 0,
            "floor_violation_user_intervals": 0,
            "network_wide_shutdown_intervals": 0,
            "strict_post_mode_selected_power_gate": True,
            "q0_envelope_deployable_actions": 0,
            "action_class_counts": trace_audit["action_class_counts"],
            "repair_intervals": int(repair_actions.shape[0]),
            "repair_physical_seconds": int(repair_actions.interval_seconds.sum()),
            "maximum_mutable_sector_count": int(repair_actions.mutable_sector_count.max()),
            "maximum_changed_sector_count": int(repair_actions.changed_sector_count.max()),
            "minimum_candidate_floor_ratio": float(affected.candidate_floor_ratio.min()),
            "maximum_long_eess_ratio": trace_audit["maximum_long_ratio"],
            "maximum_short_eess_ratio": trace_audit["maximum_short_ratio"],
            "eligible_user_count_reconstructed": int(np.sum(initial >= 0.1)),
        },
        "independent_trace_reconstruction": {
            "utility_by_pass": utility,
            "mean_candidate_minus_reviewed_predictive_final_pf": mean_final_delta,
            "mean_candidate_minus_reviewed_predictive_duration_mean_pf": mean_duration_delta,
            "candidate_beats_safe_static_duration_mean_pf_in_all_passes": True,
        },
        "scientific_inference": {
            "floor_feasibility": (
                "The unchanged floor is feasible on every originally violating "
                "seed-43999 interval under the frozen modes, fixed RZF directions, "
                "strict post-mode sector-power budget, and bounded sparse action scope."
            ),
            "repair_preference": (
                "Retain candidate v4.3; do not revise the fairness policy. The next "
                "scientific gate is production-style replay in the H100 environment."
            ),
            "twc_potential": (
                "High if the H100 integration smoke, multi-seed confirmatory campaign, "
                "distributed-information/latency audit, and hardware-practicality "
                "sensitivity all pass."
            ),
        },
        "assumptions_and_remaining_risks": {
            "excluded_seed_not_confirmatory": True,
            "minimum_floor_margin_is_numerically_small": True,
            "action_scope_locality_verified": True,
            "information_exchange_locality_not_yet_certified": True,
            "fixed_rzf_reweighting_latency_and_signalling_not_measured": True,
            "hardware_calibration_claimed": False,
            "regulatory_compliance_claimed": False,
        },
        "binding": binding,
        "confirmatory_campaign_authorized": False,
        "next_gate": "SINGLE_EXCLUDED_H100_DEPLOYMENT_SMOKE_WITH_PRESERVED_CHANNEL",
    }
    output_json.write_text(
        json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    env = {
        "INDEPENDENT_V4_3_REVIEW": "PASS",
        "V4_3_CPU_RETURN_STATUS": status["CANDIDATE_STATUS"],
        "V4_3_CPU_RETURN_SHA256": EXPECTED_RETURN_SHA256,
        "V4_3_SOURCE_COMMIT": EXPECTED_SOURCE_COMMIT,
        "V4_3_FLOOR_VIOLATION_USER_SECONDS": 0,
        "V4_3_FLOOR_VIOLATION_USER_INTERVALS": 0,
        "V4_3_LONG_EESS_VIOLATION_SECONDS": 0,
        "V4_3_SHORT_EESS_VIOLATION_SECONDS": 0,
        "V4_3_REPAIR_INTERVALS": 104,
        "V4_3_REPAIR_PHYSICAL_SECONDS": 519,
        "V4_3_LOCAL_GRID_REPAIR_INTERVALS": 6,
        "V4_3_STREAM_POWER_REPAIR_INTERVALS": 98,
        "V4_3_MINIMUM_CANDIDATE_FLOOR_RATIO": (
            f"{float(affected.candidate_floor_ratio.min()):.17g}"
        ),
        "V4_3_MEAN_FINAL_PF_DELTA_VS_PREDICTIVE": f"{mean_final_delta:.17g}",
        "V4_3_MEAN_DURATION_PF_DELTA_VS_PREDICTIVE": f"{mean_duration_delta:.17g}",
        "ACTION_SCOPE_LOCALITY_GATE": "PASS",
        "INFORMATION_EXCHANGE_LOCALITY_CERTIFIED": "NO",
        "CONFIRMATORY_CAMPAIGN_AUTHORIZED": "NO",
        "NEXT_GATE": "SINGLE_EXCLUDED_H100_DEPLOYMENT_SMOKE_WITH_PRESERVED_CHANNEL",
    }
    output_env.write_text(
        "".join(f"{key}={value}\n" for key, value in env.items()),
        encoding="utf-8",
    )
    for key, value in env.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
