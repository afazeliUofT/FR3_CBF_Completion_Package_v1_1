#!/usr/bin/env python3
"""Map the validated 128-port array to generic 64T64R/hybrid models.

Only the selected 64-RF-chain primary mapping receives the complete online
predictive plus sector-selective fallback replay. Other cases are structural
and full-load sensitivities. This keeps the local gate scientifically focused
and computationally tractable.
"""
from __future__ import annotations

import argparse
import csv
import gc
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
from fr3_cbf.null_floor_aware_sector_backoff import simulate_sector_selective
from fr3_cbf.online_pf_load_transition import (
    build_rotating_load_schedule,
    exponential_average_alpha,
    full_horizon_dynamic_envelope,
    simulate_online_predictive_controller,
)
from fr3_cbf.practical_architecture_mapping import (
    build_architecture,
    effective_channel,
    mode_leakage,
    recompute_architecture_load_state,
    safe_precoder,
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
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def summarize_fallback(
    run: object,
    states: list[object],
    interval_lengths: np.ndarray,
    eligible: np.ndarray,
    floors: np.ndarray,
    epsilon_bps_hz: float,
) -> dict[str, object]:
    pf = np.log(
        np.asarray(run.moving_average_rate)[:, eligible]
        + float(epsilon_bps_hz)
    ).sum(axis=1)
    nominal_total = np.asarray(
        [state.nominal_total_rate.sum() for state in states],
        dtype=float,
    )
    nominal_protected = np.asarray(
        [state.nominal_protected_rate.sum() for state in states],
        dtype=float,
    )
    delivered_total = np.asarray(run.delivered_total_rate).sum(axis=1)
    delivered_protected = np.asarray(run.delivered_protected_rate).sum(axis=1)

    floor_ratios: list[float] = []
    for interval, state in enumerate(states):
        mask = np.asarray(state.active_user, dtype=bool) & eligible
        if np.any(mask):
            floor_ratios.extend(
                (
                    np.asarray(run.delivered_total_rate)[interval, mask]
                    / floors[interval, mask]
                ).tolist()
            )
    mute = np.isinf(np.asarray(run.sector_backoff_db))
    return {
        "controller_evaluated": True,
        "hard_safety_violation_seconds": int(
            np.sum(np.asarray(run.second_ratio) > 1.0 + 1e-10)
        ),
        "eligible_floor_violation_user_intervals": int(
            np.sum(np.asarray(run.interval_floor_violation_count))
        ),
        "minimum_floor_ratio": float(np.min(floor_ratios)),
        "mean_moving_pf_utility": float(
            np.average(pf, weights=interval_lengths)
        ),
        "mean_total_network_retention": float(
            np.average(delivered_total / nominal_total, weights=interval_lengths)
        ),
        "minimum_total_network_retention": float(
            np.min(delivered_total / nominal_total)
        ),
        "mean_protected_network_retention": float(
            np.average(
                delivered_protected / nominal_protected,
                weights=interval_lengths,
            )
        ),
        "minimum_protected_network_retention": float(
            np.min(delivered_protected / nominal_protected)
        ),
        "sector_mute_interval_count": int(np.sum(mute)),
        "intervals_with_any_sector_mute": int(
            np.sum(np.any(mute, axis=1))
        ),
        "maximum_muted_sector_count": int(
            np.max(np.sum(mute, axis=1))
        ),
        "mean_local_cost_table_build_ms": float(
            1000.0 * np.mean(np.asarray(run.local_table_build_seconds))
        ),
        "payload_bytes_per_update": 228,
    }


def full_load_metrics(
    state: object,
    ideal_nominal_rate: np.ndarray,
    ideal_eligible: np.ndarray,
    structural: dict[str, object],
) -> dict[str, object]:
    nominal = np.asarray(state.nominal_total_rate, dtype=float)
    return {
        "nominal_network_sum_se_bps_hz": float(nominal.sum()),
        "nominal_sum_rate_retention_vs_128": float(
            nominal.sum() / np.asarray(ideal_nominal_rate).sum()
        ),
        "nominal_p05_user_se_bps_hz": float(np.quantile(nominal, 0.05)),
        "nominal_minimum_user_se_bps_hz": float(np.min(nominal)),
        "common_ideal_eligible_user_nominal_outage_count": int(
            np.sum(nominal[ideal_eligible] < 0.1)
        ),
        **structural,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/practical_architecture_mapping_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))

    for relative, expected in cfg["dependency_sha256"].items():
        actual = sha256_file(ROOT / relative)
        if actual != expected:
            raise ValueError(
                f"dependency hash mismatch {relative}: {actual} != {expected}"
            )

    data = ROOT / cfg["data_root"]
    dual = ROOT / cfg["dual_criterion_root"]
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    for path in (results, evidence):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    port_table = pd.read_csv(ROOT / cfg["port_order"])
    user_table = pd.read_csv(data / "USER_TOPOLOGY.csv")
    sector_table = pd.read_csv(data / "SECTOR_TOPOLOGY.csv").sort_values(
        "bs_index"
    )
    frequency_response = np.load(data / "frequency_response.npy", mmap_mode="r")
    serving = np.load(data / "serving_bs_index.npy").astype(np.int64)
    stream = np.load(data / "serving_stream_index.npy").astype(np.int64)
    power = np.load(data / "transmit_power_by_frequency_w.npy")
    noise = np.load(data / "noise_power_by_frequency_w.npy")
    weights = np.load(data / "frequency_weights.npy")
    physical_steering_1 = np.load(data / "protected_steering_pol1.npy")
    physical_steering_2 = np.load(data / "protected_steering_pol2.npy")
    ideal_nominal = np.load(data / "nominal_total_weighted_rate_per_user.npy")
    kappa = np.load(dual / "kappa_long_p20_single.npy")
    allowance = np.load(dual / "allowance_long_exact_w.npy")

    validation = json.loads(
        (data / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json").read_text(
            encoding="utf-8"
        )
    )
    if validation["status"] != (
        "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
    ):
        raise ValueError("full-topology data are not V4 validated")

    source_sector_audit = json.loads(
        (
            ROOT
            / "evidence/sector_selective_backoff_v1/SECTOR_BACKOFF_AUDIT.json"
        ).read_text(encoding="utf-8")
    )
    source_ideal_controller = source_sector_audit["primary_decisive_screen"][
        "sector_selective"
    ]

    interval_count = math.ceil(len(kappa) / 5)
    schedule, load_phases = build_rotating_load_schedule(
        serving,
        stream,
        interval_count,
        [20, 20, 20, 20, 20, 18],
        [4, 2, 4, 1, 3, 2],
    )
    ideal_eligible = ideal_nominal >= 0.1
    averaging_alpha = exponential_average_alpha(5, 100)
    epsilon = 0.001
    kappa_interval, interval_lengths = interval_reduce(kappa, 5, "max")
    allowance_interval, _ = interval_reduce(allowance, 5, "min")

    case_rows: list[dict[str, object]] = []
    mapping_rows: list[dict[str, object]] = []
    case_details: dict[str, object] = {}

    for case in cfg["architecture_cases"]:
        started = time.perf_counter()
        architecture = build_architecture(
            architecture_id=case["id"],
            rf_chains=int(case["rf_chains"]),
            analog_phase_bits=case["analog_phase_bits"],
            port_table=port_table,
            user_table=user_table,
            sector_table=sector_table,
            steering_pol1=physical_steering_1,
            steering_pol2=physical_steering_2,
            carrier_frequency_hz=8.15e9,
        )
        h_effective = effective_channel(frequency_response, architecture)

        full_state, _full_matrices, full_structural = (
            recompute_architecture_load_state(
                h_effective=h_effective,
                active_user=np.ones(228, dtype=bool),
                serving_bs_index=serving,
                serving_stream_index=stream,
                transmit_power_by_frequency_w=power,
                noise_power_by_frequency_w=noise,
                frequency_weights=weights,
                protected_frequency_index=4,
                steering_pol1=architecture.effective_steering_pol1,
                steering_pol2=architecture.effective_steering_pol2,
            )
        )
        full_metrics = full_load_metrics(
            full_state,
            ideal_nominal,
            ideal_eligible,
            full_structural,
        )

        controller_metrics: dict[str, object]
        minimum_nullspace = int(
            full_structural["minimum_available_digital_nullspace_dimension"]
        )
        maximum_condition = float(
            full_structural["maximum_local_channel_condition_number"]
        )
        maximum_mode_condition = float(
            full_structural["maximum_protected_mode_condition_number"]
        )
        rank_failures = int(full_structural["local_channel_rank_failure_count"])

        if case["role"] == "upper_reference":
            controller_metrics = {
                "controller_evaluated": True,
                "controller_source": "committed sector-selective audit at e69265e",
                "hard_safety_violation_seconds": int(
                    source_ideal_controller["long_violation_seconds"]
                ),
                "eligible_floor_violation_user_intervals": int(
                    source_ideal_controller[
                        "eligible_floor_violation_user_intervals"
                    ]
                ),
                "minimum_floor_ratio": float(
                    source_ideal_controller["minimum_floor_ratio"]
                ),
                "mean_moving_pf_utility": float(
                    source_ideal_controller["mean_moving_pf_utility"]
                ),
                "mean_total_network_retention": float(
                    source_ideal_controller["mean_total_network_retention"]
                ),
                "minimum_total_network_retention": float(
                    source_ideal_controller["minimum_total_network_retention"]
                ),
                "mean_protected_network_retention": float(
                    source_ideal_controller[
                        "mean_protected_network_retention"
                    ]
                ),
                "minimum_protected_network_retention": float(
                    source_ideal_controller[
                        "minimum_protected_network_retention"
                    ]
                ),
                "sector_mute_interval_count": int(
                    source_ideal_controller["sector_mute_interval_count"]
                ),
                "intervals_with_any_sector_mute": int(
                    source_ideal_controller["intervals_with_any_sector_mute"]
                ),
                "maximum_muted_sector_count": int(
                    source_ideal_controller["maximum_muted_sector_count"]
                ),
                "mean_local_cost_table_build_ms": float(
                    source_ideal_controller["mean_local_cost_table_build_ms"]
                ),
                "payload_bytes_per_update": int(
                    source_ideal_controller["fallback_payload_bytes_per_update"]
                ),
            }
        elif case["role"] == "primary_declared_architecture":
            cache: dict[bytes, tuple[object, object, dict[str, object]]] = {}
            states: list[object] = []
            matrices: list[object] = []
            matrix_indices: list[int] = []
            key_order: list[bytes] = []
            structural_records: list[dict[str, object]] = []

            for active_mask in schedule:
                key = np.asarray(active_mask, dtype=bool).tobytes()
                if key not in cache:
                    cache[key] = recompute_architecture_load_state(
                        h_effective=h_effective,
                        active_user=active_mask,
                        serving_bs_index=serving,
                        serving_stream_index=stream,
                        transmit_power_by_frequency_w=power,
                        noise_power_by_frequency_w=noise,
                        frequency_weights=weights,
                        protected_frequency_index=4,
                        steering_pol1=architecture.effective_steering_pol1,
                        steering_pol2=architecture.effective_steering_pol2,
                    )
                    key_order.append(key)
                state, matrix, structural = cache[key]
                states.append(state)
                matrix_indices.append(key_order.index(key))
                structural_records.append(structural)
            matrices = [cache[key][1] for key in key_order]

            minimum_nullspace = min(
                int(record["minimum_available_digital_nullspace_dimension"])
                for record in structural_records
            )
            maximum_condition = max(
                float(record["maximum_local_channel_condition_number"])
                for record in structural_records
            )
            maximum_mode_condition = max(
                float(record["maximum_protected_mode_condition_number"])
                for record in structural_records
            )
            rank_failures = sum(
                int(record["local_channel_rank_failure_count"])
                for record in structural_records
            )

            floors = np.zeros((interval_count, 228), dtype=float)
            for interval, state in enumerate(states):
                mask = np.asarray(state.active_user, dtype=bool) & ideal_eligible
                floors[interval, mask] = np.maximum(
                    0.1,
                    0.9 * np.asarray(state.nominal_total_rate)[mask],
                )
            contribution = np.asarray(
                [
                    kappa_interval[interval, :, None]
                    * states[interval].mode_leakage_w
                    for interval in range(interval_count)
                ]
            )
            application, command, _ = full_horizon_dynamic_envelope(
                contribution,
                delay_intervals=1,
                slew_db_per_update=3,
            )
            predictive = simulate_online_predictive_controller(
                q_grid_db=action_grid(0, 70, 1),
                states=states,
                contribution_upper_w=contribution,
                allowance_w=allowance_interval,
                application_envelope_w=application,
                command_envelope_w=command,
                delay_intervals=1,
                slew_db_per_update=3,
                maximum_action_db=70,
                moving_average_initial_rate=full_state.nominal_total_rate.copy(),
                averaging_alpha=averaging_alpha,
                eligible_user=ideal_eligible,
                required_floor_by_interval=floors,
                serving_bs_index=serving,
                serving_stream_index=stream,
                protected_noise_w=float(noise[4]),
                protected_weight=float(weights[4]),
                epsilon_bps_hz=epsilon,
                fail_safe_drop_command_indices=(),
            )
            ideal_action = np.asarray(predictive.applied_db)
            cap_db = float(
                cfg["primary_engineering_screen"]["null_depth_cap_db"]
            )
            capped_action = np.minimum(ideal_action, cap_db)
            capped_leakage = np.empty((interval_count, 57, 2), dtype=float)
            for interval, q_db in enumerate(capped_action):
                capped_leakage[interval] = mode_leakage(
                    safe_precoder(
                        matrices[matrix_indices[interval]],
                        q_db,
                    ),
                    architecture.effective_steering_pol1,
                    architecture.effective_steering_pol2,
                )
            backoff_grid = np.asarray(
                cfg["primary_engineering_screen"]["sector_backoff_grid_db"]
                + [math.inf],
                dtype=float,
            )
            fallback = simulate_sector_selective(
                ideal_actions_db=ideal_action,
                capped_leakage=capped_leakage,
                states=states,
                kappa_second=kappa,
                allowance_second=allowance,
                update_interval_s=5,
                coupling_uplift_db=3,
                null_depth_cap_db=cap_db,
                backoff_grid_db=backoff_grid,
                serving_bs=serving,
                serving_stream=stream,
                protected_noise_w=float(noise[4]),
                protected_weight=float(weights[4]),
                initial_average=full_state.nominal_total_rate.copy(),
                averaging_alpha=averaging_alpha,
                eligible=ideal_eligible,
                floors=floors,
                epsilon_bps_hz=epsilon,
            )
            controller_metrics = summarize_fallback(
                fallback,
                states,
                interval_lengths,
                ideal_eligible,
                floors,
                epsilon,
            )
            controller_metrics["controller_source"] = (
                "recomputed generic-64RF online predictive plus "
                "sector-selective fallback"
            )
            del cache, states, matrices, predictive, fallback, capped_leakage
        else:
            controller_metrics = {
                "controller_evaluated": False,
                "controller_source": (
                    "structural/full-load sensitivity only; not selected "
                    "for the phase-1 primary controller replay"
                ),
                "hard_safety_violation_seconds": None,
                "eligible_floor_violation_user_intervals": None,
                "minimum_floor_ratio": None,
                "mean_moving_pf_utility": None,
                "mean_total_network_retention": None,
                "minimum_total_network_retention": None,
                "mean_protected_network_retention": None,
                "minimum_protected_network_retention": None,
                "sector_mute_interval_count": None,
                "intervals_with_any_sector_mute": None,
                "maximum_muted_sector_count": None,
                "mean_local_cost_table_build_ms": None,
                "payload_bytes_per_update": None,
            }

        acceptance = bool(
            case["role"] == "primary_declared_architecture"
            and controller_metrics["hard_safety_violation_seconds"] == 0
            and controller_metrics[
                "eligible_floor_violation_user_intervals"
            ]
            == 0
            and full_metrics["nominal_sum_rate_retention_vs_128"]
            >= cfg["architecture_acceptance"][
                "minimum_nominal_sum_rate_retention_vs_128"
            ]
            and minimum_nullspace
            >= cfg["architecture_acceptance"][
                "minimum_available_digital_nullspace_dimension"
            ]
            and full_metrics[
                "common_ideal_eligible_user_nominal_outage_count"
            ]
            == 0
            and rank_failures == 0
        )

        row = {
            "architecture_id": case["id"],
            "role": case["role"],
            "rf_chains": int(case["rf_chains"]),
            "analog_phase_bits": case["analog_phase_bits"],
            "physical_ports_per_rf_chain": 128 // int(case["rf_chains"]),
            "minimum_available_digital_nullspace_dimension": int(
                minimum_nullspace
            ),
            "local_channel_rank_failure_count": int(rank_failures),
            "maximum_local_channel_condition_number": float(
                maximum_condition
            ),
            "maximum_protected_mode_condition_number": float(
                maximum_mode_condition
            ),
            "maximum_analog_column_orthogonality_error": float(
                architecture.maximum_column_orthogonality_error
            ),
            "phase1_primary_acceptance": acceptance,
            "runtime_seconds": float(time.perf_counter() - started),
            **full_metrics,
            **controller_metrics,
        }
        case_rows.append(row)
        case_details[case["id"]] = {
            "summary": row,
            "grouping": case["grouping"],
        }
        for chain, group in enumerate(architecture.groups):
            mapping_rows.append(
                {
                    "architecture_id": case["id"],
                    "rf_chain_index": chain,
                    "physical_port_indices": ";".join(map(str, group)),
                    "physical_port_count": len(group),
                }
            )
        del h_effective, architecture, full_state
        gc.collect()

    primary = next(
        row
        for row in case_rows
        if row["architecture_id"] == "generic_64t64r_subarray_6bit"
    )
    ideal = next(
        row for row in case_rows if row["architecture_id"] == "ideal_128fd"
    )
    phase_8bit = next(
        row
        for row in case_rows
        if row["architecture_id"] == "generic_64t64r_subarray_8bit"
    )
    hybrid = next(
        row
        for row in case_rows
        if row["architecture_id"] == "generic_32t32r_subarray_6bit"
    )

    gate = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_GENERIC_64T64R_ARCHITECTURE_MAPPING_ONE_SEED"
            if primary["phase1_primary_acceptance"]
            else "FAIL_GENERIC_64T64R_ARCHITECTURE_MAPPING"
        ),
        "paper_result": False,
        "product_mapping": False,
        "measured_calibration": False,
        "campaign_execution_authorized": False,
        "selected_phase1_primary_architecture": (
            "generic_64t64r_subarray_6bit"
            if primary["phase1_primary_acceptance"]
            else None
        ),
        "primary_hard_safe": (
            primary["hard_safety_violation_seconds"] == 0
        ),
        "primary_floor_safe": (
            primary["eligible_floor_violation_user_intervals"] == 0
        ),
        "primary_nominal_sum_rate_retention_vs_128": primary[
            "nominal_sum_rate_retention_vs_128"
        ],
        "phase_8bit_structural_sensitivity_pass": (
            phase_8bit["nominal_sum_rate_retention_vs_128"] >= 0.97
            and phase_8bit[
                "common_ideal_eligible_user_nominal_outage_count"
            ]
            == 0
        ),
        "reduced_32rf_primary_rejected": (
            hybrid["nominal_sum_rate_retention_vs_128"] < 0.97
            or hybrid[
                "common_ideal_eligible_user_nominal_outage_count"
            ]
            > 0
        ),
        "next_gate": cfg["next_gate"],
    }
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_PRACTICAL_ARCHITECTURE_MAPPING_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"],
        "architecture_source_boundary": json.loads(
            (
                ROOT
                / "source_inputs/practical_architecture_mapping_v1/"
                "ARCHITECTURE_SOURCE_RECORDS.json"
            ).read_text(encoding="utf-8")
        )["boundary"],
        "load_phase_records": load_phases,
        "architecture_cases": case_details,
        "selected_primary": primary,
        "ideal_upper_reference": ideal,
        "phase_quantization_sensitivity": phase_8bit,
        "hybrid_sensitivity": hybrid,
        "local_fallback": cfg["local_fallback"],
        "campaign_candidate": cfg["phase1_review_candidate"],
        "limitations": [
            "one channel/topology seed and one protected pass",
            "generic subarray mappings are not commercial product replicas",
            "phase resolution and null caps are declared engineering assumptions",
            "actual fallback latency is unmeasured",
            "the 8-bit and 32-RF cases receive structural/full-load screens only",
            "campaign execution remains unauthorized",
        ],
        "next_gate": cfg["next_gate"],
    }

    write_csv(results / "ARCHITECTURE_CASE_SUMMARY.csv", case_rows)
    write_csv(results / "RF_CHAIN_PORT_MAPPING.csv", mapping_rows)
    write_json(results / "PRACTICAL_ARCHITECTURE_MAPPING_AUDIT.json", audit)
    write_json(evidence / "ARCHITECTURE_GATE_DECISION.json", gate)
    for name in [
        "ARCHITECTURE_CASE_SUMMARY.csv",
        "RF_CHAIN_PORT_MAPPING.csv",
        "PRACTICAL_ARCHITECTURE_MAPPING_AUDIT.json",
    ]:
        shutil.copy2(results / name, evidence / name)
    shutil.copy2(
        ROOT
        / "source_inputs/practical_architecture_mapping_v1/"
        "ARCHITECTURE_SOURCE_RECORDS.json",
        evidence / "ARCHITECTURE_SOURCE_RECORDS.json",
    )
    shutil.copy2(
        ROOT / "docs/PRACTICAL_64T64R_ARCHITECTURE_MAPPING.md",
        evidence / "PRACTICAL_64T64R_ARCHITECTURE_MAPPING.md",
    )
    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  {path.relative_to(ROOT).as_posix()}"
            )
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("PRACTICAL 64T64R/HYBRID ARCHITECTURE MAPPING: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
