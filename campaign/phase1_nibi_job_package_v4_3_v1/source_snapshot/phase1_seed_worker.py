#!/usr/bin/env python3
"""Generate one campaign channel seed and evaluate all five passes and nine frozen method outputs.

The worker is execution-locked by an external authorization token. It generates
one cellular channel/topology realization, derives the generic 64-RF-chain
architecture once, and reuses that realization for all protected passes and all
methods.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "channel_generator"))

from fr3_cbf.dual_criterion_controller import interval_reduce
from fr3_cbf.online_pf_load_transition import (
    build_rotating_load_schedule,
    exponential_average_alpha,
)
from fr3_cbf.phase1_job_runtime import run_phase1_methods, summarize_method
from fr3_cbf.practical_architecture_mapping import (
    build_architecture,
    effective_channel,
    recompute_architecture_load_state,
)
from fr3_cbf.candidate_v4_3_campaign import (
    CANDIDATE_METHOD_ID,
    run_candidate_v4_3,
)
from authorization_guard import FULL_STAGE, SMOKE_STAGE, require_authorization

METHOD_IDS = [
    "candidate_v4_3_floor_feasibility_repair",
    "robust_predictive_constrained_pf_with_sector_selective_fallback",
    "static_robust_constrained_pf_with_sector_selective_fallback",
    "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
    "delayed_myopic_constrained_pf_unshielded",
    "virtual_queue_unshielded",
    "uniform_protected_tone_backoff",
    "hard_spatial_null_or_exact_mute",
    "common_scale_instantaneous_noncausal_reference",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_array(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )



def power_noise(cfg: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    weights = np.asarray(cfg["frequency_weights"], dtype=np.float64)
    total_power_w = 10.0 ** (
        (float(cfg["conducted_power_dbm_per_100mhz"]) - 30.0) / 10.0
    )
    noise_total_dbm = (
        float(cfg["thermal_noise_density_dbm_per_hz"])
        + 10.0 * math.log10(float(cfg["total_bandwidth_hz"]))
        + float(cfg["noise_figure_db"])
    )
    noise_total_w = 10.0 ** ((noise_total_dbm - 30.0) / 10.0)
    return total_power_w * weights, noise_total_w * weights, weights


def generate_channel(seed: int, output: Path) -> dict[str, object]:
    # Heavy GPU dependencies are imported lazily so package review and --help
    # remain possible on a CPU-only local workstation.
    import torch
    import run_full_topology_export as channel_exporter

    cfg = json.loads(
        (ROOT / "channel_generator/export_config_base.json").read_text(
            encoding="utf-8"
        )
    )
    cfg["user_seed"] = 2 * int(seed)
    cfg["channel_seed"] = 2 * int(seed) + 1

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is not visible")
    device = "cuda:0"
    gpu_name = torch.cuda.get_device_name(0)
    gpu_memory = torch.cuda.get_device_properties(0).total_memory
    if "H100" not in gpu_name or gpu_memory < 75 * 1024**3:
        raise RuntimeError(
            f"phase-1 seed generation requires H100 80 GB-class GPU: "
            f"{gpu_name}, {gpu_memory / 1024**3:.2f} GiB"
        )

    (
        bs,
        ut,
        bs_loc,
        bs_ori,
        ut_loc,
        ut_ori,
        ut_vel,
        in_state,
        serving,
        stream,
    ) = channel_exporter.build_topology(cfg, device)
    topology = (ut_loc, bs_loc, ut_ori, bs_ori, ut_vel, in_state)
    bs_array, ut_array = channel_exporter.make_arrays(cfg, device)
    frame = channel_exporter.verify_port_and_frame_inputs(cfg, bs_array)
    model = channel_exporter.make_model(cfg, bs_array, ut_array, device)
    h_gpu, channel_record = channel_exporter.generate_full_channel(
        cfg, model, topology, device
    )

    h = np.transpose(
        h_gpu.detach().cpu().numpy(), (3, 0, 1, 2)
    ).astype(np.complex64)
    steering1 = []
    steering2 = []
    for _, row in bs.iterrows():
        reference = frame.loc[row["sector_id"]]
        direction = [
            float(reference["local_direction_x"]),
            float(reference["local_direction_y"]),
            float(reference["local_direction_z"]),
        ]
        a1, a2 = channel_exporter.steering_modes(
            bs_array,
            direction,
            float(cfg["carrier_frequency_hz"]),
            device,
        )
        steering1.append(a1.detach().cpu().numpy())
        steering2.append(a2.detach().cpu().numpy())
    steering1 = np.asarray(steering1, dtype=np.complex64)
    steering2 = np.asarray(steering2, dtype=np.complex64)

    output.mkdir(parents=True, exist_ok=True)
    np.save(output / "frequency_response.npy", h, allow_pickle=False)
    np.save(
        output / "serving_bs_index.npy",
        serving.astype(np.int64),
        allow_pickle=False,
    )
    np.save(
        output / "serving_stream_index.npy",
        stream.astype(np.int64),
        allow_pickle=False,
    )
    np.save(
        output / "protected_steering_pol1.npy",
        steering1,
        allow_pickle=False,
    )
    np.save(
        output / "protected_steering_pol2.npy",
        steering2,
        allow_pickle=False,
    )
    bs.to_csv(output / "SECTOR_TOPOLOGY.csv", index=False)
    ut.to_csv(output / "USER_TOPOLOGY.csv", index=False)

    power, noise, weights = power_noise(cfg)
    np.save(
        output / "transmit_power_by_frequency_w.npy",
        power,
        allow_pickle=False,
    )
    np.save(
        output / "noise_power_by_frequency_w.npy",
        noise,
        allow_pickle=False,
    )
    np.save(output / "frequency_weights.npy", weights, allow_pickle=False)

    files = {}
    for path in sorted(output.iterdir()):
        if path.is_file():
            files[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    record = {
        "schema_version": 1,
        "campaign_seed": int(seed),
        "user_seed": int(cfg["user_seed"]),
        "channel_seed": int(cfg["channel_seed"]),
        "gpu_name": gpu_name,
        "gpu_total_memory_bytes": int(gpu_memory),
        "frequency_response_sha256_array_bytes": sha256_array(h),
        "channel_generation": channel_record,
        "files": files,
    }
    write_json(output / "CHANNEL_RECORD.json", record)

    del h_gpu, model, topology, bs_array, ut_array
    torch.cuda.empty_cache()
    return record


def load_channel(channel: Path):
    required = [
        "frequency_response.npy",
        "serving_bs_index.npy",
        "serving_stream_index.npy",
        "protected_steering_pol1.npy",
        "protected_steering_pol2.npy",
        "transmit_power_by_frequency_w.npy",
        "noise_power_by_frequency_w.npy",
        "frequency_weights.npy",
        "USER_TOPOLOGY.csv",
        "SECTOR_TOPOLOGY.csv",
        "CHANNEL_RECORD.json",
    ]
    for name in required:
        if not (channel / name).is_file():
            raise FileNotFoundError(channel / name)
    return {
        "h": np.load(channel / "frequency_response.npy", mmap_mode="r"),
        "serving": np.load(channel / "serving_bs_index.npy"),
        "stream": np.load(channel / "serving_stream_index.npy"),
        "steering1": np.load(channel / "protected_steering_pol1.npy"),
        "steering2": np.load(channel / "protected_steering_pol2.npy"),
        "power": np.load(channel / "transmit_power_by_frequency_w.npy"),
        "noise": np.load(channel / "noise_power_by_frequency_w.npy"),
        "weights": np.load(channel / "frequency_weights.npy"),
        "users": pd.read_csv(channel / "USER_TOPOLOGY.csv"),
        "sectors": pd.read_csv(channel / "SECTOR_TOPOLOGY.csv").sort_values(
            "bs_index"
        ),
        "record": json.loads(
            (channel / "CHANNEL_RECORD.json").read_text(encoding="utf-8")
        ),
    }


def extract_pass(slot: int, destination: Path) -> Path:
    archive = (
        ROOT
        / "input/protected_pass_records"
        / f"FR3_PROTECTED_PASS_SLOT_{slot}.zip"
    )
    if not archive.is_file():
        raise FileNotFoundError(archive)
    target = destination / f"slot_{slot}"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise RuntimeError(f"pass archive {slot} is corrupt")
        bundle.extractall(target)
    return target


def create_states(
    data: dict,
    contract: dict,
    pass_lengths: list[int],
):
    port_table = pd.read_csv(
        ROOT / "channel_generator/input/SIONNA_8X8_DUAL_PORT_ORDER.csv"
    )
    primary = contract["primary_scenario"]
    architecture = build_architecture(
        architecture_id=primary["architecture_id"],
        rf_chains=int(primary["rf_chains"]),
        analog_phase_bits=int(primary["analog_phase_bits"]),
        port_table=port_table,
        user_table=data["users"],
        sector_table=data["sectors"],
        steering_pol1=data["steering1"],
        steering_pol2=data["steering2"],
        carrier_frequency_hz=8.15e9,
    )
    h_effective = effective_channel(data["h"], architecture)
    full_state, _matrix, full_audit = recompute_architecture_load_state(
        h_effective,
        np.ones(len(data["serving"]), dtype=bool),
        data["serving"],
        data["stream"],
        data["power"],
        data["noise"],
        data["weights"],
        4,
        architecture.effective_steering_pol1,
        architecture.effective_steering_pol2,
    )

    load = primary["load_schedule"]
    schedules = {}
    all_masks = {}
    for slot, seconds in enumerate(pass_lengths):
        interval_count = math.ceil(int(seconds) / 5)
        schedule, phase_records = build_rotating_load_schedule(
            data["serving"],
            data["stream"],
            interval_count,
            load["declared_phase_lengths_intervals"],
            load["active_streams_per_sector"],
        )
        schedules[slot] = (schedule, phase_records)
        for mask in schedule:
            all_masks.setdefault(mask.tobytes(), mask.copy())

    state_cache = {}
    for key, mask in all_masks.items():
        state_cache[key] = recompute_architecture_load_state(
            h_effective,
            mask,
            data["serving"],
            data["stream"],
            data["power"],
            data["noise"],
            data["weights"],
            4,
            architecture.effective_steering_pol1,
            architecture.effective_steering_pol2,
        )

    return architecture, h_effective, full_state, full_audit, schedules, state_cache


def pass_evaluation(
    slot: int,
    pass_root: Path,
    data: dict,
    contract: dict,
    architecture,
    full_state,
    schedule_info,
    state_cache,
    output: Path,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    schedule, phase_records = schedule_info
    states = []
    matrices = []
    matrix_indices = []
    unique_keys = []
    for mask in schedule:
        key = mask.tobytes()
        state, matrix, _audit = state_cache[key]
        states.append(state)
        if key not in unique_keys:
            unique_keys.append(key)
        matrix_indices.append(unique_keys.index(key))
    matrices = [state_cache[key][1] for key in unique_keys]

    long_kappa = np.load(pass_root / "kappa_long_multiple.npy")
    short_kappa = np.load(pass_root / "kappa_short_multiple.npy")
    long_allowance = np.load(pass_root / "allowance_long_exact_w.npy")
    short_allowance = np.load(pass_root / "allowance_short_exact_w.npy")
    if len(states) != math.ceil(len(long_kappa) / 5):
        raise RuntimeError(f"pass {slot}: state/interval count mismatch")

    kappa_interval, interval_lengths = interval_reduce(long_kappa, 5, "max")
    long_contribution = np.asarray(
        [
            kappa_interval[index, :, None]
            * states[index].mode_leakage_w
            for index in range(len(states))
        ],
        dtype=np.float64,
    )

    primary = contract["primary_scenario"]
    fairness = primary["fairness"]
    eligible = (
        np.asarray(full_state.nominal_total_rate, dtype=float)
        >= float(fairness["serviceability_threshold_bps_hz"])
    )
    floors = np.zeros((len(states), len(data["serving"])), dtype=float)
    for index, state in enumerate(states):
        active = np.asarray(state.active_user, dtype=bool) & eligible
        floors[index, active] = np.maximum(
            float(fairness["absolute_total_band_floor_bps_hz"]),
            float(fairness["relative_current_load_floor_fraction"])
            * np.asarray(state.nominal_total_rate)[active],
        )

    alpha = exponential_average_alpha(
        float(primary["timing"]["update_interval_s"]),
        float(primary["moving_average_pf"]["time_constant_s"]),
    )
    started = time.perf_counter()
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
        update_interval_s=5,
        delay_intervals=1,
        slew_db=3.0,
        uplift_db=3.0,
        cap_db=65.0,
        epsilon=0.001,
        virtual_queue_gain=1.0,
    )
    candidate_run, candidate_diagnostics = run_candidate_v4_3(
        states=states,
        matrices=matrices,
        matrix_indices=matrix_indices,
        predictive_run=methods[
            "robust_predictive_constrained_pf_with_sector_selective_fallback"
        ],
        long_kappa=long_kappa,
        short_kappa=short_kappa,
        long_allowance=long_allowance,
        short_allowance=short_allowance,
        interval_lengths=interval_lengths,
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
        update_interval_s=5,
        coupling_uplift_db=3.0,
        epsilon=0.001,
        grid_time_limit_s=45.0,
    )
    methods[CANDIDATE_METHOD_ID] = candidate_run
    elapsed = time.perf_counter() - started

    rows = []
    traces = {}
    for method_id in METHOD_IDS:
        if method_id not in methods:
            raise RuntimeError(f"pass {slot}: method missing: {method_id}")
        run = methods[method_id]
        row = summarize_method(
            run,
            eligible,
            interval_lengths,
            epsilon=0.001,
        )
        row.update(
            {
                "pass_slot": int(slot),
                "protected_sample_count": int(len(long_kappa)),
                "interval_count": int(len(states)),
                "method_action_sha256": sha256_array(run.q_db),
                "method_sector_scale_sha256": sha256_array(
                    run.sector_power_scale
                ),
                "method_stream_action_sha256": (
                    sha256_array(candidate_diagnostics["candidate_stream_scale"])
                    if method_id == CANDIDATE_METHOD_ID
                    else "NOT_APPLICABLE"
                ),
                "runtime_scope": (
                    "candidate_end_to_end_including_sequential_fallback_and_repair_oracles"
                    if method_id == CANDIDATE_METHOD_ID
                    else "legacy_method_specific_not_cross_method_comparable"
                ),
            }
        )
        rows.append(row)
        prefix = f"m{METHOD_IDS.index(method_id)}"
        traces[f"{prefix}_long_ratio"] = run.long_ratio
        traces[f"{prefix}_short_ratio"] = run.short_ratio
        traces[f"{prefix}_floor_count"] = run.floor_violation_count
        traces[f"{prefix}_shortfall"] = run.normalized_shortfall
        traces[f"{prefix}_pf_utility"] = np.log(
            run.moving_average_rate[:, eligible] + 0.001
        ).sum(axis=1)
        traces[f"{prefix}_mute_count"] = np.sum(
            np.isinf(run.sector_backoff_db), axis=1
        )

    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output / f"PASS_{slot}_METHOD_TRACES.npz",
        method_ids=np.asarray(METHOD_IDS),
        interval_lengths=interval_lengths,
        **traces,
    )
    np.savez_compressed(
        output / f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz",
        candidate_stream_scale=candidate_diagnostics["candidate_stream_scale"],
        candidate_action_class=candidate_diagnostics["candidate_action_class"],
        candidate_pre_repair_sector_scale=candidate_diagnostics[
            "candidate_pre_repair_sector_scale"
        ],
        candidate_maximum_shortfall_trace=candidate_diagnostics[
            "candidate_maximum_shortfall_trace"
        ],
        candidate_changed_stream_coefficient_count_trace=candidate_diagnostics[
            "candidate_changed_stream_coefficient_count_trace"
        ],
        candidate_changed_sector_count_trace=candidate_diagnostics[
            "candidate_changed_sector_count_trace"
        ],
        candidate_incremental_float32_payload_lower_bound_bytes_trace=(
            candidate_diagnostics[
                "candidate_incremental_float32_payload_lower_bound_bytes_trace"
            ]
        ),
        interval_lengths=interval_lengths,
    )

    safe_ids = {
        CANDIDATE_METHOD_ID,
        "robust_predictive_constrained_pf_with_sector_selective_fallback",
        "static_robust_constrained_pf_with_sector_selective_fallback",
        "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
        "uniform_protected_tone_backoff",
        "hard_spatial_null_or_exact_mute",
        "common_scale_instantaneous_noncausal_reference",
    }
    for row in rows:
        if row["method_id"] in safe_ids:
            if row["long_violation_seconds"] != 0:
                raise RuntimeError(
                    f"pass {slot}: safe method has long violation: "
                    f"{row['method_id']}"
                )
            if row["short_violation_seconds"] != 0:
                raise RuntimeError(
                    f"pass {slot}: safe method has short violation: "
                    f"{row['method_id']}"
                )
    candidate = next(
        row for row in rows if row["method_id"] == CANDIDATE_METHOD_ID
    )
    candidate_hard_gates = {
        "long_violation_seconds": int(candidate["long_violation_seconds"]),
        "short_violation_seconds": int(candidate["short_violation_seconds"]),
        "eligible_floor_violation_user_seconds": int(
            candidate["eligible_floor_violation_user_seconds"]
        ),
        "eligible_floor_violation_user_intervals": int(
            candidate["eligible_floor_violation_user_intervals"]
        ),
        "strict_local_scope_gate": candidate_diagnostics[
            "strict_local_scope_gate"
        ],
        "strict_post_mode_selected_power_gate": candidate_diagnostics[
            "strict_post_mode_selected_power_gate"
        ],
        "q0_envelope_deployable_actions": int(
            candidate_diagnostics["q0_envelope_deployable_actions"]
        ),
        "unresolved_deployable_intervals": int(
            candidate_diagnostics["unresolved_deployable_intervals"]
        ),
        "network_wide_shutdown_intervals": int(
            candidate_diagnostics["network_wide_shutdown_intervals"]
        ),
    }
    candidate.update(
        {
            "candidate_strict_local_scope_gate": candidate_hard_gates[
                "strict_local_scope_gate"
            ],
            "candidate_strict_post_mode_power_gate": candidate_hard_gates[
                "strict_post_mode_selected_power_gate"
            ],
            "candidate_q0_envelope_deployable_actions": candidate_hard_gates[
                "q0_envelope_deployable_actions"
            ],
            "candidate_unresolved_deployable_intervals": candidate_hard_gates[
                "unresolved_deployable_intervals"
            ],
            "candidate_network_wide_shutdown_intervals": candidate_hard_gates[
                "network_wide_shutdown_intervals"
            ],
            "candidate_maximum_mutable_sector_count": candidate_diagnostics[
                "maximum_mutable_sector_count"
            ],
            "candidate_maximum_external_interferers_per_violating_user": (
                candidate_diagnostics[
                    "maximum_external_interferers_per_violating_user"
                ]
            ),
            "candidate_maximum_eess_backoff_sectors": candidate_diagnostics[
                "maximum_eess_backoff_sectors"
            ],
            "candidate_maximum_strict_post_mode_power_ratio": (
                candidate_diagnostics[
                    "maximum_strict_post_mode_selected_power_ratio"
                ]
            ),
            "candidate_maximum_q0_power_envelope_ratio": candidate_diagnostics[
                "maximum_q0_nominal_power_envelope_ratio"
            ],
            "candidate_maximum_normalized_floor_shortfall": (
                candidate_diagnostics["maximum_normalized_floor_shortfall"]
            ),
            "candidate_baseline_noop_intervals": candidate_diagnostics[
                "action_class_counts"
            ].get("BASELINE_NOOP", 0),
            "candidate_local_grid_repair_intervals": candidate_diagnostics[
                "action_class_counts"
            ].get("SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR", 0),
            "candidate_local_stream_repair_intervals": candidate_diagnostics[
                "action_class_counts"
            ].get("SPARSE_LOCAL_STREAM_POWER_REPAIR", 0),
            "candidate_information_exchange_locality_certified": False,
            "candidate_action_scope_locality_verified": candidate_diagnostics[
                "action_scope_locality_verified"
            ],
            "candidate_global_oracles_classification_only": True,
            "candidate_local_table_build_seconds_sum": candidate_diagnostics[
                "local_table_build_seconds_sum"
            ],
            "candidate_repair_solver_seconds_sum": candidate_diagnostics[
                "repair_solver_seconds_sum"
            ],
            "candidate_local_table_build_seconds_max": candidate_diagnostics[
                "local_table_build_seconds_max"
            ],
            "candidate_repair_solver_seconds_max": candidate_diagnostics[
                "repair_solver_seconds_max"
            ],
            "candidate_repair_solver_seconds_p95_nonzero": candidate_diagnostics[
                "repair_solver_seconds_p95_nonzero"
            ],
            "candidate_changed_stream_coefficient_count_sum": (
                candidate_diagnostics["changed_stream_coefficient_count_sum"]
            ),
            "candidate_changed_sector_interval_count_sum": candidate_diagnostics[
                "changed_sector_interval_count_sum"
            ],
            "candidate_maximum_changed_stream_coefficients_per_interval": (
                candidate_diagnostics[
                    "maximum_changed_stream_coefficients_per_interval"
                ]
            ),
            "candidate_maximum_changed_sectors_per_interval": candidate_diagnostics[
                "maximum_changed_sectors_per_interval"
            ],
            "candidate_incremental_float32_payload_lower_bound_bytes_sum": (
                candidate_diagnostics[
                    "incremental_float32_payload_lower_bound_bytes_sum"
                ]
            ),
            "candidate_payload_claim_boundary": candidate_diagnostics[
                "payload_claim_boundary"
            ],
        }
    )

    audit = {
        "pass_slot": int(slot),
        "protected_sample_count": int(len(long_kappa)),
        "interval_count": int(len(states)),
        "phase_records": phase_records,
        "method_count": len(rows),
        "method_runtime_seconds": elapsed,
        "candidate_hard_gates": candidate_hard_gates,
        "candidate_action_diagnostics": {
            key: value
            for key, value in candidate_diagnostics.items()
            if key not in {
                "interval_records",
                "candidate_stream_scale",
                "candidate_action_class",
                "candidate_pre_repair_sector_scale",
                "candidate_maximum_shortfall_trace",
                "candidate_changed_stream_coefficient_count_trace",
                "candidate_changed_sector_count_trace",
                "candidate_incremental_float32_payload_lower_bound_bytes_trace",
            }
        },
        "candidate_interval_records": candidate_diagnostics["interval_records"],
        "information_exchange_claim_boundary": (
            "ACTION_SCOPE_LOCALITY_VERIFIED_INFORMATION_EXCHANGE_LOCALITY_NOT_YET_CERTIFIED"
        ),
    }
    return rows, audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--array-index", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--reuse-channel", action="store_true")
    args = parser.parse_args()

    contract = json.loads(
        (ROOT / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8")
    )
    authorization = require_authorization(contract)
    stage = authorization["execution_stage"]
    allowed_seeds = [int(v) for v in authorization["allowed_seeds"]]
    if args.seed is not None:
        seed = int(args.seed)
        if seed not in allowed_seeds:
            raise ValueError(f"seed is not authorized for stage {stage}: {seed}")
        array_index = (
            contract["campaign_seed_list"].index(seed)
            if seed in contract["campaign_seed_list"]
            else -1
        )
    else:
        if stage != FULL_STAGE:
            raise RuntimeError("array-index execution is allowed only for the full campaign stage")
        array_index = (
            int(args.array_index)
            if args.array_index is not None
            else int(os.environ.get("SLURM_ARRAY_TASK_ID", "-1"))
        )
        if not (0 <= array_index < len(contract["campaign_seed_list"])):
            raise ValueError(f"invalid array index: {array_index}")
        seed = int(contract["campaign_seed_list"][array_index])
        if seed not in allowed_seeds:
            raise RuntimeError(f"array seed is not authorized: {seed}")

    output_root = Path(args.output_root).expanduser().resolve()
    seed_root = output_root / f"seed_{seed}"
    channel_root = seed_root / "channel"
    result_root = seed_root / "result"
    seed_root.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    if not args.reuse_channel or not (
        channel_root / "CHANNEL_RECORD.json"
    ).is_file():
        if channel_root.exists():
            shutil.rmtree(channel_root)
        channel_record = generate_channel(seed, channel_root)
    else:
        channel_record = json.loads(
            (channel_root / "CHANNEL_RECORD.json").read_text(
                encoding="utf-8"
            )
        )
        if int(channel_record["campaign_seed"]) != seed:
            raise RuntimeError("reused channel seed mismatch")

    data = load_channel(channel_root)
    campaign_contract = json.loads(
        (ROOT / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json").read_text(
            encoding="utf-8"
        )
    )
    pass_temp = seed_root / "pass_extract"
    pass_roots = [extract_pass(slot, pass_temp) for slot in range(5)]
    pass_lengths = [
        len(np.load(path / "protected_time_s.npy")) for path in pass_roots
    ]
    (
        architecture,
        h_effective,
        full_state,
        architecture_audit,
        schedules,
        state_cache,
    ) = create_states(data, campaign_contract, pass_lengths)

    if result_root.exists():
        shutil.rmtree(result_root)
    result_root.mkdir(parents=True)
    cell_rows = []
    pass_audits = []
    for slot, pass_root in enumerate(pass_roots):
        rows, audit = pass_evaluation(
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
        for row in rows:
            row["campaign_seed"] = seed
            row["array_index"] = array_index
        cell_rows.extend(rows)
        pass_audits.append(audit)

    pd.DataFrame(cell_rows).to_csv(
        result_root / "CELL_SUMMARY.csv", index=False
    )
    summary_frame = pd.DataFrame(cell_rows)
    paired_rows = []
    for pass_slot, frame in summary_frame.groupby("pass_slot", sort=True):
        indexed = frame.set_index("method_id")
        candidate_row = indexed.loc[CANDIDATE_METHOD_ID]
        static_row = indexed.loc[
            "static_robust_constrained_pf_with_sector_selective_fallback"
        ]
        predictive_row = indexed.loc[
            "robust_predictive_constrained_pf_with_sector_selective_fallback"
        ]
        paired_rows.append(
            {
                "pass_slot": int(pass_slot),
                "candidate_minus_static_final_pf": float(
                    candidate_row["final_moving_pf_utility"]
                    - static_row["final_moving_pf_utility"]
                ),
                "candidate_minus_static_duration_mean_pf": float(
                    candidate_row["duration_weighted_mean_moving_pf_utility"]
                    - static_row["duration_weighted_mean_moving_pf_utility"]
                ),
                "candidate_minus_predictive_final_pf": float(
                    candidate_row["final_moving_pf_utility"]
                    - predictive_row["final_moving_pf_utility"]
                ),
                "candidate_minus_predictive_duration_mean_pf": float(
                    candidate_row["duration_weighted_mean_moving_pf_utility"]
                    - predictive_row["duration_weighted_mean_moving_pf_utility"]
                ),
            }
        )
    pd.DataFrame(paired_rows).to_csv(
        result_root / "PRIMARY_PAIRED_EFFECTS.csv", index=False
    )


    result_files = {}
    for path in sorted(result_root.iterdir()):
        if path.is_file():
            result_files[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    audit = {
        "schema_version": 1,
        "status": "PENDING_CANDIDATE_HARD_GATE_CLASSIFICATION",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_seed": seed,
        "array_index": array_index,
        "package_id": contract["package_id"],
        "candidate_source_manifest_sha256": contract["candidate_v4_3"][
            "source_manifest_sha256"
        ],
        "authorization_token_sha256": authorization["authorization_file_sha256"],
        "execution_stage": stage,
        "channel_record": channel_record,
        "architecture": {
            "architecture_id": architecture.architecture_id,
            "rf_chains": architecture.rf_chains,
            "analog_phase_bits": architecture.analog_phase_bits,
            "full_load_audit": architecture_audit,
            "nominal_total_sum_se_bps_hz": float(
                full_state.nominal_total_rate.sum()
            ),
        },
        "pass_audits": pass_audits,
        "cell_count": len(cell_rows),
        "method_ids": METHOD_IDS,
        "result_files": result_files,
        "runtime_seconds": time.perf_counter() - started,
        "execution_boundary": (
            "DECLARED_ENGINEERING_SCENARIOS_NOT_CALIBRATION_NOT_COMPLIANCE"
        ),
    }
    candidate_cells = pd.DataFrame(cell_rows).loc[
        lambda value: value["method_id"] == CANDIDATE_METHOD_ID
    ]
    candidate_hard_pass = bool(
        int(candidate_cells["long_violation_seconds"].sum()) == 0
        and int(candidate_cells["short_violation_seconds"].sum()) == 0
        and int(
            candidate_cells["eligible_floor_violation_user_seconds"].sum()
        ) == 0
        and int(
            candidate_cells["eligible_floor_violation_user_intervals"].sum()
        ) == 0
        and float(
            candidate_cells[
                "candidate_maximum_strict_post_mode_power_ratio"
            ].max()
        ) <= 1.0 + 1e-10
        and all(
            record["candidate_hard_gates"]["strict_local_scope_gate"] == "PASS"
            and record["candidate_hard_gates"][
                "strict_post_mode_selected_power_gate"
            ] == "PASS"
            and record["candidate_hard_gates"][
                "q0_envelope_deployable_actions"
            ] == 0
            and record["candidate_hard_gates"][
                "unresolved_deployable_intervals"
            ] == 0
            and record["candidate_hard_gates"][
                "network_wide_shutdown_intervals"
            ] == 0
            for record in pass_audits
        )
    )
    audit["status"] = (
        "PASS_PHASE1_V4_3_SEED_RESULT_REVIEW_REQUIRED"
        if candidate_hard_pass
        else "FAIL_PHASE1_V4_3_CANDIDATE_HARD_GATE_RESULT_REVIEW_REQUIRED"
    )
    audit["candidate_hard_gates_pass"] = candidate_hard_pass
    audit["scientific_exit_code"] = 0 if candidate_hard_pass else 42
    audit["execution_boundary"] = (
        "DECLARED_ENGINEERING_SCENARIOS_NOT_CALIBRATION_NOT_COMPLIANCE"
    )
    write_json(result_root / "SEED_RESULT.json", audit)

    result_files["SEED_RESULT.json"] = {
        "bytes": (result_root / "SEED_RESULT.json").stat().st_size,
        "sha256": sha256_file(result_root / "SEED_RESULT.json"),
    }
    write_json(result_root / "RESULT_FILE_MANIFEST.json", result_files)

    print(
        "PHASE-1 V4.3 SEED WORKER: "
        + ("PASS" if candidate_hard_pass else "SCIENTIFIC_FAIL_RETURN_READY")
    )
    print(json.dumps(audit, indent=2))
    return 0 if candidate_hard_pass else 42


if __name__ == "__main__":
    raise SystemExit(main())
