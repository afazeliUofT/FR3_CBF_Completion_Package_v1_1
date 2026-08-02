#!/usr/bin/env python3
"""Exact post-campaign feasibility diagnosis for one preserved failed seed."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linprog

FAILED_SEEDS = {44001, 44007, 44008, 44013, 44017, 44018, 44024, 44025, 44026, 44027, 44028}
EXPECTED_PACKAGE_ID = "8473d5504e69347a69a536c43dcae35bec9519a90bc55de3a0712f9e0fb97889"
EXPECTED_SOURCE_MANIFEST = "a2e67130c91577b83be6e14f400d0934aa6d94ac0f974956594df35eec0cb93c"
RESERVE = 1e-8


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def user_id(index: int) -> str:
    sector = int(index) // 4
    stream = int(index) % 4
    return f"E3_SITE_{sector // 3 + 1:02d}_SEC_{sector % 3 + 1}_UE_{stream + 1}"


def outcome_record(outcome: Any) -> dict[str, Any]:
    return {
        "status": str(outcome.status),
        "feasible": bool(outcome.feasible),
        "optimal": bool(outcome.optimal),
        "objective": None if outcome.objective is None else float(outcome.objective),
        "maximum_constraint_excess": (
            None if outcome.maximum_constraint_excess is None else float(outcome.maximum_constraint_excess)
        ),
        "changed_variable_count": (
            None if outcome.changed_variable_count is None else int(outcome.changed_variable_count)
        ),
        "message": str(outcome.message),
    }


def exact_stream_audit(
    repair: Any,
    stream_scale: np.ndarray,
    kwargs: dict[str, Any],
    system: dict[str, Any],
) -> dict[str, Any]:
    """Verify floor, EESS, and strict post-mode sector-power constraints exactly."""
    gain = system["gain"]
    matrix = np.asarray(stream_scale, dtype=np.float64).reshape(
        gain.shape[1], gain.shape[2]
    )
    audit = repair.exact_audit(
        gain_user_sector_stream=gain,
        stream_scale=matrix,
        other_weighted_rate=kwargs["state"].other_weighted_rate,
        active_user=kwargs["state"].active_user,
        eligible_user=kwargs["eligible_user"],
        floors=kwargs["floors"],
        serving_bs=kwargs["serving_bs"],
        serving_stream=kwargs["serving_stream"],
        protected_noise_w=kwargs["protected_noise_w"],
        protected_weight=kwargs["protected_weight"],
        long_kappa_second_sector=kwargs["long_kappa_second_sector"],
        short_kappa_second_sector=kwargs["short_kappa_second_sector"],
        leakage_sector_stream=system["leakage"],
        long_allowance_second=kwargs["long_allowance_second"],
        short_allowance_second=kwargs["short_allowance_second"],
        coupling_uplift_db=kwargs["coupling_uplift_db"],
    )
    actual = np.asarray(system["stream_power"], dtype=np.float64)
    baseline = np.asarray(system["baseline_sector"], dtype=np.float64)
    used = np.sum(actual * matrix, axis=1)
    budget = baseline * np.sum(actual, axis=1)
    positive = budget > np.finfo(np.float64).tiny
    ratio = np.zeros_like(used)
    ratio[positive] = used[positive] / budget[positive]
    ratio[~positive] = np.where(
        used[~positive] <= np.finfo(np.float64).tiny, 0.0, np.inf
    )
    maximum_ratio = float(np.max(ratio))
    power_feasible = bool(maximum_ratio <= 1.0 + 1e-10)
    exact_feasible = bool(
        audit.floor_violation_count == 0
        and audit.long_violation_seconds == 0
        and audit.short_violation_seconds == 0
        and power_feasible
    )
    return {
        "exact_feasible": exact_feasible,
        "floor_violation_count": int(audit.floor_violation_count),
        "long_violation_seconds": int(audit.long_violation_seconds),
        "short_violation_seconds": int(audit.short_violation_seconds),
        "maximum_normalized_floor_shortfall": float(
            audit.maximum_normalized_floor_shortfall
        ),
        "minimum_active_eligible_floor_ratio": (
            None
            if audit.minimum_active_eligible_floor_ratio is None
            else float(audit.minimum_active_eligible_floor_ratio)
        ),
        "maximum_long_ratio": float(audit.maximum_long_ratio),
        "maximum_short_ratio": float(audit.maximum_short_ratio),
        "strict_post_mode_power_feasible": power_feasible,
        "maximum_strict_post_mode_power_ratio": maximum_ratio,
    }


def exact_outcome_audit(
    repair: Any,
    outcome: Any,
    kwargs: dict[str, Any],
    system: dict[str, Any],
) -> dict[str, Any]:
    if outcome.stream_scale is None:
        return {
            "exact_feasible": False,
            "floor_violation_count": None,
            "long_violation_seconds": None,
            "short_violation_seconds": None,
            "maximum_normalized_floor_shortfall": None,
            "minimum_active_eligible_floor_ratio": None,
            "maximum_long_ratio": None,
            "maximum_short_ratio": None,
            "strict_post_mode_power_feasible": None,
            "maximum_strict_post_mode_power_ratio": None,
        }
    return exact_stream_audit(
        repair,
        np.asarray(outcome.stream_scale, dtype=np.float64),
        kwargs,
        system,
    )

def build_systems(repair: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    q = np.asarray(kwargs["q_db"], dtype=np.float64)
    baseline_sector = np.asarray(kwargs["baseline_sector_scale"], dtype=np.float64)
    amplitude = repair.mode_adjusted_amplitude(kwargs["state"], q)
    gain = np.abs(amplitude) ** 2
    leakage, stream_power, nominal_q0 = repair.stream_leakage_and_power_envelopes(
        kwargs["matrices"], q, kwargs["steering_pol1"], kwargs["steering_pol2"]
    )
    floor_system = repair.floor_system_for_stream_scales(
        gain,
        np.asarray(kwargs["state"].other_weighted_rate, dtype=np.float64),
        np.asarray(kwargs["state"].active_user, dtype=bool),
        kwargs["eligible_user"],
        kwargs["floors"],
        kwargs["serving_bs"],
        kwargs["serving_stream"],
        kwargs["protected_noise_w"],
        kwargs["protected_weight"],
    )
    eess_system = repair.eess_system_for_stream_scales(
        kwargs["long_kappa_second_sector"],
        kwargs["short_kappa_second_sector"],
        leakage,
        kwargs["long_allowance_second"],
        kwargs["short_allowance_second"],
        kwargs["coupling_uplift_db"],
    )
    hard = repair.combine_systems(floor_system, eess_system)
    baseline_stream = np.repeat(baseline_sector, gain.shape[2])
    baseline_audit = repair.exact_audit(
        gain_user_sector_stream=gain,
        stream_scale=baseline_stream.reshape(gain.shape[1], gain.shape[2]),
        other_weighted_rate=kwargs["state"].other_weighted_rate,
        active_user=kwargs["state"].active_user,
        eligible_user=kwargs["eligible_user"],
        floors=kwargs["floors"],
        serving_bs=kwargs["serving_bs"],
        serving_stream=kwargs["serving_stream"],
        protected_noise_w=kwargs["protected_noise_w"],
        protected_weight=kwargs["protected_weight"],
        long_kappa_second_sector=kwargs["long_kappa_second_sector"],
        short_kappa_second_sector=kwargs["short_kappa_second_sector"],
        leakage_sector_stream=leakage,
        long_allowance_second=kwargs["long_allowance_second"],
        short_allowance_second=kwargs["short_allowance_second"],
        coupling_uplift_db=kwargs["coupling_uplift_db"],
    )
    violating = np.flatnonzero(baseline_audit.floor_violation_mask)
    critical = tuple(sorted(set(int(np.asarray(kwargs["serving_bs"])[u]) for u in violating)))
    return {
        "q": q,
        "baseline_sector": baseline_sector,
        "baseline_stream": baseline_stream,
        "gain": gain,
        "leakage": leakage,
        "stream_power": stream_power,
        "nominal_q0_stream_power": nominal_q0,
        "hard": hard,
        "baseline_audit": baseline_audit,
        "violating_users": violating,
        "critical": critical,
    }


def strict_global_solver(repair: Any, system: dict[str, Any], reserve: float) -> Any:
    gain = system["gain"]
    count = gain.shape[1] * gain.shape[2]
    mapping = np.eye(count, dtype=np.float64)
    offset = np.zeros(count, dtype=np.float64)
    base = system["baseline_stream"].copy()
    power = repair.local_sector_power_budget_system(
        mapping=mapping,
        offset=offset,
        actual_stream_power=system["stream_power"],
        envelope_stream_power=system["stream_power"],
        baseline_sector_scale=system["baseline_sector"],
        constrained_sectors=tuple(range(gain.shape[1])),
        label_prefix="strict_global_post_mode_power_budget",
    )
    return repair.solve_continuous_l1(
        system["hard"],
        mapping,
        offset,
        base,
        np.zeros_like(base),
        np.ones_like(base),
        np.maximum(system["stream_power"].reshape(-1), 1e-12),
        extra_system=power,
        constraint_reserve=reserve,
    )



def independent_global_feasibility_crosscheck(
    repair: Any,
    kwargs: dict[str, Any],
    system: dict[str, Any],
) -> dict[str, Any]:
    """Cross-check untightened global feasibility with HiGHS dual simplex/IPM.

    Two independent HiGHS algorithms are used on a zero-objective formulation.
    Infeasibility is classified as solver-certified only when both return status
    2. Any recovered vector is subjected to the exact nonlinear and physical
    power audit before it is accepted as a witness.
    """
    count = system["gain"].shape[1] * system["gain"].shape[2]
    mapping = np.eye(count, dtype=np.float64)
    offset = np.zeros(count, dtype=np.float64)
    power = repair.local_sector_power_budget_system(
        mapping=mapping,
        offset=offset,
        actual_stream_power=system["stream_power"],
        envelope_stream_power=system["stream_power"],
        baseline_sector_scale=system["baseline_sector"],
        constrained_sectors=tuple(range(system["gain"].shape[1])),
        label_prefix="strict_global_post_mode_power_budget_crosscheck",
    )
    decision_system = repair.combine_systems(
        repair.mapped_system(system["hard"], mapping, offset), power
    )
    a = np.asarray(decision_system.a_ub, dtype=np.float64)
    b = np.asarray(decision_system.b_ub, dtype=np.float64)
    row_norm = np.max(np.abs(a), axis=1)
    scale = np.maximum(
        np.maximum(row_norm, np.abs(b)), np.finfo(np.float64).tiny
    )
    a = a / scale[:, None]
    b = b / scale
    records: list[dict[str, Any]] = []
    witness_found = False
    for method in ("highs-ds", "highs-ipm"):
        result = linprog(
            np.zeros(count, dtype=np.float64),
            A_ub=a,
            b_ub=b,
            bounds=[(0.0, 1.0)] * count,
            method=method,
            options={
                "presolve": True,
                "primal_feasibility_tolerance": 1e-9,
                "dual_feasibility_tolerance": 1e-9,
            },
        )
        exact = None
        if result.x is not None:
            exact = exact_stream_audit(
                repair, np.asarray(result.x, dtype=np.float64), kwargs, system
            )
            witness_found = witness_found or bool(exact["exact_feasible"])
        records.append(
            {
                "method": method,
                "success": bool(result.success),
                "status_code": int(result.status),
                "message": str(result.message),
                "exact_audit": exact,
            }
        )
    certified_infeasible = bool(
        not witness_found and all(record["status_code"] == 2 for record in records)
    )
    return {
        "witness_found": witness_found,
        "solver_certified_infeasible": certified_infeasible,
        "records": records,
    }

def expanded_solver(
    repair: Any,
    kwargs: dict[str, Any],
    system: dict[str, Any],
    *,
    external_per_user: int,
    all_stream: bool,
    eess_count: int = 4,
    constraint_reserve: float = RESERVE,
) -> tuple[Any, dict[str, Any]]:
    gain = system["gain"]
    external = repair.top_external_interfering_sectors(
        gain,
        system["baseline_stream"].reshape(gain.shape[1], gain.shape[2]),
        system["violating_users"],
        kwargs["serving_bs"],
        per_user=min(int(external_per_user), gain.shape[1] - 1),
    )
    eess = repair.top_eess_contributing_sectors(
        kwargs["long_kappa_second_sector"],
        kwargs["short_kappa_second_sector"],
        system["leakage"],
        system["baseline_stream"].reshape(gain.shape[1], gain.shape[2]),
        kwargs["long_allowance_second"],
        kwargs["short_allowance_second"],
        kwargs["coupling_uplift_db"],
        count=int(eess_count),
        stress_sectors=system["critical"],
        excluded_sectors=system["critical"],
    )
    selected = tuple(sorted(set(system["critical"]) | set(external) | set(eess)))
    if all_stream:
        mapping, offset, base, names = repair.sparse_hybrid_mapping(
            system["baseline_sector"], selected, (), stream_count=gain.shape[2]
        )
        weights: list[float] = []
        for sector in selected:
            weights.extend(np.maximum(system["stream_power"][sector], 1e-12).tolist())
        upper = np.ones_like(base)
        constrained = selected
        action = "EXPANDED_LOCAL_ALL_STREAM"
    else:
        external_scalar = tuple(sorted((set(external) | set(eess)) - set(system["critical"])))
        mapping, offset, base, names = repair.sparse_hybrid_mapping(
            system["baseline_sector"], system["critical"], external_scalar, stream_count=gain.shape[2]
        )
        weights = []
        for sector in system["critical"]:
            weights.extend(np.maximum(system["stream_power"][sector], 1e-12).tolist())
        for sector in external_scalar:
            weights.append(float(max(np.sum(system["stream_power"][sector]), 1e-12)))
        upper = np.ones_like(base)
        for index, name in enumerate(names):
            if name.endswith(":scalar"):
                sector = int(name.split(":", 1)[0].split("=", 1)[1])
                upper[index] = system["baseline_sector"][sector]
        constrained = system["critical"]
        action = "EXPANDED_LOCAL_HYBRID"
    power = repair.local_sector_power_budget_system(
        mapping=mapping,
        offset=offset,
        actual_stream_power=system["stream_power"],
        envelope_stream_power=system["stream_power"],
        baseline_sector_scale=system["baseline_sector"],
        constrained_sectors=constrained,
        label_prefix="expanded_strict_post_mode_power_budget",
    )
    outcome = repair.solve_continuous_l1(
        system["hard"],
        mapping,
        offset,
        base,
        np.zeros_like(base),
        upper,
        np.asarray(weights, dtype=np.float64),
        extra_system=power,
        constraint_reserve=float(constraint_reserve),
    )
    return outcome, {
        "action_class": action,
        "external_per_user": int(external_per_user),
        "eess_neighbourhood_size": int(eess_count),
        "critical_sectors": list(system["critical"]),
        "external_sectors": list(external),
        "eess_sectors": list(eess),
        "mutable_sectors": list(selected),
        "mutable_sector_count": len(selected),
        "variable_count": int(len(base)),
    }


def diagnose_interval(
    repair: Any,
    kwargs: dict[str, Any],
    choice: Any,
    pass_slot: int,
    interval_record: dict[str, Any],
    full_nominal: np.ndarray,
) -> dict[str, Any]:
    system = build_systems(repair, kwargs)
    global_reserved = strict_global_solver(repair, system, RESERVE)
    global_reserved_audit = exact_outcome_audit(
        repair, global_reserved, kwargs, system
    )
    global_unreserved = None
    global_unreserved_audit = None
    global_crosscheck = None
    global_exact = bool(global_reserved_audit["exact_feasible"])
    global_source = "reserved_l1" if global_exact else None
    global_proven_infeasible = False
    global_solver_uncertified = False

    if not global_exact:
        global_unreserved = strict_global_solver(repair, system, 0.0)
        global_unreserved_audit = exact_outcome_audit(
            repair, global_unreserved, kwargs, system
        )
        if bool(global_unreserved_audit["exact_feasible"]):
            global_exact = True
            global_source = "unreserved_l1_boundary"
        else:
            global_crosscheck = independent_global_feasibility_crosscheck(
                repair, kwargs, system
            )
            if bool(global_crosscheck["witness_found"]):
                global_exact = True
                global_source = "independent_zero_objective_lp"
            elif bool(global_crosscheck["solver_certified_infeasible"]):
                global_proven_infeasible = True
                global_source = "dual_simplex_and_ipm_infeasible"
            else:
                global_solver_uncertified = True
                global_source = "solver_uncertified"

    selected_expanded: dict[str, Any] | None = None
    expanded_records: list[dict[str, Any]] = []
    expanded_solver_uncertified = False
    if global_exact:
        for k in (4, 8):
            for all_stream in (False, True):
                outcome, scope = expanded_solver(
                    repair,
                    kwargs,
                    system,
                    external_per_user=k,
                    all_stream=all_stream,
                    eess_count=4,
                    constraint_reserve=RESERVE,
                )
                audit = exact_outcome_audit(repair, outcome, kwargs, system)
                record: dict[str, Any] = {
                    "scope": scope,
                    "reserved_solver": outcome_record(outcome),
                    "reserved_exact_audit": audit,
                    "unreserved_solver": None,
                    "unreserved_exact_audit": None,
                    "witness_type": None,
                }
                if bool(audit["exact_feasible"]):
                    record["witness_type"] = "CERTIFIED_RESERVE"
                    selected_expanded = record
                else:
                    unreserved, _ = expanded_solver(
                        repair,
                        kwargs,
                        system,
                        external_per_user=k,
                        all_stream=all_stream,
                        eess_count=4,
                        constraint_reserve=0.0,
                    )
                    unreserved_audit = exact_outcome_audit(
                        repair, unreserved, kwargs, system
                    )
                    record["unreserved_solver"] = outcome_record(unreserved)
                    record["unreserved_exact_audit"] = unreserved_audit
                    if bool(unreserved_audit["exact_feasible"]):
                        record["witness_type"] = "BOUNDARY_WITHOUT_RESERVE"
                        selected_expanded = record
                    elif str(unreserved.status) not in {"INFEASIBLE"}:
                        expanded_solver_uncertified = True
                expanded_records.append(record)
                if selected_expanded is not None:
                    break
            if selected_expanded is not None:
                break

    users = []
    optimistic_infeasible = False
    current_load_policy_mismatch = False
    for user in system["violating_users"]:
        user_i = int(user)
        optimistic = repair.optimistic_single_user_upper_bound(
            user=user_i,
            gain_user_sector_stream=system["gain"],
            other_weighted_rate=kwargs["state"].other_weighted_rate,
            serving_bs=kwargs["serving_bs"],
            serving_stream=kwargs["serving_stream"],
            protected_noise_w=kwargs["protected_noise_w"],
            protected_weight=kwargs["protected_weight"],
            long_kappa_second_sector=kwargs["long_kappa_second_sector"],
            short_kappa_second_sector=kwargs["short_kappa_second_sector"],
            leakage_sector_stream=system["leakage"],
            long_allowance_second=kwargs["long_allowance_second"],
            short_allowance_second=kwargs["short_allowance_second"],
            coupling_uplift_db=kwargs["coupling_uplift_db"],
        )
        floor = float(np.asarray(kwargs["floors"])[user_i])
        current_nominal = float(
            np.asarray(kwargs["state"].nominal_total_rate)[user_i]
        )
        relative = 0.9 * current_nominal
        branch = (
            "ABSOLUTE_0P1"
            if 0.1 >= relative - 1e-12
            else "RELATIVE_0P9_CURRENT_LOAD_NOMINAL"
        )
        optimistic_ok = (
            float(optimistic["optimistic_total_rate_bps_hz"])
            >= floor - 1e-12
        )
        policy_mismatch = bool(
            branch == "ABSOLUTE_0P1" and current_nominal < 0.1 - 1e-12
        )
        optimistic_infeasible = optimistic_infeasible or not optimistic_ok
        current_load_policy_mismatch = (
            current_load_policy_mismatch or policy_mismatch
        )
        users.append(
            {
                "user_index": user_i,
                "user_id": user_id(user_i),
                "serving_sector": int(
                    np.asarray(kwargs["serving_bs"])[user_i]
                ),
                "serving_stream": int(
                    np.asarray(kwargs["serving_stream"])[user_i]
                ),
                "full_load_nominal_total_rate_bps_hz": float(
                    full_nominal[user_i]
                ),
                "current_load_nominal_total_rate_bps_hz": current_nominal,
                "floor_bps_hz": floor,
                "floor_branch": branch,
                "current_load_nominal_meets_absolute_floor": bool(
                    current_nominal >= 0.1 - 1e-12
                ),
                "current_load_serviceability_mismatch": policy_mismatch,
                "optimistic_single_user": optimistic,
                "optimistic_single_user_floor_feasible": optimistic_ok,
            }
        )

    if selected_expanded is not None:
        suffix = (
            "FEASIBLE"
            if selected_expanded["witness_type"] == "CERTIFIED_RESERVE"
            else "BOUNDARY_FEASIBLE_WITHOUT_RESERVE"
        )
        classification = (
            f"{selected_expanded['scope']['action_class']}_"
            f"K{selected_expanded['scope']['external_per_user']}_{suffix}"
        )
    elif global_exact and expanded_solver_uncertified:
        classification = (
            "EXPANDED_LOCAL_SOLVER_UNCERTIFIED_WITH_GLOBAL_FIXED_BEAM_FEASIBLE"
        )
    elif global_exact:
        classification = (
            "STRICT_GLOBAL_FIXED_BEAM_FEASIBLE_BUT_EXPANDED_LOCAL_K8_INFEASIBLE"
        )
    elif global_proven_infeasible and optimistic_infeasible:
        classification = "FIXED_Q_FIXED_BEAM_SINGLE_USER_INFEASIBLE"
    elif global_proven_infeasible:
        classification = "FIXED_Q_FIXED_BEAM_JOINT_GLOBAL_INFEASIBLE"
    elif global_solver_uncertified:
        classification = "STRICT_GLOBAL_FIXED_BEAM_SOLVER_UNCERTIFIED"
    else:
        classification = "STRICT_GLOBAL_FIXED_BEAM_UNCLASSIFIED"

    return {
        "pass_slot": int(pass_slot),
        "interval_index": int(interval_record["interval_index"]),
        "interval_seconds": int(interval_record["interval_seconds"]),
        "original_candidate_floor_violation_count": int(
            interval_record["candidate_floor_violation_count"]
        ),
        "original_candidate_action_class": str(
            interval_record["chosen_action_class"]
        ),
        "pre_repair_violating_users": [
            int(v) for v in interval_record["pre_repair_violating_users"]
        ],
        "classification": classification,
        "global_feasibility_source": global_source,
        "current_load_serviceability_mismatch_present": (
            current_load_policy_mismatch
        ),
        "existing_oracles": {
            "continuous_sector": outcome_record(choice.continuous_sector),
            "frozen_grid_sector": outcome_record(choice.frozen_grid_sector),
            "local_frozen_grid_sector": outcome_record(
                choice.local_frozen_grid_sector
            ),
            "strict_post_mode_sparse_stream": outcome_record(
                choice.strict_post_mode_sparse_stream
            ),
            "q0_nominal_envelope_sparse_stream": outcome_record(
                choice.q0_nominal_envelope_sparse_stream
            ),
            "legacy_global_stream_oracle_without_sector_power_envelopes": (
                outcome_record(choice.global_stream_oracle)
            ),
        },
        "strict_global_fixed_beam_reserved": {
            "solver": outcome_record(global_reserved),
            "exact_audit": global_reserved_audit,
        },
        "strict_global_fixed_beam_unreserved": (
            None
            if global_unreserved is None
            else {
                "solver": outcome_record(global_unreserved),
                "exact_audit": global_unreserved_audit,
            }
        ),
        "strict_global_independent_crosscheck": global_crosscheck,
        "expanded_local_trials": expanded_records,
        "selected_expanded_local_witness": selected_expanded,
        "users": users,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--campaign-run-root", type=Path, required=True)
    parser.add_argument("--job-package-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    seed = int(args.seed)
    if seed not in FAILED_SEEDS:
        raise RuntimeError(f"seed is outside frozen failed-seed scope: {seed}")
    run_root = args.campaign_run_root.resolve()
    job_root = args.job_package_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    contract = json.loads((job_root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8"))
    if contract["package_id"] != EXPECTED_PACKAGE_ID:
        raise RuntimeError("job-package ID mismatch")
    if contract["candidate_v4_3"]["source_manifest_sha256"] != EXPECTED_SOURCE_MANIFEST:
        raise RuntimeError("candidate source-manifest mismatch")

    sys.path.insert(0, str(job_root))
    sys.path.insert(0, str(job_root / "src"))
    import phase1_seed_worker as worker  # type: ignore
    from fr3_cbf import floor_feasibility_repair as repair  # type: ignore

    seed_root = run_root / "results" / f"seed_{seed}"
    channel_root = seed_root / "channel"
    original_result_path = seed_root / "result" / "SEED_RESULT.json"
    if not (channel_root / "CHANNEL_RECORD.json").is_file() or not original_result_path.is_file():
        raise RuntimeError(f"preserved seed data missing: {seed_root}")
    original = json.loads(original_result_path.read_text(encoding="utf-8"))
    if int(original["campaign_seed"]) != seed or bool(original["candidate_hard_gates_pass"]):
        raise RuntimeError("seed result is not the expected failed campaign seed")
    channel_record = json.loads((channel_root / "CHANNEL_RECORD.json").read_text(encoding="utf-8"))
    if int(channel_record["campaign_seed"]) != seed:
        raise RuntimeError("channel record seed mismatch")

    started = time.perf_counter()
    data = worker.load_channel(channel_root)
    campaign_contract = json.loads((job_root / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json").read_text(encoding="utf-8"))
    pass_temp = output_dir / "pass_extract"
    pass_roots = [worker.extract_pass(slot, pass_temp) for slot in range(5)]
    pass_lengths = [len(np.load(path / "protected_time_s.npy")) for path in pass_roots]
    architecture, _h_effective, full_state, architecture_audit, schedules, state_cache = worker.create_states(
        data, campaign_contract, pass_lengths
    )

    interval_diagnostics: list[dict[str, Any]] = []
    reproduction_rows: list[dict[str, Any]] = []
    original_repair = repair.repair_interval
    temp_result = output_dir / "rerun_result"
    for slot, pass_root in enumerate(pass_roots):
        captures: list[tuple[dict[str, Any], Any]] = []

        def capturing_repair(**kwargs: Any) -> Any:
            choice = original_repair(**kwargs)
            captures.append((dict(kwargs), choice))
            return choice

        repair.repair_interval = capturing_repair
        try:
            _rows, rerun_audit = worker.pass_evaluation(
                slot,
                pass_root,
                data,
                campaign_contract,
                architecture,
                full_state,
                schedules[slot],
                state_cache,
                temp_result,
            )
        finally:
            repair.repair_interval = original_repair

        expected_audit = original["pass_audits"][slot]
        expected_records = expected_audit["candidate_interval_records"]
        if len(captures) != len(expected_records):
            raise RuntimeError(f"pass {slot}: captured repair count mismatch")
        for key in [
            "eligible_floor_violation_user_seconds",
            "eligible_floor_violation_user_intervals",
            "long_violation_seconds",
            "short_violation_seconds",
            "unresolved_deployable_intervals",
        ]:
            if int(rerun_audit["candidate_hard_gates"][key]) != int(expected_audit["candidate_hard_gates"][key]):
                raise RuntimeError(f"pass {slot}: candidate reproduction mismatch: {key}")
        if rerun_audit["candidate_action_diagnostics"]["action_class_counts"] != expected_audit["candidate_action_diagnostics"]["action_class_counts"]:
            raise RuntimeError(f"pass {slot}: action-class reproduction mismatch")
        reproduction_rows.append({
            "pass_slot": slot,
            "status": "PASS",
            "floor_violation_user_seconds": int(rerun_audit["candidate_hard_gates"]["eligible_floor_violation_user_seconds"]),
            "unresolved_deployable_intervals": int(rerun_audit["candidate_hard_gates"]["unresolved_deployable_intervals"]),
            "captured_repair_intervals": len(captures),
        })
        for record, captured in zip(expected_records, captures, strict=True):
            kwargs, choice = captured
            if str(record["chosen_action_class"]) != str(choice.chosen_action_class):
                raise RuntimeError(f"pass {slot}: interval action reproduction mismatch")
            if str(record["chosen_action_class"]) != "NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND":
                continue
            interval_diagnostics.append(
                diagnose_interval(
                    repair,
                    kwargs,
                    choice,
                    slot,
                    record,
                    np.asarray(full_state.nominal_total_rate, dtype=np.float64),
                )
            )

    classification_counts = Counter(
        item["classification"] for item in interval_diagnostics
    )
    expanded_certified_count = sum(
        value
        for key, value in classification_counts.items()
        if key.startswith("EXPANDED_LOCAL_") and key.endswith("_FEASIBLE")
    )
    expanded_boundary_count = sum(
        value
        for key, value in classification_counts.items()
        if key.startswith("EXPANDED_LOCAL_")
        and "BOUNDARY_FEASIBLE_WITHOUT_RESERVE" in key
    )
    global_only_count = int(
        classification_counts.get(
            "STRICT_GLOBAL_FIXED_BEAM_FEASIBLE_BUT_EXPANDED_LOCAL_K8_INFEASIBLE",
            0,
        )
    )
    solver_uncertified_count = sum(
        value
        for key, value in classification_counts.items()
        if "SOLVER_UNCERTIFIED" in key or key.endswith("_UNCLASSIFIED")
    )
    boundary_count = expanded_boundary_count + sum(
        1
        for item in interval_diagnostics
        if item.get("global_feasibility_source") == "unreserved_l1_boundary"
    )
    single_infeasible = int(
        classification_counts.get(
            "FIXED_Q_FIXED_BEAM_SINGLE_USER_INFEASIBLE", 0
        )
    )
    joint_infeasible = int(
        classification_counts.get(
            "FIXED_Q_FIXED_BEAM_JOINT_GLOBAL_INFEASIBLE", 0
        )
    )
    serviceability_mismatch_count = sum(
        1
        for item in interval_diagnostics
        if item["current_load_serviceability_mismatch_present"]
    )
    if len(interval_diagnostics) != sum(
        int(pass_audit["candidate_hard_gates"]["unresolved_deployable_intervals"])
        for pass_audit in original["pass_audits"]
    ):
        raise RuntimeError("unresolved interval diagnosis count mismatch")

    if expanded_certified_count == len(interval_diagnostics):
        status = (
            "PASS_ALL_UNRESOLVED_INTERVALS_FEASIBLE_WITH_CERTIFIED_"
            "EXPANDED_LOCAL_FIXED_BEAM_ACTIONS"
        )
    elif single_infeasible or joint_infeasible:
        status = (
            "VALID_DIAGNOSIS_FIXED_BEAM_INFEASIBILITY_REQUIRES_"
            "SCHEDULING_REASSIGNMENT"
        )
    elif solver_uncertified_count:
        status = "VALID_DIAGNOSIS_SOLVER_UNCERTIFIED_INTERVALS_REQUIRE_REVIEW"
    elif expanded_certified_count + expanded_boundary_count == len(
        interval_diagnostics
    ):
        status = "VALID_DIAGNOSIS_LOCAL_BOUNDARY_WITNESS_REFINEMENT_REQUIRED"
    else:
        status = "VALID_DIAGNOSIS_BROADER_COORDINATION_REQUIRED"
    rc = 0

    summary = {
        "schema_version": 1,
        "status": status,
        "campaign_seed": seed,
        "candidate_source_changed": False,
        "channel_reused": True,
        "channel_regenerated": False,
        "gpu_requested": False,
        "campaign_run_root": str(run_root),
        "channel_record_sha256": sha256_file(channel_root / "CHANNEL_RECORD.json"),
        "original_seed_result_sha256": sha256_file(original_result_path),
        "original_floor_violation_user_seconds": sum(
            int(record["candidate_hard_gates"]["eligible_floor_violation_user_seconds"])
            for record in original["pass_audits"]
        ),
        "original_unresolved_interval_count": len(interval_diagnostics),
        "classification_counts": dict(classification_counts),
        "expanded_local_certified_interval_count": expanded_certified_count,
        "expanded_local_boundary_interval_count": expanded_boundary_count,
        "strict_global_only_interval_count": global_only_count,
        "solver_uncertified_interval_count": solver_uncertified_count,
        "boundary_only_interval_count": boundary_count,
        "fixed_beam_single_user_infeasible_interval_count": single_infeasible,
        "fixed_beam_joint_infeasible_interval_count": joint_infeasible,
        "current_load_serviceability_mismatch_interval_count": serviceability_mismatch_count,
        "reproduction_passes": reproduction_rows,
        "runtime_seconds": time.perf_counter() - started,
        "claim_boundary": "POST_CAMPAIGN_DIAGNOSIS_REUSING_PRESERVED_CHANNEL_NOT_NEW_CONFIRMATORY_SAMPLE",
    }
    (output_dir / "FAILED_SEED_DIAGNOSIS.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "INTERVAL_FEASIBILITY_DIAGNOSIS.json").write_text(
        json.dumps(interval_diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    pd.DataFrame(reproduction_rows).to_csv(output_dir / "REPRODUCTION_AUDIT.csv", index=False)
    user_rows: list[dict[str, Any]] = []
    for item in interval_diagnostics:
        for user in item["users"]:
            row = {
                "campaign_seed": seed,
                "pass_slot": item["pass_slot"],
                "interval_index": item["interval_index"],
                "classification": item["classification"],
                **user,
            }
            optimistic = row.pop("optimistic_single_user")
            for key, value in optimistic.items():
                column = key if key.startswith("optimistic_") else f"optimistic_{key}"
                row[column] = value
            user_rows.append(row)
    pd.DataFrame(user_rows).to_csv(output_dir / "AFFECTED_USER_DIAGNOSIS.csv", index=False)
    if temp_result.exists():
        shutil.rmtree(temp_result)
    if pass_temp.exists():
        shutil.rmtree(pass_temp)

    print(f"FAILED_SEED_DIAGNOSIS_STATUS={status}")
    print(f"CAMPAIGN_SEED={seed}")
    print("CANDIDATE_SOURCE_CHANGED=NO")
    print("CHANNEL_REUSED=YES")
    print("CHANNEL_REGENERATION=NO")
    print("GPU_REQUESTED=NO")
    print(f"ORIGINAL_UNRESOLVED_INTERVALS={len(interval_diagnostics)}")
    print(
        f"EXPANDED_LOCAL_CERTIFIED_INTERVALS={expanded_certified_count}"
    )
    print(f"EXPANDED_LOCAL_BOUNDARY_INTERVALS={expanded_boundary_count}")
    print(f"STRICT_GLOBAL_ONLY_INTERVALS={global_only_count}")
    print(f"SOLVER_UNCERTIFIED_INTERVALS={solver_uncertified_count}")
    print(f"BOUNDARY_ONLY_INTERVALS={boundary_count}")
    print(f"FIXED_BEAM_SINGLE_USER_INFEASIBLE_INTERVALS={single_infeasible}")
    print(f"FIXED_BEAM_JOINT_INFEASIBLE_INTERVALS={joint_infeasible}")
    print(f"CURRENT_LOAD_SERVICEABILITY_MISMATCH_INTERVALS={serviceability_mismatch_count}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
