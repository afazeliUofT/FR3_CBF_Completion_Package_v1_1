#!/usr/bin/env python3
"""Run practical null-depth and deterministic physical-impairment sensitivity."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from fr3_cbf.constrained_pf_safety import action_grid
from fr3_cbf.dual_criterion_controller import interval_reduce
from fr3_cbf.online_pf_load_transition import (
    LoadState,
    build_rotating_load_schedule,
    exponential_average_alpha,
    full_horizon_dynamic_envelope,
    recompute_load_state,
    sequential_average_trace,
    simulate_online_predictive_controller,
)
from fr3_cbf.physical_impairment_sensitivity import (
    correlated_port_errors,
    mode_leakage,
    mode_matrices,
    perturbed_direction,
    quantize_precoder_phase,
    renormalize_sector_power,
    required_uniform_backoff_db,
    safe_precoder,
    second_ratio_from_interval_leakage,
    steering_from_local_direction,
)

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"no rows for {path}")
    fields = list(rows[0])
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def quantiles(values: np.ndarray) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    return {
        name: float(np.quantile(x, q))
        for name, q in [
            ("minimum", 0.0),
            ("median", 0.5),
            ("p95", 0.95),
            ("maximum", 1.0),
        ]
    }


def evaluate_with_uniform_backoff(
    actions_db: np.ndarray,
    backoff_db: float,
    states: list[LoadState],
    interval_lengths: np.ndarray,
    serving: np.ndarray,
    stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    initial_average: np.ndarray,
    alpha: float,
    eligible: np.ndarray,
    floors: np.ndarray,
    epsilon: float,
) -> dict[str, float]:
    total_rows = []
    protected_rows = []
    backoff_scale = 10.0 ** (-float(backoff_db) / 20.0)
    for interval, state in enumerate(states):
        q = np.asarray(actions_db[interval], dtype=float)
        scale = np.power(10.0, -q / 20.0)
        amplitude = backoff_scale * (
            state.amp_perpendicular
            + scale[None, :, 0, None] * state.amp_pol1
            + scale[None, :, 1, None] * state.amp_pol2
        )
        power = np.abs(amplitude) ** 2
        desired = power[np.arange(228), serving, stream]
        total_power = power.sum(axis=(1, 2))
        protected_rate = np.log2(
            1.0
            + desired
            / (total_power - desired + float(protected_noise_w))
        )
        total_rate = state.other_weighted_rate + float(protected_weight) * protected_rate
        total_rate = np.asarray(total_rate, dtype=float)
        protected_rate = np.asarray(protected_rate, dtype=float)
        total_rate[~state.active_user] = 0.0
        protected_rate[~state.active_user] = 0.0
        total_rows.append(total_rate)
        protected_rows.append(protected_rate)

    delivered_total = np.asarray(total_rows)
    delivered_protected = np.asarray(protected_rows)
    moving_average = sequential_average_trace(
        delivered_total,
        initial_average,
        alpha,
    )
    active = np.stack([state.active_user for state in states])
    active_eligible = active & eligible[None, :]
    floor_violation = active_eligible & (delivered_total < floors - 1e-12)
    valid = active_eligible & (floors > 0)
    floor_ratio = np.full_like(delivered_total, np.inf, dtype=float)
    floor_ratio[valid] = delivered_total[valid] / floors[valid]
    pf = np.log(moving_average[:, eligible] + epsilon).sum(axis=1)
    nominal_protected = np.asarray(
        [state.nominal_protected_rate.sum() for state in states], dtype=float
    )
    delivered_protected_network = delivered_protected.sum(axis=1)
    return {
        "eligible_floor_violation_user_intervals": int(floor_violation.sum()),
        "minimum_floor_ratio": float(floor_ratio[valid].min()),
        "mean_moving_pf_utility": float(np.average(pf, weights=interval_lengths)),
        "mean_protected_network_retention": float(
            np.average(
                delivered_protected_network / nominal_protected,
                weights=interval_lengths,
            )
        ),
    }


def build_state_mode_matrices(
    states: list[LoadState],
    steering1: np.ndarray,
    steering2: np.ndarray,
) -> tuple[list[object], list[int]]:
    cache: dict[int, int] = {}
    matrices = []
    state_indices = []
    for state in states:
        key = id(state)
        if key not in cache:
            cache[key] = len(matrices)
            matrices.append(
                mode_matrices(
                    state.nominal_precoder_by_frequency[4],
                    steering1,
                    steering2,
                )
            )
        state_indices.append(cache[key])
    return matrices, state_indices


def interval_leakage_with_port_error(
    actions_db: np.ndarray,
    matrices: list[object],
    state_indices: list[int],
    port_error: np.ndarray,
    steering1: np.ndarray,
    steering2: np.ndarray,
) -> np.ndarray:
    rows = []
    for interval, action in enumerate(actions_db):
        nominal = safe_precoder(matrices[state_indices[interval]], action)
        implemented = port_error[:, :, None] * nominal
        implemented = renormalize_sector_power(implemented, nominal)
        rows.append(mode_leakage(implemented, steering1, steering2))
    return np.asarray(rows)


def interval_leakage_with_true_steering(
    actions_db: np.ndarray,
    matrices: list[object],
    state_indices: list[int],
    true_steering1: np.ndarray,
    true_steering2: np.ndarray,
) -> np.ndarray:
    rows = []
    for interval, action in enumerate(actions_db):
        nominal = safe_precoder(matrices[state_indices[interval]], action)
        rows.append(mode_leakage(nominal, true_steering1, true_steering2))
    return np.asarray(rows)


def interval_leakage_with_quantization(
    actions_db: np.ndarray,
    matrices: list[object],
    state_indices: list[int],
    bits: int,
    steering1: np.ndarray,
    steering2: np.ndarray,
) -> np.ndarray:
    rows = []
    for interval, action in enumerate(actions_db):
        nominal = safe_precoder(matrices[state_indices[interval]], action)
        quantized = quantize_precoder_phase(nominal, bits)
        quantized = renormalize_sector_power(quantized, nominal)
        rows.append(mode_leakage(quantized, steering1, steering2))
    return np.asarray(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/physical_impairment_sensitivity_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    controller_cfg = json.loads(
        (ROOT / cfg["dual_controller_config"]).read_text(encoding="utf-8")
    )
    data = ROOT / cfg["data_root"]
    dual = ROOT / cfg["dual_criterion_root"]
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    for path in [results, evidence]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    for name, expected in [
        (cfg["source_inputs"]["port_order"], cfg["source_inputs"]["port_order_sha256"]),
        (cfg["source_inputs"]["local_frame"], cfg["source_inputs"]["local_frame_sha256"]),
    ]:
        if sha256_file(ROOT / name) != expected:
            raise ValueError(f"source input SHA-256 mismatch: {name}")

    frequency_response = np.load(data / "frequency_response.npy", mmap_mode="r")
    serving = np.load(data / "serving_bs_index.npy")
    stream = np.load(data / "serving_stream_index.npy")
    power_f = np.load(data / "transmit_power_by_frequency_w.npy")
    noise_f = np.load(data / "noise_power_by_frequency_w.npy")
    weights = np.load(data / "frequency_weights.npy")
    steering1 = np.load(data / "protected_steering_pol1.npy")
    steering2 = np.load(data / "protected_steering_pol2.npy")
    time_s = np.load(data / "protected_time_s.npy")
    nominal_full = np.load(data / "nominal_total_weighted_rate_per_user.npy")
    users = pd.read_csv(data / "USER_TOPOLOGY.csv")

    timing = controller_cfg["controller_timing"]
    update_interval = int(timing["update_interval_s"])
    delay = int(timing["message_delay_intervals"])
    slew = float(timing["slew_db_per_update"])
    interval_count = int(math.ceil(len(time_s) / update_interval))
    load = controller_cfg["load_schedule"]
    schedule, _ = build_rotating_load_schedule(
        serving,
        stream,
        interval_count,
        load["phase_lengths_intervals"],
        load["active_streams_per_sector"],
    )

    state_cache: dict[bytes, LoadState] = {}
    states: list[LoadState] = []
    for interval in range(interval_count):
        key = schedule[interval].tobytes()
        if key not in state_cache:
            state_cache[key] = recompute_load_state(
                frequency_response,
                schedule[interval],
                serving,
                stream,
                power_f,
                noise_f,
                weights,
                4,
                steering1,
                steering2,
            )
        states.append(state_cache[key])

    fairness = controller_cfg["fairness_policy"]
    eligible = nominal_full >= float(fairness["serviceability_threshold_bps_hz"])
    floors = np.zeros((interval_count, 228), dtype=float)
    for interval, state in enumerate(states):
        active_eligible = state.active_user & eligible
        floors[interval, active_eligible] = np.maximum(
            float(fairness["absolute_total_band_floor_bps_hz"]),
            float(fairness["relative_current_load_floor_fraction"])
            * state.nominal_total_rate[active_eligible],
        )
    moving = controller_cfg["moving_average"]
    alpha = exponential_average_alpha(update_interval, float(moving["time_constant_s"]))
    epsilon = float(moving["epsilon_bps_hz"])
    initial_average = nominal_full.copy()
    q_grid = action_grid(0, 70, 1)

    matrices, state_indices = build_state_mode_matrices(states, steering1, steering2)
    predictive_actions: dict[str, np.ndarray] = {}
    case_data = {}
    for case_name in cfg["cases"]:
        case_cfg = controller_cfg["criteria"][case_name]
        kappa = np.load(dual / case_cfg["kappa_file"])
        allowance_second = np.load(dual / case_cfg["allowance_file"])
        kappa_interval, lengths = interval_reduce(kappa, update_interval, "max")
        allowance_interval, _ = interval_reduce(
            allowance_second, update_interval, "min"
        )
        contribution = np.asarray(
            [
                kappa_interval[index, :, None] * states[index].mode_leakage_w
                for index in range(interval_count)
            ]
        )
        application_env, command_env, _ = full_horizon_dynamic_envelope(
            contribution, delay, slew
        )
        run = simulate_online_predictive_controller(
            q_grid,
            states,
            contribution,
            allowance_interval,
            application_env,
            command_env,
            delay,
            slew,
            70.0,
            initial_average,
            alpha,
            eligible,
            floors,
            serving,
            stream,
            float(noise_f[4]),
            float(weights[4]),
            epsilon,
            fail_safe_drop_command_indices=(),
        )
        predictive_actions[case_name] = run.applied_db
        case_data[case_name] = {
            "kappa": kappa,
            "allowance": allowance_second,
            "interval_lengths": lengths,
        }

    cap_rows = []
    for case_name in cfg["cases"]:
        action = predictive_actions[case_name]
        kappa = case_data[case_name]["kappa"]
        allowance = case_data[case_name]["allowance"]
        for cap in cfg["null_depth_cap_db"]:
            capped = np.minimum(action, float(cap))
            leakage_rows = []
            for interval, q_value in enumerate(capped):
                w_safe = safe_precoder(matrices[state_indices[interval]], q_value)
                leakage_rows.append(mode_leakage(w_safe, steering1, steering2))
            ratio = second_ratio_from_interval_leakage(
                kappa, np.asarray(leakage_rows), update_interval, allowance
            )
            backoff = required_uniform_backoff_db(float(ratio.max()))
            metrics = evaluate_with_uniform_backoff(
                capped,
                backoff,
                states,
                case_data[case_name]["interval_lengths"],
                serving,
                stream,
                float(noise_f[4]),
                float(weights[4]),
                initial_average,
                alpha,
                eligible,
                floors,
                epsilon,
            )
            cap_rows.append(
                {
                    "case": case_name,
                    "null_depth_cap_db": float(cap),
                    "uncorrected_violation_seconds": int(np.sum(ratio > 1.0 + 1e-10)),
                    "uncorrected_maximum_excess_db": float(10.0 * np.log10(ratio.max())),
                    "minimum_uniform_protected_tone_backoff_db": backoff,
                    "post_backoff_maximum_ratio": float(ratio.max() * 10.0 ** (-backoff / 10.0)),
                    **metrics,
                }
            )

    # Worst-case long/single-entry deterministic perturbation screens.
    case_name = "long_single"
    action = predictive_actions[case_name]
    kappa = case_data[case_name]["kappa"]
    allowance = case_data[case_name]["allowance"]
    stress_cfg = cfg["array_error_stress"]
    rng = np.random.default_rng(int(stress_cfg["random_seed"]))
    port_table = pd.read_csv(ROOT / cfg["source_inputs"]["port_order"])
    frame = pd.read_csv(ROOT / cfg["source_inputs"]["local_frame"]).sort_values("sector_id")
    positions = port_table[["x_m", "y_m", "z_m"]].to_numpy(float)
    pol = port_table["polarization"].astype(str).to_numpy()
    pol1_mask = pol == "pol1"
    pol2_mask = pol == "pol2"
    unique_y = sorted(port_table.loc[pol1_mask, "y_m"].unique(), reverse=True)
    unique_z = sorted(port_table.loc[pol1_mask, "z_m"].unique(), reverse=True)
    y_to_col = {value: index for index, value in enumerate(unique_y)}
    z_to_row = {value: index for index, value in enumerate(unique_z)}
    row_index = np.asarray([z_to_row[value] for value in port_table["z_m"]])
    col_index = np.asarray([y_to_col[value] for value in port_table["y_m"]])
    local_direction = frame[["local_direction_x", "local_direction_y", "local_direction_z"]].to_numpy(float)

    stress_rows = []
    trials = int(stress_cfg["trials_per_level"])
    for kind, levels in [
        ("phase_rms_deg", stress_cfg["phase_rms_deg"]),
        ("gain_rms_db", stress_cfg["gain_rms_db"]),
    ]:
        for level in levels:
            max_ratios = []
            violation_seconds = []
            for _ in range(trials):
                phase = float(level) if kind == "phase_rms_deg" else 0.0
                gain = float(level) if kind == "gain_rms_db" else 0.0
                error = correlated_port_errors(
                    rng,
                    pol,
                    row_index,
                    col_index,
                    phase,
                    gain,
                    "independent_port",
                )
                leakage = interval_leakage_with_port_error(
                    action,
                    matrices,
                    state_indices,
                    error,
                    steering1,
                    steering2,
                )
                ratio = second_ratio_from_interval_leakage(
                    kappa, leakage, update_interval, allowance
                )
                max_ratios.append(float(ratio.max()))
                violation_seconds.append(int(np.sum(ratio > 1.0 + 1e-10)))
            stress_rows.append(
                {
                    "stress_family": kind,
                    "level": float(level),
                    "correlation_model": "independent_port",
                    "trials": trials,
                    "maximum_ratio_median": float(np.median(max_ratios)),
                    "maximum_ratio_p95": float(np.quantile(max_ratios, 0.95)),
                    "violation_seconds_median": float(np.median(violation_seconds)),
                    "violation_seconds_p95": float(np.quantile(violation_seconds, 0.95)),
                    "calibrated": False,
                }
            )

    for model in stress_cfg["correlation_models"]:
        max_ratios = []
        violation_seconds = []
        for _ in range(trials):
            error = correlated_port_errors(
                rng,
                pol,
                row_index,
                col_index,
                float(stress_cfg["correlation_probe_phase_rms_deg"]),
                float(stress_cfg["correlation_probe_gain_rms_db"]),
                model,
            )
            leakage = interval_leakage_with_port_error(
                action,
                matrices,
                state_indices,
                error,
                steering1,
                steering2,
            )
            ratio = second_ratio_from_interval_leakage(
                kappa, leakage, update_interval, allowance
            )
            max_ratios.append(float(ratio.max()))
            violation_seconds.append(int(np.sum(ratio > 1.0 + 1e-10)))
        stress_rows.append(
            {
                "stress_family": "joint_phase_gain_correlation",
                "level": f"{stress_cfg['correlation_probe_phase_rms_deg']}deg+{stress_cfg['correlation_probe_gain_rms_db']}dB",
                "correlation_model": model,
                "trials": trials,
                "maximum_ratio_median": float(np.median(max_ratios)),
                "maximum_ratio_p95": float(np.quantile(max_ratios, 0.95)),
                "violation_seconds_median": float(np.median(violation_seconds)),
                "violation_seconds_p95": float(np.quantile(violation_seconds, 0.95)),
                "calibrated": False,
            }
        )

    for error_deg in stress_cfg["direction_error_deg"]:
        max_ratios = []
        violation_seconds = []
        for _ in range(trials):
            true1 = np.empty_like(steering1, dtype=np.complex128)
            true2 = np.empty_like(steering2, dtype=np.complex128)
            for sector in range(57):
                direction = perturbed_direction(
                    local_direction[sector],
                    float(error_deg),
                    rng.normal(size=3),
                )
                true1[sector], true2[sector] = steering_from_local_direction(
                    positions,
                    direction,
                    8.15e9,
                    pol1_mask,
                    pol2_mask,
                )
            leakage = interval_leakage_with_true_steering(
                action,
                matrices,
                state_indices,
                true1,
                true2,
            )
            ratio = second_ratio_from_interval_leakage(
                kappa, leakage, update_interval, allowance
            )
            max_ratios.append(float(ratio.max()))
            violation_seconds.append(int(np.sum(ratio > 1.0 + 1e-10)))
        stress_rows.append(
            {
                "stress_family": "steering_direction_error_deg",
                "level": float(error_deg),
                "correlation_model": "random_tangent_per_sector_static_over_pass",
                "trials": trials,
                "maximum_ratio_median": float(np.median(max_ratios)),
                "maximum_ratio_p95": float(np.quantile(max_ratios, 0.95)),
                "violation_seconds_median": float(np.median(violation_seconds)),
                "violation_seconds_p95": float(np.quantile(violation_seconds, 0.95)),
                "calibrated": False,
            }
        )

    for bits in stress_cfg["phase_quantization_bits"]:
        leakage = interval_leakage_with_quantization(
            action,
            matrices,
            state_indices,
            int(bits),
            steering1,
            steering2,
        )
        ratio = second_ratio_from_interval_leakage(
            kappa, leakage, update_interval, allowance
        )
        stress_rows.append(
            {
                "stress_family": "phase_quantization_bits",
                "level": int(bits),
                "correlation_model": "deterministic_nearest_phase",
                "trials": 1,
                "maximum_ratio_median": float(ratio.max()),
                "maximum_ratio_p95": float(ratio.max()),
                "violation_seconds_median": int(np.sum(ratio > 1.0 + 1e-10)),
                "violation_seconds_p95": int(np.sum(ratio > 1.0 + 1e-10)),
                "calibrated": False,
            }
        )

    write_csv(results / "NULL_DEPTH_CAP_AND_BACKOFF_SWEEP.csv", cap_rows)
    write_csv(results / "ARRAY_STEERING_QUANTIZATION_STRESS.csv", stress_rows)
    np.savez_compressed(
        results / "PREDICTIVE_ACTIONS_LONG_CASES.npz",
        long_multiple_applied_db=predictive_actions["long_multiple"],
        long_single_applied_db=predictive_actions["long_single"],
    )

    cap_long_single = {
        float(row["null_depth_cap_db"]): row
        for row in cap_rows
        if row["case"] == "long_single"
    }
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_PHYSICAL_IMPAIRMENT_SENSITIVITY_AUDIT_CALIBRATION_REQUIRED",
        "claim_boundary": cfg["claim_boundary"],
        "source_commit": cfg["required_ancestor_commit"],
        "cases": cfg["cases"],
        "null_depth_findings": {
            "long_single_cap60": cap_long_single[60.0],
            "long_single_cap65": cap_long_single[65.0],
            "long_single_cap67": cap_long_single[67.0],
            "long_single_cap70": cap_long_single[70.0],
            "interpretation": "Clipping the ideal action to a practical null-depth cap can break hard safety. A broad protected-tone backoff can restore safety but may reduce protected-band utility or violate eligible-user floors. A sector-selective null-floor-aware fallback is required.",
        },
        "stress_findings": {
            "row_count": len(stress_rows),
            "all_levels_are_assumed_not_calibrated": True,
            "any_positive_stress_has_violation": bool(
                any(float(row["violation_seconds_p95"]) > 0 for row in stress_rows)
            ),
            "interpretation": "The ideal long-term single-entry solution operates near the threshold and is sensitive to differential array/steering/quantization errors. Common-mode errors can be much less damaging; the correlation structure must be measured or explicitly bounded.",
        },
        "calibration_status": cfg["calibration_status"],
        "campaign_spec": "config/phased_campaign_spec_v2.json",
        "campaign_execution_authorized": False,
        "next_gate": cfg["next_gate"],
    }
    write_json(results / "PHYSICAL_IMPAIRMENT_SENSITIVITY_AUDIT.json", audit)

    for name in [
        "NULL_DEPTH_CAP_AND_BACKOFF_SWEEP.csv",
        "ARRAY_STEERING_QUANTIZATION_STRESS.csv",
        "PHYSICAL_IMPAIRMENT_SENSITIVITY_AUDIT.json",
    ]:
        shutil.copy2(results / name, evidence / name)
    shutil.copy2(ROOT / "docs/PHYSICAL_CALIBRATION_REQUIREMENTS.md", evidence / "PHYSICAL_CALIBRATION_REQUIREMENTS.md")
    shutil.copy2(ROOT / "config/phased_campaign_spec_v2.json", evidence / "PHASED_CAMPAIGN_SPEC_V2.json")
    shutil.copy2(ROOT / cfg["source_inputs"]["port_order"], evidence / "SIONNA_8X8_DUAL_PORT_ORDER.csv")
    shutil.copy2(ROOT / cfg["source_inputs"]["local_frame"], evidence / "SIONNA_INCUMBENT_LOCAL_FRAME.csv")
    write_json(
        evidence / "PHYSICAL_IMPAIRMENT_GATE_DECISION.json",
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS_DETERMINISTIC_PHYSICAL_IMPAIRMENT_SENSITIVITY_CALIBRATION_DATA_REQUIRED",
            "paper_result": False,
            "regulatory_compliance_result": False,
            "ideal_controller_result_preserved": True,
            "physical_null_depth_calibrated": False,
            "campaign_execution_authorized": False,
            "null_floor_aware_fallback_required": True,
            "next_gate": cfg["next_gate"],
        },
    )
    (evidence / "README.md").write_text(
        "# Physical impairment sensitivity audit\n\n"
        "This stage preserves the ideal corrected dual-criterion result but shows "
        "that its near-threshold 60--70 dB spatial-mode commands are not practical "
        "claims. Null-depth caps, differential array/steering errors, and phase "
        "quantization are deterministic engineering sensitivities only. Measured "
        "or source-referenced calibration data and a null-floor-aware fallback "
        "are required before a multi-seed campaign.\n",
        encoding="utf-8",
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(f"{sha256_file(path)}  {path.relative_to(ROOT).as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("PHYSICAL NULL-DEPTH/UNCERTAINTY SENSITIVITY AUDIT: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
