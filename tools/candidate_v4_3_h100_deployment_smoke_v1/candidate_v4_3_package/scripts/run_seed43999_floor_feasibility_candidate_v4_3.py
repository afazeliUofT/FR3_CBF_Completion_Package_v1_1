#!/usr/bin/env python3
"""CPU-only exact seed-43999 floor-feasibility repair diagnostic.

The script imports the immutable reviewed phase-1 package, reuses the preserved
H100-generated seed-43999 channel, reproduces all five passes and eight reviewed
methods, and then applies candidate-v4.3 only as a separately versioned fixed-q,
fixed-beam repair layer.  It never generates a channel and never authorizes the
confirmatory campaign.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import traceback
from typing import Any

import numpy as np
import pandas as pd

PRED = "robust_predictive_constrained_pf_with_sector_selective_fallback"
REACTIVE = "delayed_myopic_constrained_pf_with_reactive_sector_fallback"
EXPECTED_PRED_FLOOR_SECONDS = 519
EXPECTED_PRED_FLOOR_INTERVALS = 104
EXPECTED_AFFECTED = {23, 73}
GRID_DB = tuple(float(v) for v in range(13)) + (math.inf,)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_array(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return None
        return "Infinity" if value > 0 else "-Infinity"
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jsonable(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_status(path: Path, values: dict[str, Any]) -> None:
    lines = []
    for key, value in values.items():
        text = str(value).replace("\n", " ")
        lines.append(f"{key}={text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_worker(package_root: Path):
    sys.path.insert(0, str(package_root))
    sys.path.insert(0, str(package_root / "src"))
    sys.path.insert(0, str(package_root / "channel_generator"))
    return load_module(
        package_root / "phase1_seed_worker.py",
        "phase1_seed_worker_candidate_v4_3_import",
    )


def floor_metrics(
    delivered: np.ndarray,
    active: np.ndarray,
    eligible: np.ndarray,
    floors: np.ndarray,
) -> tuple[int, float, float | None, float]:
    valid = np.asarray(active, bool) & np.asarray(eligible, bool) & (floors > 0.0)
    violation = valid & (delivered < floors - 1e-12)
    if not np.any(valid):
        return 0, 0.0, None, 0.0
    short = np.maximum(0.0, (floors[valid] - delivered[valid]) / floors[valid])
    return (
        int(np.sum(violation)),
        float(np.sum(short)),
        float(np.min(delivered[valid] / floors[valid])),
        float(np.max(short)),
    )


def solver_record(outcome: Any) -> dict[str, Any]:
    return {
        "status": outcome.status,
        "feasible": bool(outcome.feasible),
        "optimal": bool(outcome.optimal),
        "objective": outcome.objective,
        "message": outcome.message,
        "maximum_constraint_excess": outcome.maximum_constraint_excess,
        "changed_variable_count": outcome.changed_variable_count,
        "decision_sha256": (
            sha256_array(np.asarray(outcome.decision))
            if outcome.decision is not None
            else None
        ),
    }


def mode_case_rates(
    repair: Any,
    state: Any,
    q_db: np.ndarray,
    stream_scale: np.ndarray,
    data: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    amplitude = repair.mode_adjusted_amplitude(state, q_db)
    gain = np.abs(amplitude) ** 2
    total, protected = repair.exact_rates_from_stream_scale(
        gain,
        stream_scale,
        state.other_weighted_rate,
        state.active_user,
        data["serving"],
        data["stream"],
        float(data["noise"][4]),
        float(data["weights"][4]),
    )
    return total, protected, gain


def decompose_user_power(
    gain: np.ndarray,
    stream_scale: np.ndarray,
    user: int,
    serving: np.ndarray,
    stream: np.ndarray,
    noise: float,
) -> dict[str, float]:
    bs = int(serving[user])
    local_stream = int(stream[user])
    power = gain[user] * stream_scale
    desired = float(power[bs, local_stream])
    same = float(np.sum(power[bs]) - desired)
    external = float(np.sum(power) - np.sum(power[bs]))
    denominator = same + external + float(noise)
    return {
        "desired_power_w": desired,
        "same_sector_interference_w": max(same, 0.0),
        "external_sector_interference_w": max(external, 0.0),
        "protected_noise_w": float(noise),
        "sinr": desired / denominator if denominator > 0.0 else math.inf,
        "same_sector_fraction_of_nonnoise_interference": (
            same / (same + external) if same + external > 0.0 else 0.0
        ),
        "external_fraction_of_nonnoise_interference": (
            external / (same + external) if same + external > 0.0 else 0.0
        ),
    }


def classify_interval(choice: Any, optimistic: dict[str, Any], floor: float) -> str:
    if choice.local_frozen_grid_sector.feasible:
        return "SPARSE_LOCAL_FROZEN_GRID_FEASIBLE_REVIEWED_FALLBACK_SELECTION_DEFECT"
    if choice.strict_post_mode_sparse_stream.feasible:
        return (
            "LOCAL_SECTOR_GRID_INFEASIBLE_"
            "STRICT_POST_MODE_BUDGET_STREAM_REPAIR_FEASIBLE"
        )
    if choice.q0_nominal_envelope_sparse_stream.feasible:
        return (
            "Q0_ONLY_DIAGNOSTIC_WITNESS_NOT_DEPLOYABLE_UNDER_"
            "STRICT_POST_MODE_POWER_BUDGET"
        )
    if choice.frozen_grid_sector.feasible:
        return "GLOBAL_FROZEN_SECTOR_CLASS_FEASIBLE_LOCAL_DEPLOYABLE_CLASS_INFEASIBLE"
    if choice.continuous_sector.status == "INFEASIBLE":
        return "FULL_CONTINUOUS_SECTOR_SCALE_CLASS_PROVEN_INFEASIBLE"
    if choice.global_stream_oracle.feasible:
        return "DEPLOYABLE_LOCAL_REPAIR_INFEASIBLE_GLOBAL_FIXED_BEAM_STREAM_CLASS_FEASIBLE"
    if float(optimistic["optimistic_total_rate_bps_hz"]) < floor - 1e-12:
        return "FIXED_Q_FIXED_BEAM_SINGLE_USER_UPPER_BOUND_BELOW_FLOOR"
    return "COUPLED_FIXED_Q_FIXED_BEAM_CLASS_INFEASIBLE_OR_UNRESOLVED"

def make_manifest(output: Path) -> None:
    records = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name not in {"OUTPUT_MANIFEST.sha256"}:
            records.append(
                f"{sha256_file(path)}  {path.relative_to(output).as_posix()}"
            )
    (output / "OUTPUT_MANIFEST.sha256").write_text(
        "\n".join(records) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--channel-root", required=True)
    parser.add_argument("--candidate-source", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--expected-channel-record-sha256", required=True)
    parser.add_argument("--expected-frequency-array-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--grid-time-limit-s", type=float, default=45.0)
    args = parser.parse_args()

    package = Path(args.package_root).expanduser().resolve()
    channel = Path(args.channel_root).expanduser().resolve()
    candidate_source = Path(args.candidate_source).expanduser().resolve()
    output = Path(args.output_root).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    status_values: dict[str, Any] = {
        "CANDIDATE_STATUS": "RUNNING",
        "CONFIRMATORY_CAMPAIGN_AUTHORIZED": "NO",
        "NEXT_GATE": "CPU_ONLY_RORQUAL_EXACT_SEED43999_FEASIBILITY_DIAGNOSTIC",
    }
    write_status(output / "RUN_STATUS.env", status_values)

    try:
        record_path = channel / "CHANNEL_RECORD.json"
        actual_record_sha = sha256_file(record_path)
        if actual_record_sha != args.expected_channel_record_sha256:
            raise RuntimeError(
                "preserved CHANNEL_RECORD.json SHA-256 mismatch: "
                f"{actual_record_sha}"
            )

        repair = load_module(candidate_source, "fr3_floor_repair_candidate_v4_3")
        worker = load_worker(package)
        from fr3_cbf.dual_criterion_controller import interval_reduce
        from fr3_cbf.online_pf_load_transition import exponential_average_alpha
        from fr3_cbf.phase1_job_runtime import run_phase1_methods, summarize_method
        from fr3_cbf.null_floor_aware_sector_backoff import (
            SectorBackoffPriceAllocator,
            build_local_cost_table,
        )

        data = worker.load_channel(channel)
        actual_array_sha = str(
            data["record"]["frequency_response_sha256_array_bytes"]
        )
        if actual_array_sha != args.expected_frequency_array_sha256:
            raise RuntimeError(
                "preserved frequency-response array-byte SHA-256 mismatch: "
                f"{actual_array_sha}"
            )
        contract = json.loads(
            (package / "PHASE1_CAMPAIGN_CONTRACT_V3.json").read_text(
                encoding="utf-8"
            )
        )
        primary = contract["primary_scenario"]
        fairness = primary["fairness"]
        update_interval = int(primary["timing"]["update_interval_s"])
        if update_interval != 5:
            raise RuntimeError("frozen update interval changed")
        users = data["users"].reset_index().rename(columns={"index": "user_index"})

        with tempfile.TemporaryDirectory(prefix="fr3_candidate_v4_3_passes_") as name:
            pass_temp = Path(name)
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
            ) = worker.create_states(data, contract, pass_lengths)

            eligible = (
                np.asarray(full_state.nominal_total_rate, dtype=float)
                >= float(fairness["serviceability_threshold_bps_hz"])
            )
            alpha = exponential_average_alpha(
                float(update_interval),
                float(primary["moving_average_pf"]["time_constant_s"]),
            )

            all_method_rows: list[dict[str, Any]] = []
            candidate_rows: list[dict[str, Any]] = []
            affected_rows: list[dict[str, Any]] = []
            action_rows: list[dict[str, Any]] = []
            interval_certificates: list[dict[str, Any]] = []
            candidate_residual_rows: list[dict[str, Any]] = []
            pass_extension_records: list[dict[str, Any]] = []
            all_candidate_floor_seconds = 0
            all_candidate_floor_intervals = 0
            all_candidate_long_violations = 0
            all_candidate_short_violations = 0
            network_shutdown_intervals = 0
            baseline_formula_max_rate_error = 0.0
            baseline_formula_max_long_error = 0.0
            baseline_formula_max_short_error = 0.0
            predictive_reproduction_seconds = 0
            predictive_reproduction_intervals = 0
            affected_seen: set[int] = set()
            action_counter: Counter[str] = Counter()
            class_counter: Counter[str] = Counter()
            continuous_sector_proven_infeasible_intervals = 0
            global_frozen_proven_infeasible_intervals = 0
            local_frozen_repaired_intervals = 0
            local_stream_repaired_intervals = 0
            local_stream_proven_infeasible_intervals = 0
            global_stream_proven_infeasible_intervals = 0
            unresolved_deployable_intervals = 0
            strict_local_scope_violation_intervals = 0
            maximum_external_interferers_per_violating_user = 0
            maximum_eess_backoff_sectors = 0
            maximum_mutable_sector_count = 0
            strict_post_mode_stream_feasible_intervals = 0
            strict_post_mode_stream_infeasible_intervals = 0
            strict_post_mode_stream_uncertified_intervals = 0
            q0_headroom_used_intervals = 0
            maximum_q0_nominal_power_envelope_ratio = 0.0
            maximum_strict_post_mode_baseline_power_ratio = 0.0
            minimum_mode_adjusted_to_q0_power_ratio = math.inf
            maximum_mode_adjusted_to_q0_power_ratio = 0.0

            for slot, pass_root in enumerate(pass_roots):
                schedule, phase_records = schedules[slot]
                states: list[Any] = []
                matrix_indices: list[int] = []
                unique_keys: list[bytes] = []
                for mask in schedule:
                    key = mask.tobytes()
                    state, _matrix, _audit = state_cache[key]
                    states.append(state)
                    if key not in unique_keys:
                        unique_keys.append(key)
                    matrix_indices.append(unique_keys.index(key))
                matrices = [state_cache[key][1] for key in unique_keys]

                long_kappa = np.load(pass_root / "kappa_long_multiple.npy")
                short_kappa = np.load(pass_root / "kappa_short_multiple.npy")
                long_allowance = np.load(pass_root / "allowance_long_exact_w.npy")
                short_allowance = np.load(pass_root / "allowance_short_exact_w.npy")
                if not (
                    len(long_kappa) == len(short_kappa)
                    == len(long_allowance) == len(short_allowance)
                ):
                    raise RuntimeError(
                        f"pass {slot}: long/short physical-second arrays do not align"
                    )
                if len(states) != math.ceil(len(long_kappa) / update_interval):
                    raise RuntimeError(f"pass {slot}: interval count mismatch")
                kappa_interval, interval_lengths = interval_reduce(
                    long_kappa, update_interval, "max"
                )
                long_contribution = np.asarray(
                    [
                        kappa_interval[index, :, None]
                        * states[index].mode_leakage_w
                        for index in range(len(states))
                    ],
                    dtype=np.float64,
                )

                floors = np.zeros((len(states), len(eligible)), dtype=float)
                for index, state in enumerate(states):
                    active = np.asarray(state.active_user, bool) & eligible
                    floors[index, active] = np.maximum(
                        float(fairness["absolute_total_band_floor_bps_hz"]),
                        float(fairness["relative_current_load_floor_fraction"])
                        * np.asarray(state.nominal_total_rate)[active],
                    )

                methods = run_phase1_methods(
                    states=states,
                    matrices=matrices,
                    matrix_indices=matrix_indices,
                    long_kappa=long_kappa,
                    short_kappa=short_kappa,
                    long_allowance=long_allowance,
                    short_allowance=short_allowance,
                    interval_lengths=interval_lengths,
                    long_contribution=long_contribution,
                    serving=data["serving"],
                    stream=data["stream"],
                    protected_noise_w=float(data["noise"][4]),
                    protected_weight=float(data["weights"][4]),
                    initial_average=np.asarray(full_state.nominal_total_rate).copy(),
                    alpha=alpha,
                    eligible=eligible,
                    floors=floors,
                    steering1=architecture.effective_steering_pol1,
                    steering2=architecture.effective_steering_pol2,
                    update_interval_s=update_interval,
                    delay_intervals=1,
                    slew_db=3.0,
                    uplift_db=3.0,
                    cap_db=65.0,
                    epsilon=0.001,
                    virtual_queue_gain=1.0,
                )
                for method_id in worker.METHOD_IDS:
                    row = summarize_method(
                        methods[method_id], eligible, interval_lengths, epsilon=0.001
                    )
                    row.update(
                        {
                            "pass_slot": slot,
                            "protected_sample_count": int(len(long_kappa)),
                            "interval_count": int(len(states)),
                        }
                    )
                    all_method_rows.append(row)

                pred = methods[PRED]
                predictive_reproduction_seconds += int(
                    np.sum(pred.floor_violation_count * interval_lengths)
                )
                predictive_reproduction_intervals += int(
                    np.sum(pred.floor_violation_count)
                )

                candidate_total = np.empty_like(pred.delivered_total_rate)
                candidate_protected = np.empty_like(pred.delivered_protected_rate)
                candidate_average = np.empty_like(pred.moving_average_rate)
                candidate_floor_count = np.empty(len(states), dtype=np.int64)
                candidate_shortfall = np.empty(len(states), dtype=float)
                candidate_min_ratio = np.empty(len(states), dtype=float)
                candidate_max_shortfall = np.empty(len(states), dtype=float)
                candidate_stream = np.empty((len(states), 57, 4), dtype=float)
                candidate_sector_equiv = np.empty((len(states), 57), dtype=float)
                candidate_pre_repair_sector = np.empty((len(states), 57), dtype=float)
                candidate_pre_repair_envelope_ratio = np.empty(len(states), dtype=float)
                candidate_local_table_build_seconds = np.empty(len(states), dtype=float)
                candidate_action_class = np.empty(len(states), dtype="U96")
                candidate_long = np.empty(len(long_kappa), dtype=float)
                candidate_short = np.empty(len(short_kappa), dtype=float)
                current_average = np.asarray(full_state.nominal_total_rate, float).copy()
                candidate_allocator = SectorBackoffPriceAllocator(
                    np.asarray(GRID_DB, dtype=float)
                )

                for interval, state in enumerate(states):
                    start = interval * update_interval
                    stop = min(start + update_interval, len(long_kappa))
                    q = np.asarray(pred.q_db[interval], dtype=float)
                    reviewed_sector = np.asarray(
                        pred.sector_power_scale[interval], dtype=float
                    )
                    reviewed_stream = np.repeat(reviewed_sector, 4).reshape(57, 4)
                    matrix = matrices[matrix_indices[interval]]

                    amplitude = repair.mode_adjusted_amplitude(state, q)
                    gain = np.abs(amplitude) ** 2
                    (
                        leakage,
                        stream_power,
                        nominal_q0_stream_power,
                    ) = repair.stream_leakage_and_power_envelopes(
                        matrix,
                        q,
                        architecture.effective_steering_pol1,
                        architecture.effective_steering_pol2,
                    )
                    positive_q0 = nominal_q0_stream_power > 1e-15
                    if np.any(positive_q0):
                        interval_power_ratios = (
                            stream_power[positive_q0]
                            / nominal_q0_stream_power[positive_q0]
                        )
                        minimum_mode_adjusted_to_q0_power_ratio = min(
                            minimum_mode_adjusted_to_q0_power_ratio,
                            float(np.min(interval_power_ratios)),
                        )
                        maximum_mode_adjusted_to_q0_power_ratio = max(
                            maximum_mode_adjusted_to_q0_power_ratio,
                            float(np.max(interval_power_ratios)),
                        )
                    reviewed_audit = repair.exact_audit(
                        gain_user_sector_stream=gain,
                        stream_scale=reviewed_stream,
                        other_weighted_rate=state.other_weighted_rate,
                        active_user=state.active_user,
                        eligible_user=eligible,
                        floors=floors[interval],
                        serving_bs=data["serving"],
                        serving_stream=data["stream"],
                        protected_noise_w=float(data["noise"][4]),
                        protected_weight=float(data["weights"][4]),
                        long_kappa_second_sector=long_kappa[start:stop],
                        short_kappa_second_sector=short_kappa[start:stop],
                        leakage_sector_stream=leakage,
                        long_allowance_second=long_allowance[start:stop],
                        short_allowance_second=short_allowance[start:stop],
                        coupling_uplift_db=3.0,
                    )
                    baseline_formula_max_rate_error = max(
                        baseline_formula_max_rate_error,
                        float(
                            np.max(
                                np.abs(
                                    reviewed_audit.delivered_total_rate
                                    - pred.delivered_total_rate[interval]
                                )
                            )
                        ),
                    )
                    baseline_formula_max_long_error = max(
                        baseline_formula_max_long_error,
                        float(
                            np.max(
                                np.abs(
                                    reviewed_audit.long_ratio
                                    - pred.long_ratio[start:stop]
                                )
                            )
                        ),
                    )
                    baseline_formula_max_short_error = max(
                        baseline_formula_max_short_error,
                        float(
                            np.max(
                                np.abs(
                                    reviewed_audit.short_ratio
                                    - pred.short_ratio[start:stop]
                                )
                            )
                        ),
                    )

                    # Recompute the reviewed distributed fallback sequentially
                    # using the candidate-delivered moving-average state.  This
                    # is the deployable pre-repair action, not a replay of the
                    # original failed fallback trajectory.
                    local_started = time.perf_counter()
                    local_cost, _local_audit = build_local_cost_table(
                        state,
                        q,
                        current_average,
                        eligible,
                        floors[interval],
                        data["serving"],
                        data["stream"],
                        float(data["noise"][4]),
                        float(data["weights"][4]),
                        alpha,
                        0.001,
                        np.asarray(GRID_DB, dtype=float),
                    )
                    candidate_local_table_build_seconds[interval] = (
                        time.perf_counter() - local_started
                    )
                    sector_leakage = np.sum(leakage, axis=1)
                    envelope = (
                        10.0 ** (3.0 / 10.0)
                        * np.max(
                            long_kappa[start:stop]
                            * sector_leakage[None, :]
                            / long_allowance[start:stop, None],
                            axis=0,
                        )
                    )
                    (
                        _pre_backoff,
                        pre_sector,
                        pre_envelope_ratio,
                        _pre_price,
                        pre_feasible,
                    ) = candidate_allocator.solve(local_cost, envelope)
                    if not pre_feasible:
                        raise RuntimeError(
                            f"pass {slot} interval {interval}: candidate pre-repair "
                            "sector fallback infeasible despite exact mute endpoint"
                        )
                    pre_sector = np.asarray(pre_sector, dtype=float)
                    pre_stream = np.repeat(pre_sector, 4).reshape(57, 4)
                    candidate_pre_repair_sector[interval] = pre_sector
                    candidate_pre_repair_envelope_ratio[interval] = float(
                        pre_envelope_ratio
                    )
                    pre_audit = repair.exact_audit(
                        gain_user_sector_stream=gain,
                        stream_scale=pre_stream,
                        other_weighted_rate=state.other_weighted_rate,
                        active_user=state.active_user,
                        eligible_user=eligible,
                        floors=floors[interval],
                        serving_bs=data["serving"],
                        serving_stream=data["stream"],
                        protected_noise_w=float(data["noise"][4]),
                        protected_weight=float(data["weights"][4]),
                        long_kappa_second_sector=long_kappa[start:stop],
                        short_kappa_second_sector=short_kappa[start:stop],
                        leakage_sector_stream=leakage,
                        long_allowance_second=long_allowance[start:stop],
                        short_allowance_second=short_allowance[start:stop],
                        coupling_uplift_db=3.0,
                    )

                    reviewed_choice = None
                    reviewed_violating = np.flatnonzero(
                        reviewed_audit.floor_violation_mask
                    )
                    if len(reviewed_violating):
                        affected_seen.update(int(v) for v in reviewed_violating)
                        reviewed_choice = repair.repair_interval(
                            state=state,
                            matrices=matrix,
                            q_db=q,
                            baseline_sector_scale=reviewed_sector,
                            eligible_user=eligible,
                            floors=floors[interval],
                            serving_bs=data["serving"],
                            serving_stream=data["stream"],
                            protected_noise_w=float(data["noise"][4]),
                            protected_weight=float(data["weights"][4]),
                            steering_pol1=architecture.effective_steering_pol1,
                            steering_pol2=architecture.effective_steering_pol2,
                            long_kappa_second_sector=long_kappa[start:stop],
                            short_kappa_second_sector=short_kappa[start:stop],
                            long_allowance_second=long_allowance[start:stop],
                            short_allowance_second=short_allowance[start:stop],
                            coupling_uplift_db=3.0,
                            grid_backoff_db=GRID_DB,
                            grid_time_limit_s=float(args.grid_time_limit_s),
                        )

                    pre_hard_failure = bool(
                        pre_audit.floor_violation_count
                        or pre_audit.long_violation_seconds
                        or pre_audit.short_violation_seconds
                    )
                    candidate_choice = None
                    if pre_hard_failure:
                        if (
                            reviewed_choice is not None
                            and np.array_equal(pre_sector, reviewed_sector)
                        ):
                            candidate_choice = reviewed_choice
                        else:
                            candidate_choice = repair.repair_interval(
                                state=state,
                                matrices=matrix,
                                q_db=q,
                                baseline_sector_scale=pre_sector,
                                eligible_user=eligible,
                                floors=floors[interval],
                                serving_bs=data["serving"],
                                serving_stream=data["stream"],
                                protected_noise_w=float(data["noise"][4]),
                                protected_weight=float(data["weights"][4]),
                                steering_pol1=architecture.effective_steering_pol1,
                                steering_pol2=architecture.effective_steering_pol2,
                                long_kappa_second_sector=long_kappa[start:stop],
                                short_kappa_second_sector=short_kappa[start:stop],
                                long_allowance_second=long_allowance[start:stop],
                                short_allowance_second=short_allowance[start:stop],
                                coupling_uplift_db=3.0,
                                grid_backoff_db=GRID_DB,
                                grid_time_limit_s=float(args.grid_time_limit_s),
                            )
                        selected_stream = np.asarray(
                            candidate_choice.stream_scale, dtype=float
                        )
                        selected_audit = candidate_choice.exact_audit
                        selected_sector = np.asarray(
                            candidate_choice.sector_scale_equivalent, dtype=float
                        )
                        selected_class = candidate_choice.chosen_action_class
                    else:
                        selected_stream = pre_stream
                        selected_audit = pre_audit
                        selected_sector = pre_sector
                        selected_class = "BASELINE_NOOP"
                    action_counter[selected_class] += 1

                    # Enforce and report the practical sparse-distributed action
                    # restrictions independently of the optimizer status.
                    selected_choice = candidate_choice if pre_hard_failure else None
                    mutable = (
                        tuple(int(v) for v in selected_choice.mutable_sectors)
                        if selected_choice is not None
                        else tuple()
                    )
                    critical = (
                        tuple(int(v) for v in selected_choice.critical_serving_sectors)
                        if selected_choice is not None
                        else tuple()
                    )
                    external = (
                        tuple(int(v) for v in selected_choice.top_external_sectors)
                        if selected_choice is not None
                        else tuple()
                    )
                    eess_backoff = (
                        tuple(int(v) for v in selected_choice.top_eess_sectors)
                        if selected_choice is not None
                        else tuple()
                    )
                    scalar_backoff = tuple(sorted(set(external) | set(eess_backoff)))
                    violating_for_scope = (
                        np.flatnonzero(pre_audit.floor_violation_mask)
                        if selected_choice is not None
                        else np.zeros(0, dtype=np.int64)
                    )
                    allowed_external = 2 * len(violating_for_scope)
                    scope_ok = (
                        len(external) <= allowed_external
                        and len(eess_backoff) <= 2
                        and set(mutable)
                        == (set(critical) | set(external) | set(eess_backoff))
                        and set(critical)
                        == set(
                            int(data["serving"][user])
                            for user in violating_for_scope
                        )
                    )
                    if not scope_ok:
                        strict_local_scope_violation_intervals += 1
                        raise RuntimeError(
                            f"pass {slot} interval {interval}: strict local scope violated"
                        )
                    maximum_external_interferers_per_violating_user = max(
                        maximum_external_interferers_per_violating_user,
                        int(math.ceil(len(external) / max(len(violating_for_scope), 1))),
                    )
                    maximum_eess_backoff_sectors = max(
                        maximum_eess_backoff_sectors, len(eess_backoff)
                    )
                    maximum_mutable_sector_count = max(
                        maximum_mutable_sector_count, len(mutable)
                    )
                    immutable_sectors = sorted(set(range(57)) - set(mutable))
                    if immutable_sectors and not np.allclose(
                        selected_stream[immutable_sectors],
                        pre_stream[immutable_sectors],
                        rtol=0.0,
                        atol=1e-12,
                    ):
                        raise RuntimeError(
                            f"pass {slot} interval {interval}: nonmutable sector changed"
                        )
                    for sector in scalar_backoff:
                        if not np.allclose(
                            selected_stream[sector],
                            selected_stream[sector, 0],
                            rtol=0.0,
                            atol=1e-12,
                        ):
                            raise RuntimeError(
                                f"pass {slot} interval {interval}: external/EESS sector "
                                f"{sector} is not a scalar action"
                            )
                        if selected_stream[sector, 0] > pre_sector[sector] + 1e-12:
                            raise RuntimeError(
                                f"pass {slot} interval {interval}: external/EESS sector "
                                f"{sector} increased above reviewed fallback"
                            )
                    maximum_critical_q0_envelope_ratio = 0.0
                    maximum_critical_strict_post_mode_ratio = 0.0
                    interval_q0_headroom_used = False
                    if selected_class == "SPARSE_LOCAL_STREAM_POWER_REPAIR":
                        for sector in critical:
                            q0_envelope_power = float(
                                pre_sector[sector]
                                * np.sum(nominal_q0_stream_power[sector])
                            )
                            strict_post_mode_power = float(
                                pre_sector[sector] * np.sum(stream_power[sector])
                            )
                            selected_power = float(
                                np.sum(stream_power[sector] * selected_stream[sector])
                            )
                            q0_ratio = (
                                selected_power / q0_envelope_power
                                if q0_envelope_power > 0.0
                                else (0.0 if selected_power <= 1e-15 else math.inf)
                            )
                            strict_ratio = (
                                selected_power / strict_post_mode_power
                                if strict_post_mode_power > 0.0
                                else (0.0 if selected_power <= 1e-15 else math.inf)
                            )
                            maximum_critical_q0_envelope_ratio = max(
                                maximum_critical_q0_envelope_ratio, q0_ratio
                            )
                            maximum_critical_strict_post_mode_ratio = max(
                                maximum_critical_strict_post_mode_ratio, strict_ratio
                            )
                            maximum_q0_nominal_power_envelope_ratio = max(
                                maximum_q0_nominal_power_envelope_ratio, q0_ratio
                            )
                            maximum_strict_post_mode_baseline_power_ratio = max(
                                maximum_strict_post_mode_baseline_power_ratio,
                                strict_ratio,
                            )
                            tolerance = max(
                                1e-12, 1e-10 * max(q0_envelope_power, 1.0)
                            )
                            if selected_power > q0_envelope_power + tolerance:
                                raise RuntimeError(
                                    f"pass {slot} interval {interval}: q=0 nominal "
                                    f"critical-sector power envelope exceeded for "
                                    f"sector {sector}"
                                )
                            if selected_power > strict_post_mode_power + max(
                                1e-12, 1e-10 * max(strict_post_mode_power, 1.0)
                            ):
                                interval_q0_headroom_used = True
                        if interval_q0_headroom_used:
                            q0_headroom_used_intervals += 1
                    grid_scales = np.asarray(
                        [10.0 ** (-v / 10.0) for v in range(13)] + [0.0]
                    )
                    if selected_class == "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR":
                        for sector in mutable:
                            if not np.allclose(
                                selected_stream[sector],
                                selected_stream[sector, 0],
                                rtol=0.0,
                                atol=1e-12,
                            ) or float(np.min(np.abs(
                                grid_scales - selected_stream[sector, 0]
                            ))) > 1e-10:
                                raise RuntimeError(
                                    f"pass {slot} interval {interval}: local-grid action "
                                    f"for sector {sector} is outside the frozen grid"
                                )
                    changed_sector_mask = np.any(
                        np.abs(selected_stream - pre_stream) > 1e-10, axis=1
                    )
                    changed_sectors = np.flatnonzero(changed_sector_mask)
                    muted_sectors = np.flatnonzero(
                        np.all(selected_stream <= 1e-12, axis=1)
                    )
                    changed_streams = np.argwhere(
                        np.abs(selected_stream - pre_stream) > 1e-10
                    )
                    action_rows.append(
                        {
                            "pass_slot": slot,
                            "interval_index": interval,
                            "interval_seconds": int(interval_lengths[interval]),
                            "chosen_action_class": selected_class,
                            "pre_repair_floor_violation_count": int(
                                pre_audit.floor_violation_count
                            ),
                            "candidate_floor_violation_count": int(
                                selected_audit.floor_violation_count
                            ),
                            "candidate_long_violation_seconds": int(
                                selected_audit.long_violation_seconds
                            ),
                            "candidate_short_violation_seconds": int(
                                selected_audit.short_violation_seconds
                            ),
                            "mutable_sector_count": len(mutable),
                            "mutable_sectors": ";".join(str(v) for v in mutable),
                            "critical_serving_sectors": ";".join(
                                str(v) for v in critical
                            ),
                            "external_backoff_sectors": ";".join(
                                str(v) for v in external
                            ),
                            "eess_backoff_sectors": ";".join(
                                str(v) for v in eess_backoff
                            ),
                            "scalar_backoff_sectors": ";".join(
                                str(v) for v in scalar_backoff
                            ),
                            "strict_local_scope_gate": "PASS",
                            "changed_sector_count": int(len(changed_sectors)),
                            "changed_sectors": ";".join(
                                str(int(v)) for v in changed_sectors
                            ),
                            "changed_sector_equivalent_scales": ";".join(
                                f"{int(v)}:{float(selected_sector[v]):.17g}"
                                for v in changed_sectors
                            ),
                            "muted_sector_count": int(len(muted_sectors)),
                            "muted_sectors": ";".join(
                                str(int(v)) for v in muted_sectors
                            ),
                            "changed_stream_count": int(len(changed_streams)),
                            "changed_streams": ";".join(
                                f"{int(v[0])}:{int(v[1])}:{float(selected_stream[tuple(v)]):.17g}"
                                for v in changed_streams
                            ),
                            "maximum_critical_q0_nominal_power_envelope_ratio": float(
                                maximum_critical_q0_envelope_ratio
                            ),
                            "maximum_critical_strict_post_mode_baseline_power_ratio": float(
                                maximum_critical_strict_post_mode_ratio
                            ),
                            "q0_power_headroom_used": bool(
                                interval_q0_headroom_used
                            ),
                            "candidate_stream_scale_sha256": sha256_array(
                                selected_stream
                            ),
                        }
                    )

                    for residual_user in np.flatnonzero(
                        selected_audit.floor_violation_mask
                    ):
                        residual_meta = (
                            users.iloc[int(residual_user)].to_dict()
                            if int(residual_user) < len(users)
                            else {"user_index": int(residual_user)}
                        )
                        residual_floor = float(floors[interval, residual_user])
                        residual_rate = float(
                            selected_audit.delivered_total_rate[residual_user]
                        )
                        candidate_residual_rows.append(
                            {
                                "pass_slot": slot,
                                "interval_index": interval,
                                "interval_seconds": int(interval_lengths[interval]),
                                "user_index": int(residual_user),
                                "user_id": residual_meta.get(
                                    "user_id", str(int(residual_user))
                                ),
                                "floor_bps_hz": residual_floor,
                                "candidate_rate_bps_hz": residual_rate,
                                "margin_bps_hz": residual_rate - residual_floor,
                                "floor_ratio": residual_rate / residual_floor,
                                "normalized_shortfall": max(
                                    residual_floor - residual_rate, 0.0
                                ) / residual_floor,
                                "chosen_action_class": selected_class,
                                "strict_solver_status": (
                                    source_choice.strict_post_mode_sparse_stream.status
                                ),
                                "strict_solver_maximum_constraint_excess": (
                                    source_choice.strict_post_mode_sparse_stream.maximum_constraint_excess
                                ),
                            }
                        )

                    pre_violating = np.flatnonzero(pre_audit.floor_violation_mask)
                    diagnostic_users = sorted(
                        set(int(v) for v in reviewed_violating)
                        | set(int(v) for v in pre_violating)
                    )
                    if diagnostic_users:
                        mode_total, _mode_protected, _ = mode_case_rates(
                            repair,
                            state,
                            q,
                            np.ones((57, 4)),
                            data,
                        )
                        nominal_total, _nominal_protected, _ = mode_case_rates(
                            repair,
                            state,
                            np.zeros((57, 2)),
                            np.ones((57, 4)),
                            data,
                        )
                    for user in diagnostic_users:
                        source_choice = (
                            reviewed_choice
                            if user in set(int(v) for v in reviewed_violating)
                            and reviewed_choice is not None
                            else candidate_choice
                        )
                        if source_choice is None:
                            raise RuntimeError(
                                "diagnostic user has no feasibility certificate"
                            )
                        optimistic = repair.optimistic_single_user_upper_bound(
                            user=user,
                            gain_user_sector_stream=gain,
                            other_weighted_rate=state.other_weighted_rate,
                            serving_bs=data["serving"],
                            serving_stream=data["stream"],
                            protected_noise_w=float(data["noise"][4]),
                            protected_weight=float(data["weights"][4]),
                            long_kappa_second_sector=long_kappa[start:stop],
                            short_kappa_second_sector=short_kappa[start:stop],
                            leakage_sector_stream=leakage,
                            long_allowance_second=long_allowance[start:stop],
                            short_allowance_second=short_allowance[start:stop],
                            coupling_uplift_db=3.0,
                        )
                        root_class = classify_interval(
                            source_choice,
                            optimistic,
                            float(floors[interval, user]),
                        )
                        class_counter[root_class] += 1
                        reviewed_decomp = decompose_user_power(
                            gain,
                            reviewed_stream,
                            user,
                            data["serving"],
                            data["stream"],
                            float(data["noise"][4]),
                        )
                        pre_decomp = decompose_user_power(
                            gain,
                            pre_stream,
                            user,
                            data["serving"],
                            data["stream"],
                            float(data["noise"][4]),
                        )
                        candidate_decomp = decompose_user_power(
                            gain,
                            selected_stream,
                            user,
                            data["serving"],
                            data["stream"],
                            float(data["noise"][4]),
                        )
                        external_contribution = np.sum(
                            gain[user] * reviewed_stream, axis=1
                        )
                        external_contribution[int(data["serving"][user])] = -1.0
                        top_external = np.argsort(
                            -external_contribution, kind="stable"
                        )[:5]
                        user_meta = (
                            users.iloc[user].to_dict()
                            if user < len(users)
                            else {"user_index": user}
                        )
                        floor_value = float(floors[interval, user])
                        affected_rows.append(
                            {
                                "pass_slot": slot,
                                "interval_index": interval,
                                "interval_seconds": int(interval_lengths[interval]),
                                "user_index": user,
                                "user_id": user_meta.get("user_id", str(user)),
                                "serving_bs_index": int(data["serving"][user]),
                                "serving_stream_index": int(data["stream"][user]),
                                "was_reviewed_fallback_violation": bool(
                                    user in set(int(v) for v in reviewed_violating)
                                ),
                                "was_integrated_pre_repair_violation": bool(
                                    user in set(int(v) for v in pre_violating)
                                ),
                                "floor_bps_hz": floor_value,
                                "floor_branch": (
                                    "ABSOLUTE_0P1"
                                    if abs(floor_value - 0.1) <= 1e-12
                                    else "RELATIVE_0P9_CURRENT_LOAD_NOMINAL"
                                ),
                                "full_load_nominal_total_rate_bps_hz": float(
                                    full_state.nominal_total_rate[user]
                                ),
                                "current_load_nominal_total_rate_bps_hz": float(
                                    state.nominal_total_rate[user]
                                ),
                                "nominal_no_protection_rate_bps_hz": float(
                                    nominal_total[user]
                                ),
                                "mode_only_rate_bps_hz": float(mode_total[user]),
                                "reviewed_fallback_rate_bps_hz": float(
                                    reviewed_audit.delivered_total_rate[user]
                                ),
                                "integrated_pre_repair_rate_bps_hz": float(
                                    pre_audit.delivered_total_rate[user]
                                ),
                                "candidate_rate_bps_hz": float(
                                    selected_audit.delivered_total_rate[user]
                                ),
                                "reviewed_floor_ratio": float(
                                    reviewed_audit.delivered_total_rate[user]
                                    / floor_value
                                ),
                                "integrated_pre_repair_floor_ratio": float(
                                    pre_audit.delivered_total_rate[user] / floor_value
                                ),
                                "candidate_floor_ratio": float(
                                    selected_audit.delivered_total_rate[user]
                                    / floor_value
                                ),
                                "continuous_sector_status": source_choice.continuous_sector.status,
                                "continuous_sector_feasible": bool(
                                    source_choice.continuous_sector.feasible
                                ),
                                "global_frozen_grid_status": source_choice.frozen_grid_sector.status,
                                "global_frozen_grid_feasible": bool(
                                    source_choice.frozen_grid_sector.feasible
                                ),
                                "local_frozen_grid_status": source_choice.local_frozen_grid_sector.status,
                                "local_frozen_grid_feasible": bool(
                                    source_choice.local_frozen_grid_sector.feasible
                                ),
                                "strict_post_mode_sparse_stream_status": (
                                    source_choice.strict_post_mode_sparse_stream.status
                                ),
                                "strict_post_mode_sparse_stream_feasible": bool(
                                    source_choice.strict_post_mode_sparse_stream.feasible
                                ),
                                "q0_envelope_sparse_stream_status": (
                                    source_choice.q0_nominal_envelope_sparse_stream.status
                                ),
                                "q0_envelope_sparse_stream_feasible": bool(
                                    source_choice.q0_nominal_envelope_sparse_stream.feasible
                                ),
                                "deployable_sparse_stream_status": (
                                    source_choice.strict_post_mode_sparse_stream.status
                                ),
                                "deployable_sparse_stream_feasible": bool(
                                    source_choice.strict_post_mode_sparse_stream.feasible
                                ),
                                "global_stream_status": source_choice.global_stream_oracle.status,
                                "global_stream_feasible": bool(
                                    source_choice.global_stream_oracle.feasible
                                ),
                                "chosen_action_class": selected_class,
                                "root_cause_class": root_class,
                                "optimistic_single_user_rate_bps_hz": float(
                                    optimistic["optimistic_total_rate_bps_hz"]
                                ),
                                "optimistic_single_user_floor_feasible": bool(
                                    float(optimistic["optimistic_total_rate_bps_hz"])
                                    >= floor_value - 1e-12
                                ),
                                **{
                                    f"reviewed_{key}": value
                                    for key, value in reviewed_decomp.items()
                                },
                                **{
                                    f"integrated_pre_{key}": value
                                    for key, value in pre_decomp.items()
                                },
                                **{
                                    f"candidate_{key}": value
                                    for key, value in candidate_decomp.items()
                                },
                                "top_external_sector_indices": ";".join(
                                    str(int(v)) for v in top_external
                                ),
                                "top_external_contributions_w": ";".join(
                                    f"{float(external_contribution[v]):.17g}"
                                    for v in top_external
                                ),
                            }
                        )

                    if reviewed_choice is not None or candidate_choice is not None:
                        certificate_choice = (
                            candidate_choice
                            if candidate_choice is not None
                            else reviewed_choice
                        )
                        if certificate_choice.continuous_sector.status == "INFEASIBLE":
                            continuous_sector_proven_infeasible_intervals += 1
                        if certificate_choice.frozen_grid_sector.status.startswith(
                            "PROVEN_INFEASIBLE"
                        ):
                            global_frozen_proven_infeasible_intervals += 1
                        if selected_class == "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR":
                            local_frozen_repaired_intervals += 1
                        if selected_class == "SPARSE_LOCAL_STREAM_POWER_REPAIR":
                            local_stream_repaired_intervals += 1
                        strict_comparator = (
                            certificate_choice.strict_post_mode_sparse_stream
                        )
                        if strict_comparator.status == "INFEASIBLE":
                            strict_post_mode_stream_infeasible_intervals += 1
                            local_stream_proven_infeasible_intervals += 1
                        elif strict_comparator.status in {
                            "NO_CERTIFIED_WITNESS_AT_FIXED_RESERVE",
                            "NUMERICAL_CERTIFICATE_MARGIN_FAIL",
                        }:
                            strict_post_mode_stream_uncertified_intervals += 1
                        elif (
                            strict_comparator.feasible
                            and not strict_comparator.status.startswith("NOT_")
                        ):
                            strict_post_mode_stream_feasible_intervals += 1
                        if certificate_choice.global_stream_oracle.status == "INFEASIBLE":
                            global_stream_proven_infeasible_intervals += 1
                        if selected_class == "NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND":
                            unresolved_deployable_intervals += 1
                        interval_certificates.append(
                            {
                                "pass_slot": slot,
                                "interval_index": interval,
                                "interval_seconds": int(interval_lengths[interval]),
                                "reviewed_violating_users": reviewed_violating.tolist(),
                                "integrated_pre_repair_violating_users": pre_violating.tolist(),
                                "reviewed_floor_violation_count": int(
                                    reviewed_audit.floor_violation_count
                                ),
                                "integrated_pre_repair_floor_violation_count": int(
                                    pre_audit.floor_violation_count
                                ),
                                "chosen_status": certificate_choice.status,
                                "chosen_action_class": selected_class,
                                "mutable_sectors": list(
                                    certificate_choice.mutable_sectors
                                ),
                                "critical_serving_sectors": list(
                                    certificate_choice.critical_serving_sectors
                                ),
                                "top_external_sectors": list(
                                    certificate_choice.top_external_sectors
                                ),
                                "top_eess_sectors": list(
                                    certificate_choice.top_eess_sectors
                                ),
                                "strict_local_scope_gate": "PASS",
                                "continuous_sector": solver_record(
                                    certificate_choice.continuous_sector
                                ),
                                "global_frozen_grid_sector": solver_record(
                                    certificate_choice.frozen_grid_sector
                                ),
                                "local_frozen_grid_sector": solver_record(
                                    certificate_choice.local_frozen_grid_sector
                                ),
                                "selected_strict_post_mode_sparse_stream": solver_record(
                                    certificate_choice.strict_post_mode_sparse_stream
                                ),
                                "q0_nominal_envelope_sparse_stream_diagnostic": solver_record(
                                    certificate_choice.q0_nominal_envelope_sparse_stream
                                ),
                                "global_stream_oracle": solver_record(
                                    certificate_choice.global_stream_oracle
                                ),
                                "candidate_floor_violation_count": int(
                                    selected_audit.floor_violation_count
                                ),
                                "candidate_violating_users": np.flatnonzero(
                                    selected_audit.floor_violation_mask
                                ).tolist(),
                                "candidate_floor_margins_bps_hz": {
                                    str(int(user)): float(
                                        selected_audit.delivered_total_rate[user]
                                        - floors[interval, user]
                                    )
                                    for user in np.flatnonzero(
                                        selected_audit.floor_violation_mask
                                    )
                                },
                                "candidate_long_violation_seconds": int(
                                    selected_audit.long_violation_seconds
                                ),
                                "candidate_short_violation_seconds": int(
                                    selected_audit.short_violation_seconds
                                ),
                                "candidate_stream_scale_sha256": sha256_array(
                                    selected_stream
                                ),
                                "claim_boundary": certificate_choice.claim_boundary,
                            }
                        )

                    candidate_stream[interval] = selected_stream
                    candidate_sector_equiv[interval] = selected_sector
                    candidate_action_class[interval] = selected_class
                    candidate_total[interval] = selected_audit.delivered_total_rate
                    candidate_protected[interval] = (
                        selected_audit.delivered_protected_rate
                    )
                    candidate_long[start:stop] = selected_audit.long_ratio
                    candidate_short[start:stop] = selected_audit.short_ratio
                    count, shortfall, min_ratio, max_short = floor_metrics(
                        candidate_total[interval],
                        state.active_user,
                        eligible,
                        floors[interval],
                    )
                    candidate_floor_count[interval] = count
                    candidate_shortfall[interval] = shortfall
                    candidate_min_ratio[interval] = (
                        min_ratio if min_ratio is not None else math.nan
                    )
                    candidate_max_shortfall[interval] = max_short
                    current_average = (
                        (1.0 - alpha) * current_average
                        + alpha * candidate_total[interval]
                    )
                    candidate_average[interval] = current_average
                    if np.all(selected_stream <= 1e-12):
                        network_shutdown_intervals += 1

                candidate_floor_seconds = int(
                    np.sum(candidate_floor_count * interval_lengths)
                )
                candidate_floor_intervals = int(np.sum(candidate_floor_count))
                long_violations = int(np.sum(candidate_long > 1.0 + 1e-10))
                short_violations = int(np.sum(candidate_short > 1.0 + 1e-10))
                all_candidate_floor_seconds += candidate_floor_seconds
                all_candidate_floor_intervals += candidate_floor_intervals
                all_candidate_long_violations += long_violations
                all_candidate_short_violations += short_violations
                valid_ratios = candidate_min_ratio[np.isfinite(candidate_min_ratio)]
                candidate_rows.append(
                    {
                        "method_id": "candidate_v4_3_floor_feasibility_repair",
                        "pass_slot": slot,
                        "protected_sample_count": int(len(long_kappa)),
                        "interval_count": int(len(states)),
                        "long_violation_seconds": long_violations,
                        "short_violation_seconds": short_violations,
                        "eligible_floor_violation_user_intervals": candidate_floor_intervals,
                        "eligible_floor_violation_user_seconds": candidate_floor_seconds,
                        "minimum_active_eligible_floor_ratio": (
                            float(np.min(valid_ratios))
                            if len(valid_ratios)
                            else None
                        ),
                        "maximum_normalized_floor_shortfall": float(
                            np.max(candidate_max_shortfall)
                        ),
                        "total_normalized_floor_shortfall": float(
                            np.sum(candidate_shortfall)
                        ),
                        "maximum_long_ratio": float(np.max(candidate_long)),
                        "maximum_short_ratio": float(np.max(candidate_short)),
                        "network_wide_shutdown_intervals": int(
                            np.sum(np.all(candidate_stream <= 1e-12, axis=(1, 2)))
                        ),
                        "local_frozen_grid_repair_intervals": int(
                            np.sum(
                                candidate_action_class
                                == "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR"
                            )
                        ),
                        "local_stream_repair_intervals": int(
                            np.sum(
                                candidate_action_class
                                == "SPARSE_LOCAL_STREAM_POWER_REPAIR"
                            )
                        ),
                        "unresolved_intervals": int(
                            np.sum(
                                candidate_action_class
                                == "NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND"
                            )
                        ),
                    }
                )
                np.savez_compressed(
                    output / f"CANDIDATE_PASS_{slot}_TRACE.npz",
                    q_db=np.asarray(pred.q_db),
                    reviewed_sector_scale=np.asarray(pred.sector_power_scale),
                    integrated_pre_repair_sector_scale=candidate_pre_repair_sector,
                    integrated_pre_repair_envelope_ratio=(
                        candidate_pre_repair_envelope_ratio
                    ),
                    integrated_local_table_build_seconds=(
                        candidate_local_table_build_seconds
                    ),
                    candidate_stream_scale=candidate_stream,
                    candidate_sector_equivalent=candidate_sector_equiv,
                    candidate_total_rate=candidate_total,
                    candidate_protected_rate=candidate_protected,
                    candidate_moving_average_rate=candidate_average,
                    candidate_floor_count=candidate_floor_count,
                    candidate_normalized_shortfall=candidate_shortfall,
                    candidate_long_ratio=candidate_long,
                    candidate_short_ratio=candidate_short,
                    interval_lengths=interval_lengths,
                    action_class=candidate_action_class,
                )
                pass_extension_records.append(
                    {
                        "pass_slot": slot,
                        "physical_seconds": int(len(long_kappa)),
                        "interval_count": int(len(states)),
                        "final_interval_seconds": int(interval_lengths[-1]),
                        "phase_records": phase_records,
                        "all_physical_seconds_covered_once": bool(
                            int(np.sum(interval_lengths)) == len(long_kappa)
                        ),
                    }
                )

        all_methods = pd.DataFrame(all_method_rows)
        candidate_frame = pd.DataFrame(candidate_rows)
        affected_frame = pd.DataFrame(affected_rows)
        action_frame = pd.DataFrame(action_rows)
        residual_frame = pd.DataFrame(candidate_residual_rows)
        all_methods.to_csv(output / "ALL_METHOD_CELL_SUMMARY.csv", index=False)
        candidate_frame.to_csv(output / "CANDIDATE_CELL_SUMMARY.csv", index=False)
        action_frame.to_csv(output / "CANDIDATE_ACTION_INTERVALS.csv", index=False)
        residual_frame.to_csv(
            output / "CANDIDATE_RESIDUAL_FLOOR_VIOLATIONS.csv", index=False
        )
        affected_frame.to_csv(
            output / "AFFECTED_USER_INTERVAL_FEASIBILITY.csv", index=False
        )
        write_json(
            output / "INTERVAL_FEASIBILITY_CERTIFICATES.json",
            {"certificates": interval_certificates},
        )

        pred_rows = all_methods.loc[all_methods.method_id == PRED]
        reactive_rows = all_methods.loc[all_methods.method_id == REACTIVE]
        reproduction_pass = (
            predictive_reproduction_seconds == EXPECTED_PRED_FLOOR_SECONDS
            and predictive_reproduction_intervals == EXPECTED_PRED_FLOOR_INTERVALS
            and int(pred_rows.long_violation_seconds.sum()) == 0
            and int(pred_rows.short_violation_seconds.sum()) == 0
            and affected_seen == EXPECTED_AFFECTED
        )
        maximum_candidate_normalized_shortfall = (
            float(candidate_frame.maximum_normalized_floor_shortfall.max())
            if len(candidate_frame)
            else 0.0
        )
        formula_pass = (
            baseline_formula_max_rate_error <= 2e-6
            and baseline_formula_max_long_error <= 2e-10
            and baseline_formula_max_short_error <= 2e-10
        )
        candidate_pass = (
            all_candidate_floor_seconds == 0
            and all_candidate_floor_intervals == 0
            and all_candidate_long_violations == 0
            and all_candidate_short_violations == 0
            and network_shutdown_intervals == 0
            and strict_local_scope_violation_intervals == 0
            and maximum_external_interferers_per_violating_user <= 2
            and maximum_eess_backoff_sectors <= 2
            and maximum_strict_post_mode_baseline_power_ratio <= 1.0 + 1e-10
            and q0_headroom_used_intervals == 0
            and strict_post_mode_stream_uncertified_intervals == 0
        )
        reactive_safety_pass = (
            int(reactive_rows.long_violation_seconds.sum()) == 0
            and int(reactive_rows.short_violation_seconds.sum()) == 0
        )

        root_summary: dict[str, Any] = {}
        if len(affected_frame):
            for user_id, frame in affected_frame.groupby("user_id", sort=True):
                root_summary[str(user_id)] = {
                    "violating_interval_count": int(len(frame)),
                    "minimum_reviewed_floor_ratio": float(
                        frame.reviewed_floor_ratio.min()
                    ),
                    "minimum_candidate_floor_ratio": float(
                        frame.candidate_floor_ratio.min()
                    ),
                    "floor_branches": sorted(set(frame.floor_branch.astype(str))),
                    "root_cause_classes": dict(
                        Counter(frame.root_cause_class.astype(str))
                    ),
                    "global_frozen_grid_feasible_intervals": int(
                        frame.global_frozen_grid_feasible.sum()
                    ),
                    "local_frozen_grid_feasible_intervals": int(
                        frame.local_frozen_grid_feasible.sum()
                    ),
                    "strict_post_mode_sparse_stream_feasible_intervals": int(
                        frame.strict_post_mode_sparse_stream_feasible.sum()
                    ),
                    "q0_envelope_sparse_stream_feasible_intervals": int(
                        frame.q0_envelope_sparse_stream_feasible.sum()
                    ),
                    "deployable_sparse_stream_feasible_intervals": int(
                        frame.deployable_sparse_stream_feasible.sum()
                    ),
                    "global_stream_feasible_intervals": int(
                        frame.global_stream_feasible.sum()
                    ),
                    "minimum_optimistic_single_user_rate_bps_hz": float(
                        frame.optimistic_single_user_rate_bps_hz.min()
                    ),
                }

        floor_audit = {
            "status": "PASS_FROZEN_FLOOR_DEFINITION_REPRODUCED",
            "eligibility": (
                "full_load_nominal_total_rate >= 0.1 bit/s/Hz"
            ),
            "eligible_user_count": int(eligible.sum()),
            "active_floor": (
                "max(0.1, 0.9 * current_load_nominal_total_rate)"
            ),
            "comparison_tolerance": 1e-12,
            "tolerance_changed": False,
            "policy_changed": False,
            "solver_side_constraint_reserve": repair.SOLVER_CONSTRAINT_RESERVE,
            "scientific_tolerance_widened": False,
        }
        extension_audit = {
            "status": "PASS_VARIABLE_PASS_EXTENSION_COVERAGE",
            "passes": pass_extension_records,
            "pass_count": 5,
            "all_passes_cover_every_physical_second": bool(
                all(v["all_physical_seconds_covered_once"] for v in pass_extension_records)
            ),
        }
        write_json(output / "FLOOR_DEFINITION_AUDIT.json", floor_audit)
        write_json(output / "VARIABLE_PASS_EXTENSION_AUDIT.json", extension_audit)

        if candidate_pass and reproduction_pass and formula_pass and reactive_safety_pass:
            candidate_status = (
                "PASS_EXCLUDED_SEED43999_CANDIDATE_V4_3_ALL5_FLOOR_EESS_AND_STRICT_POWER_GATES"
            )
            next_gate = (
                "INDEPENDENT_REVIEW_THEN_EXCLUDED_H100_DEPLOYMENT_SMOKE"
            )
            exit_code = 0
        elif not reproduction_pass or not formula_pass:
            candidate_status = "FAIL_SOURCE_OR_FORMULA_REPRODUCTION_MISMATCH"
            next_gate = "DIAGNOSE_SOURCE_BINDING_OR_EXACT_FORMULA_MISMATCH"
            exit_code = 50
        else:
            candidate_status = (
                "FAIL_OR_UNRESOLVED_EXCLUDED_SEED43999_CANDIDATE_V4_3_REVIEW_REQUIRED"
            )
            if (
                all_candidate_long_violations == 0
                and all_candidate_short_violations == 0
                and maximum_candidate_normalized_shortfall <= 1e-7
            ):
                next_gate = (
                    "REVIEW_NUMERICAL_CERTIFICATES_AND_RESIDUAL_USER_MARGINS"
                )
            else:
                next_gate = (
                    "REVIEW_INTERVAL_CERTIFICATES_AND_CONSIDER_PROTECTED_"
                    "SUBBAND_SCHEDULING_REASSIGNMENT_OR_PREREGISTERED_"
                    "ADMISSION_POLICY"
                )
            exit_code = 42

        verdict = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": candidate_status,
            "source_supported_facts": {
                "excluded_seed": 43999,
                "source_commit": args.source_commit,
                "channel_record_sha256": actual_record_sha,
                "frequency_response_sha256_array_bytes": actual_array_sha,
                "channel_reused": True,
                "h100_channel_regenerated": False,
                "pass_count": 5,
                "reviewed_method_count": 8,
                "reviewed_predictive_floor_violation_user_seconds": (
                    predictive_reproduction_seconds
                ),
                "reviewed_predictive_floor_violation_user_intervals": (
                    predictive_reproduction_intervals
                ),
                "reviewed_predictive_long_violation_seconds": int(
                    pred_rows.long_violation_seconds.sum()
                ),
                "reviewed_predictive_short_violation_seconds": int(
                    pred_rows.short_violation_seconds.sum()
                ),
            },
            "candidate_results": {
                "floor_violation_user_seconds": all_candidate_floor_seconds,
                "floor_violation_user_intervals": all_candidate_floor_intervals,
                "long_violation_seconds": all_candidate_long_violations,
                "short_violation_seconds": all_candidate_short_violations,
                "network_wide_shutdown_intervals": network_shutdown_intervals,
                "continuous_sector_proven_infeasible_intervals": (
                    continuous_sector_proven_infeasible_intervals
                ),
                "global_frozen_grid_proven_infeasible_intervals": (
                    global_frozen_proven_infeasible_intervals
                ),
                "local_frozen_grid_repaired_intervals": (
                    local_frozen_repaired_intervals
                ),
                "local_stream_power_repaired_intervals": (
                    local_stream_repaired_intervals
                ),
                "local_stream_power_proven_infeasible_intervals": (
                    local_stream_proven_infeasible_intervals
                ),
                "global_stream_proven_infeasible_intervals": (
                    global_stream_proven_infeasible_intervals
                ),
                "unresolved_deployable_intervals": (
                    unresolved_deployable_intervals
                ),
                "strict_local_scope_violation_intervals": (
                    strict_local_scope_violation_intervals
                ),
                "strict_post_mode_stream_feasible_intervals": (
                    strict_post_mode_stream_feasible_intervals
                ),
                "strict_post_mode_stream_infeasible_intervals": (
                    strict_post_mode_stream_infeasible_intervals
                ),
                "strict_post_mode_stream_uncertified_intervals": (
                    strict_post_mode_stream_uncertified_intervals
                ),
                "solver_constraint_reserve": repair.SOLVER_CONSTRAINT_RESERVE,
                "solver_primal_feasibility_tolerance": (
                    repair.SOLVER_PRIMAL_FEASIBILITY_TOLERANCE
                ),
                "solver_dual_feasibility_tolerance": (
                    repair.SOLVER_DUAL_FEASIBILITY_TOLERANCE
                ),
                "maximum_candidate_normalized_shortfall": (
                    maximum_candidate_normalized_shortfall
                ),
                "q0_power_headroom_used_intervals": q0_headroom_used_intervals,
                "maximum_q0_nominal_power_envelope_ratio": (
                    maximum_q0_nominal_power_envelope_ratio
                ),
                "maximum_strict_post_mode_baseline_power_ratio": (
                    maximum_strict_post_mode_baseline_power_ratio
                ),
                "minimum_mode_adjusted_to_q0_power_ratio": (
                    minimum_mode_adjusted_to_q0_power_ratio
                    if math.isfinite(minimum_mode_adjusted_to_q0_power_ratio)
                    else None
                ),
                "maximum_mode_adjusted_to_q0_power_ratio": (
                    maximum_mode_adjusted_to_q0_power_ratio
                ),
                "maximum_external_interferers_per_violating_user": (
                    maximum_external_interferers_per_violating_user
                ),
                "maximum_eess_backoff_sectors": maximum_eess_backoff_sectors,
                "maximum_mutable_sector_count": maximum_mutable_sector_count,
                "action_class_counts": dict(action_counter),
                "root_cause_class_counts": dict(class_counter),
            },
            "scientific_inference": {
                "reviewed_fallback_defect": (
                    "local served-user cost tables and an incumbent-only scalar "
                    "price do not enforce coupled network-wide floors"
                ),
                "root_cause_by_user": root_summary,
                "preferred_repair": (
                    "hard EESS and floor feasibility first; exact frozen sector "
                    "grid when feasible; otherwise actual post-mode serving-stream "
                    "power redistribution bounded by the stricter reviewed scalar "
                    "times the actual post-mode sector-power baseline, plus at "
                    "most two external interferers per violated user and at most two "
                    "EESS-contributor backoffs; minimum "
                    "deviation is secondary and sum rate is not primary"
                ),
            },
            "assumptions_requiring_validation": {
                "local_stream_power_update_latency_and_signalling": True,
                "fixed_rzf_direction_validity_during_stream_reweighting": True,
                "q0_nominal_power_envelope_maps_to_available_conducted_power": False,
                "q0_nominal_power_envelope_deployed": False,
                "hardware_calibration": False,
                "regulatory_compliance_claimed": False,
            },
            "reproduction_gates": {
                "reviewed_seed43999_reproduced": reproduction_pass,
                "candidate_formula_matches_reviewed_baseline": formula_pass,
                "maximum_total_rate_formula_error": baseline_formula_max_rate_error,
                "maximum_long_ratio_formula_error": baseline_formula_max_long_error,
                "maximum_short_ratio_formula_error": baseline_formula_max_short_error,
                "reactive_same_fallback_zero_eess_violations": reactive_safety_pass,
                "strict_post_mode_selected_power_gate": bool(
                    maximum_strict_post_mode_baseline_power_ratio
                    <= 1.0 + 1e-10
                ),
                "q0_envelope_deployable_actions": 0,
            },
            "confirmatory_campaign_authorized": False,
            "paper_result": False,
            "claim_boundary": (
                "EXCLUDED_SEED_DIAGNOSTIC_NOT_CONFIRMATORY_NOT_CALIBRATION_"
                "NOT_REGULATORY_COMPLIANCE"
            ),
            "next_gate": next_gate,
            "runtime_seconds": time.perf_counter() - started,
        }
        write_json(output / "SCIENTIFIC_VERDICT.json", verdict)
        status_values = {
            "CANDIDATE_STATUS": candidate_status,
            "SCIENTIFIC_SCRIPT_EXIT_CODE": exit_code,
            "CANDIDATE_LONG_VIOLATION_SECONDS": all_candidate_long_violations,
            "CANDIDATE_SHORT_VIOLATION_SECONDS": all_candidate_short_violations,
            "CANDIDATE_FLOOR_VIOLATION_USER_SECONDS": all_candidate_floor_seconds,
            "CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS": all_candidate_floor_intervals,
            "NETWORK_WIDE_SHUTDOWN_INTERVALS": network_shutdown_intervals,
            "CONTINUOUS_SECTOR_PROVEN_INFEASIBLE_INTERVALS": (
                continuous_sector_proven_infeasible_intervals
            ),
            "GLOBAL_FROZEN_GRID_PROVEN_INFEASIBLE_INTERVALS": (
                global_frozen_proven_infeasible_intervals
            ),
            "LOCAL_FROZEN_GRID_REPAIRED_INTERVALS": (
                local_frozen_repaired_intervals
            ),
            "LOCAL_STREAM_POWER_REPAIRED_INTERVALS": (
                local_stream_repaired_intervals
            ),
            "LOCAL_STREAM_POWER_PROVEN_INFEASIBLE_INTERVALS": (
                local_stream_proven_infeasible_intervals
            ),
            "GLOBAL_STREAM_PROVEN_INFEASIBLE_INTERVALS": (
                global_stream_proven_infeasible_intervals
            ),
            "UNRESOLVED_DEPLOYABLE_INTERVALS": unresolved_deployable_intervals,
            "STRICT_LOCAL_SCOPE_GATE": (
                "PASS" if strict_local_scope_violation_intervals == 0 else "FAIL"
            ),
            "STRICT_LOCAL_SCOPE_VIOLATION_INTERVALS": (
                strict_local_scope_violation_intervals
            ),
            "MAX_EXTERNAL_INTERFERERS_PER_VIOLATING_USER": (
                maximum_external_interferers_per_violating_user
            ),
            "MAX_EESS_BACKOFF_SECTORS": maximum_eess_backoff_sectors,
            "MAX_MUTABLE_SECTOR_COUNT": maximum_mutable_sector_count,
            "STRICT_POST_MODE_SELECTED_POWER_GATE": (
                "PASS"
                if maximum_strict_post_mode_baseline_power_ratio <= 1.0 + 1e-10
                else "FAIL"
            ),
            "Q0_ENVELOPE_DEPLOYABLE_ACTIONS": 0,
            "SOLVER_CONSTRAINT_RESERVE": (
                f"{repair.SOLVER_CONSTRAINT_RESERVE:.17g}"
            ),
            "SOLVER_PRIMAL_FEASIBILITY_TOLERANCE": (
                f"{repair.SOLVER_PRIMAL_FEASIBILITY_TOLERANCE:.17g}"
            ),
            "SOLVER_DUAL_FEASIBILITY_TOLERANCE": (
                f"{repair.SOLVER_DUAL_FEASIBILITY_TOLERANCE:.17g}"
            ),
            "MAXIMUM_CANDIDATE_NORMALIZED_FLOOR_SHORTFALL": (
                f"{maximum_candidate_normalized_shortfall:.17g}"
            ),
            "CANDIDATE_RESIDUAL_USER_COUNT": int(
                residual_frame.user_index.nunique() if len(residual_frame) else 0
            ),
            "MAXIMUM_Q0_NOMINAL_POWER_ENVELOPE_RATIO": (
                f"{maximum_q0_nominal_power_envelope_ratio:.17g}"
            ),
            "MAXIMUM_STRICT_POST_MODE_BASELINE_POWER_RATIO": (
                f"{maximum_strict_post_mode_baseline_power_ratio:.17g}"
            ),
            "Q0_HEADROOM_USED_INTERVALS": q0_headroom_used_intervals,
            "STRICT_POST_MODE_STREAM_FEASIBLE_INTERVALS": (
                strict_post_mode_stream_feasible_intervals
            ),
            "STRICT_POST_MODE_STREAM_INFEASIBLE_INTERVALS": (
                strict_post_mode_stream_infeasible_intervals
            ),
            "STRICT_POST_MODE_STREAM_UNCERTIFIED_INTERVALS": (
                strict_post_mode_stream_uncertified_intervals
            ),
            "MINIMUM_MODE_ADJUSTED_TO_Q0_POWER_RATIO": (
                f"{minimum_mode_adjusted_to_q0_power_ratio:.17g}"
                if math.isfinite(minimum_mode_adjusted_to_q0_power_ratio)
                else "NA"
            ),
            "MAXIMUM_MODE_ADJUSTED_TO_Q0_POWER_RATIO": (
                f"{maximum_mode_adjusted_to_q0_power_ratio:.17g}"
            ),
            "PREDICTIVE_REPRODUCTION_USER_SECONDS": predictive_reproduction_seconds,
            "PREDICTIVE_REPRODUCTION_USER_INTERVALS": predictive_reproduction_intervals,
            "CHANNEL_RECORD_SHA256": actual_record_sha,
            "FREQUENCY_RESPONSE_ARRAY_SHA256": actual_array_sha,
            "CONFIRMATORY_CAMPAIGN_AUTHORIZED": "NO",
            "NEXT_GATE": next_gate,
        }
        write_status(output / "RUN_STATUS.env", status_values)
        make_manifest(output)

        for key, value in status_values.items():
            print(f"{key}={value}")
        return exit_code
    except Exception as exc:
        error = {
            "status": "FATAL_DIAGNOSTIC_ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "confirmatory_campaign_authorized": False,
        }
        write_json(output / "FATAL_ERROR.json", error)
        status_values = {
            "CANDIDATE_STATUS": "FATAL_DIAGNOSTIC_ERROR",
            "SCIENTIFIC_SCRIPT_EXIT_CODE": 90,
            "ERROR_TYPE": type(exc).__name__,
            "CONFIRMATORY_CAMPAIGN_AUTHORIZED": "NO",
            "NEXT_GATE": "DIAGNOSE_FATAL_CANDIDATE_V4_3_ERROR",
        }
        write_status(output / "RUN_STATUS.env", status_values)
        make_manifest(output)
        print(traceback.format_exc(), file=sys.stderr)
        for key, value in status_values.items():
            print(f"{key}={value}")
        return 90


if __name__ == "__main__":
    raise SystemExit(main())
