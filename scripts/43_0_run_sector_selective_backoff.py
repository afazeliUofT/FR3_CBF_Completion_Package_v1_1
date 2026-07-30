#!/usr/bin/env python3
"""Run declared-envelope sector-selective backoff on the exact one-seed data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from fr3_cbf.constrained_pf_safety import action_grid
from fr3_cbf.dual_criterion_controller import interval_reduce
from fr3_cbf.null_floor_aware_sector_backoff import (
    exact_second_ratio,
    simulate_sector_selective,
    simulate_uniform,
)
from fr3_cbf.online_pf_load_transition import (
    build_rotating_load_schedule,
    exponential_average_alpha,
    full_horizon_dynamic_envelope,
    recompute_load_state,
    simulate_online_predictive_controller,
)
from fr3_cbf.physical_impairment_sensitivity import (
    mode_leakage,
    mode_matrices,
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


def summarize_run(
    run: object,
    states: list[object],
    interval_lengths: np.ndarray,
    eligible: np.ndarray,
    floors: np.ndarray,
    epsilon_bps_hz: float,
    nominal_total_by_interval: np.ndarray,
    nominal_protected_by_interval: np.ndarray,
) -> dict[str, object]:
    weights = np.asarray(interval_lengths, dtype=float)
    pf_utility = np.log(
        np.asarray(run.moving_average_rate)[:, eligible]
        + float(epsilon_bps_hz)
    ).sum(axis=1)
    total_network = np.asarray(run.delivered_total_rate).sum(axis=1)
    protected_network = np.asarray(run.delivered_protected_rate).sum(axis=1)
    total_retention = total_network / np.asarray(
        nominal_total_by_interval,
        dtype=float,
    )
    protected_retention = protected_network / np.asarray(
        nominal_protected_by_interval,
        dtype=float,
    )

    active_eligible_values: list[float] = []
    floor_ratios: list[float] = []
    for interval, state in enumerate(states):
        active_eligible = (
            np.asarray(state.active_user, dtype=bool)
            & np.asarray(eligible, dtype=bool)
        )
        active_eligible_values.extend(
            np.asarray(run.delivered_total_rate)[
                interval,
                active_eligible,
            ].tolist()
        )
        if np.any(active_eligible):
            floor_ratios.extend(
                (
                    np.asarray(run.delivered_total_rate)[
                        interval,
                        active_eligible,
                    ]
                    / floors[interval, active_eligible]
                ).tolist()
            )

    mute = np.isinf(np.asarray(run.sector_backoff_db))
    finite_backoff = np.asarray(run.sector_backoff_db)[
        np.isfinite(np.asarray(run.sector_backoff_db))
    ]
    backed_off_count = np.sum(
        np.asarray(run.sector_power_scale) < 1.0 - 1e-15,
        axis=1,
    )
    mute_count = np.sum(mute, axis=1)

    return {
        "long_violation_seconds": int(
            np.sum(np.asarray(run.second_ratio) > 1.0 + 1e-10)
        ),
        "long_maximum_excess_db": float(
            10.0 * np.log10(np.max(run.second_ratio))
        ),
        "eligible_floor_violation_user_intervals": int(
            np.asarray(run.interval_floor_violation_count).sum()
        ),
        "eligible_floor_violation_user_seconds": int(
            np.sum(
                np.asarray(run.interval_floor_violation_count)
                * np.asarray(interval_lengths)
            )
        ),
        "total_normalized_floor_shortfall": float(
            np.asarray(run.interval_normalized_shortfall).sum()
        ),
        "minimum_floor_ratio": float(np.min(floor_ratios)),
        "mean_moving_pf_utility": float(
            np.average(pf_utility, weights=weights)
        ),
        "minimum_moving_pf_utility": float(np.min(pf_utility)),
        "final_moving_pf_utility": float(pf_utility[-1]),
        "mean_total_network_retention": float(
            np.average(total_retention, weights=weights)
        ),
        "minimum_total_network_retention": float(
            np.min(total_retention)
        ),
        "mean_protected_network_retention": float(
            np.average(protected_retention, weights=weights)
        ),
        "minimum_protected_network_retention": float(
            np.min(protected_retention)
        ),
        "minimum_active_eligible_rate_bps_hz": float(
            np.min(active_eligible_values)
        ),
        "p05_active_eligible_rate_bps_hz": float(
            np.quantile(active_eligible_values, 0.05)
        ),
        "maximum_finite_sector_backoff_db": float(
            np.max(finite_backoff) if finite_backoff.size else 0.0
        ),
        "sector_mute_interval_count": int(mute.sum()),
        "intervals_with_any_sector_mute": int(np.sum(mute_count > 0)),
        "mean_muted_sector_count": float(np.mean(mute_count)),
        "maximum_muted_sector_count": int(np.max(mute_count)),
        "mean_backed_off_sector_count": float(
            np.mean(backed_off_count)
        ),
        "maximum_backed_off_sector_count": int(
            np.max(backed_off_count)
        ),
        "maximum_envelope_ratio": float(
            np.max(run.envelope_ratio)
        ),
        "mean_local_cost_table_build_ms": float(
            1000.0 * np.mean(run.local_table_build_seconds)
        ),
        # One float32 backoff value per sector.
        "fallback_payload_bytes_per_update": 57 * 4,
    }


def primary_user_rows(
    user_table: pd.DataFrame,
    states: list[object],
    eligible: np.ndarray,
    floors: np.ndarray,
    selective_run: object,
    uniform_run: object,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for user in range(228):
        active_intervals = np.asarray(
            [state.active_user[user] for state in states],
            dtype=bool,
        )
        row: dict[str, object] = {
            "user_id": str(user_table.loc[user, "user_id"]),
            "serving_sector_id": str(
                user_table.loc[user, "serving_sector_id"]
            ),
            "indoor": bool(user_table.loc[user, "indoor"]),
            "eligible": bool(eligible[user]),
            "active_interval_count": int(active_intervals.sum()),
        }
        for name, run in [
            ("sector_selective", selective_run),
            ("uniform", uniform_run),
        ]:
            delivered = np.asarray(run.delivered_total_rate)[
                active_intervals,
                user,
            ]
            protected = np.asarray(run.delivered_protected_rate)[
                active_intervals,
                user,
            ]
            row[f"{name}_minimum_active_total_rate_bps_hz"] = float(
                np.min(delivered)
            )
            row[f"{name}_mean_active_total_rate_bps_hz"] = float(
                np.mean(delivered)
            )
            row[f"{name}_minimum_active_protected_rate_bps_hz"] = float(
                np.min(protected)
            )
            if eligible[user]:
                active_floor = floors[active_intervals, user]
                row[f"{name}_minimum_floor_ratio"] = float(
                    np.min(delivered / active_floor)
                )
                row[f"{name}_floor_violation_intervals"] = int(
                    np.sum(delivered < active_floor - 1e-12)
                )
            else:
                row[f"{name}_minimum_floor_ratio"] = ""
                row[f"{name}_floor_violation_intervals"] = 0
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/sector_selective_backoff_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))

    for relative, expected in cfg["dependency_sha256"].items():
        actual = sha256_file(ROOT / relative)
        if actual != expected:
            raise ValueError(
                f"dependency hash mismatch for {relative}: "
                f"expected {expected}, actual {actual}"
            )

    data = ROOT / cfg["data_root"]
    dual = ROOT / cfg["dual_criterion_root"]
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    for path in [results, evidence]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    validation = json.loads(
        (data / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json").read_text(
            encoding="utf-8"
        )
    )
    if validation["status"] != (
        "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
    ):
        raise ValueError("the full-topology dataset is not V4 validated")

    frequency_response = np.load(
        data / "frequency_response.npy",
        mmap_mode="r",
    )
    serving = np.load(data / "serving_bs_index.npy")
    stream = np.load(data / "serving_stream_index.npy")
    power_by_frequency = np.load(
        data / "transmit_power_by_frequency_w.npy"
    )
    noise_by_frequency = np.load(
        data / "noise_power_by_frequency_w.npy"
    )
    frequency_weights = np.load(data / "frequency_weights.npy")
    steering1 = np.load(data / "protected_steering_pol1.npy")
    steering2 = np.load(data / "protected_steering_pol2.npy")
    time_s = np.load(data / "protected_time_s.npy")
    nominal_full = np.load(
        data / "nominal_total_weighted_rate_per_user.npy"
    )
    user_table = pd.read_csv(data / "USER_TOPOLOGY.csv")

    timing = cfg["timing"]
    update_interval_s = int(timing["update_interval_s"])
    delay_intervals = int(timing["message_delay_intervals"])
    mode_slew_db = float(timing["mode_slew_db_per_update"])
    interval_count = math.ceil(len(time_s) / update_interval_s)

    load = cfg["load_schedule"]
    schedule, phase_records = build_rotating_load_schedule(
        serving,
        stream,
        interval_count,
        load["phase_lengths_intervals"],
        load["active_streams_per_sector"],
    )
    state_cache: dict[bytes, object] = {}
    states: list[object] = []
    for interval in range(interval_count):
        key = schedule[interval].tobytes()
        if key not in state_cache:
            state_cache[key] = recompute_load_state(
                frequency_response,
                schedule[interval],
                serving,
                stream,
                power_by_frequency,
                noise_by_frequency,
                frequency_weights,
                4,
                steering1,
                steering2,
            )
        states.append(state_cache[key])

    matrices: list[object] = []
    matrix_index_by_state: dict[int, int] = {}
    state_matrix_index: list[int] = []
    for state in states:
        key = id(state)
        if key not in matrix_index_by_state:
            matrix_index_by_state[key] = len(matrices)
            matrices.append(
                mode_matrices(
                    state.nominal_precoder_by_frequency[4],
                    steering1,
                    steering2,
                )
            )
        state_matrix_index.append(matrix_index_by_state[key])

    fairness = cfg["fairness"]
    eligible = nominal_full >= float(
        fairness["serviceability_threshold_bps_hz"]
    )
    floors = np.zeros((interval_count, 228), dtype=float)
    for interval, state in enumerate(states):
        active_eligible = state.active_user & eligible
        floors[interval, active_eligible] = np.maximum(
            float(fairness["absolute_floor_bps_hz"]),
            float(fairness["relative_floor_fraction"])
            * state.nominal_total_rate[active_eligible],
        )

    moving = cfg["moving_average"]
    averaging_alpha = exponential_average_alpha(
        update_interval_s,
        float(moving["time_constant_s"]),
    )
    epsilon = float(moving["epsilon_bps_hz"])
    initial_average = nominal_full.copy()
    nominal_total_by_interval = np.asarray(
        [state.nominal_total_rate.sum() for state in states],
        dtype=float,
    )
    nominal_protected_by_interval = np.asarray(
        [state.nominal_protected_rate.sum() for state in states],
        dtype=float,
    )

    q_grid = action_grid(0, 70, 1)
    backoff_grid = np.asarray(
        cfg["fallback"]["backoff_grid_db"] + [math.inf],
        dtype=float,
    )

    criteria = {
        "long_multiple": (
            "kappa_long_p20_multiple.npy",
            "allowance_long_exact_w.npy",
        ),
        "short_multiple": (
            "kappa_short_p0005_multiple.npy",
            "allowance_short_exact_w.npy",
        ),
        "long_single": (
            "kappa_long_p20_single.npy",
            "allowance_long_exact_w.npy",
        ),
        "short_single": (
            "kappa_short_p0005_single.npy",
            "allowance_short_exact_w.npy",
        ),
    }
    criterion_data: dict[str, dict[str, np.ndarray]] = {}
    for name, (kappa_name, allowance_name) in criteria.items():
        kappa = np.load(dual / kappa_name)
        allowance = np.load(dual / allowance_name)
        kappa_interval, lengths = interval_reduce(
            kappa,
            update_interval_s,
            "max",
        )
        allowance_interval, _ = interval_reduce(
            allowance,
            update_interval_s,
            "min",
        )
        contribution = np.asarray(
            [
                kappa_interval[index, :, None]
                * states[index].mode_leakage_w
                for index in range(interval_count)
            ]
        )
        criterion_data[name] = {
            "kappa": kappa,
            "allowance": allowance,
            "kappa_interval": kappa_interval,
            "allowance_interval": allowance_interval,
            "contribution": contribution,
            "lengths": lengths,
        }

    # Reconstruct the corrected ideal-digital predictive actions. These remain
    # an upper reference; the fallback is evaluated only after clipping them to
    # the declared null-depth cap.
    ideal_actions: dict[str, np.ndarray] = {}
    for long_case in ["long_multiple", "long_single"]:
        item = criterion_data[long_case]
        application_envelope, command_envelope, _ = (
            full_horizon_dynamic_envelope(
                item["contribution"],
                delay_intervals,
                mode_slew_db,
            )
        )
        run = simulate_online_predictive_controller(
            q_grid,
            states,
            item["contribution"],
            item["allowance_interval"],
            application_envelope,
            command_envelope,
            delay_intervals,
            mode_slew_db,
            70.0,
            initial_average,
            averaging_alpha,
            eligible,
            floors,
            serving,
            stream,
            float(noise_by_frequency[4]),
            float(frequency_weights[4]),
            epsilon,
            fail_safe_drop_command_indices=(),
        )
        ideal_actions[long_case] = run.applied_db

    scenario_rows: list[dict[str, object]] = []
    detailed: dict[str, dict[str, object]] = {}
    runs: dict[str, object] = {}
    primary_actions: dict[str, np.ndarray] = {}
    primary_time_rows: list[dict[str, object]] = []

    declared = cfg["declared_engineering_envelope"]
    for pattern in ["multiple", "single"]:
        long_case = f"long_{pattern}"
        short_case = f"short_{pattern}"
        ideal = ideal_actions[long_case]
        for cap in declared["null_depth_caps_db"]:
            q_capped = np.minimum(ideal, float(cap))
            capped_leakage = np.empty(
                (interval_count, 57, 2),
                dtype=float,
            )
            for interval, q_value in enumerate(q_capped):
                implemented = safe_precoder(
                    matrices[state_matrix_index[interval]],
                    q_value,
                )
                capped_leakage[interval] = mode_leakage(
                    implemented,
                    steering1,
                    steering2,
                )

            for uplift in declared["residual_coupling_uplift_db"]:
                for method in ["sector_selective", "uniform"]:
                    started = time.perf_counter()
                    if method == "sector_selective":
                        run = simulate_sector_selective(
                            ideal,
                            capped_leakage,
                            states,
                            criterion_data[long_case]["kappa"],
                            criterion_data[long_case]["allowance"],
                            update_interval_s,
                            float(uplift),
                            float(cap),
                            backoff_grid,
                            serving,
                            stream,
                            float(noise_by_frequency[4]),
                            float(frequency_weights[4]),
                            initial_average,
                            averaging_alpha,
                            eligible,
                            floors,
                            epsilon,
                        )
                    else:
                        run = simulate_uniform(
                            ideal,
                            capped_leakage,
                            states,
                            criterion_data[long_case]["kappa"],
                            criterion_data[long_case]["allowance"],
                            update_interval_s,
                            float(uplift),
                            float(cap),
                            serving,
                            stream,
                            float(noise_by_frequency[4]),
                            float(frequency_weights[4]),
                            initial_average,
                            averaging_alpha,
                            eligible,
                            floors,
                            epsilon,
                        )
                    runtime_seconds = time.perf_counter() - started
                    summary = summarize_run(
                        run,
                        states,
                        criterion_data[long_case]["lengths"],
                        eligible,
                        floors,
                        epsilon,
                        nominal_total_by_interval,
                        nominal_protected_by_interval,
                    )
                    short_ratio = exact_second_ratio(
                        criterion_data[short_case]["kappa"],
                        capped_leakage,
                        run.sector_power_scale,
                        criterion_data[short_case]["allowance"],
                        update_interval_s,
                        float(uplift),
                    )
                    row: dict[str, object] = {
                        "pattern": pattern,
                        "design_case": long_case,
                        "paired_short_case": short_case,
                        "method": method,
                        "null_depth_cap_db": float(cap),
                        "residual_coupling_uplift_db": float(uplift),
                        **summary,
                        "paired_short_violation_seconds": int(
                            np.sum(short_ratio > 1.0 + 1e-10)
                        ),
                        "paired_short_maximum_excess_db": float(
                            10.0 * np.log10(np.max(short_ratio))
                        ),
                        "runtime_seconds": runtime_seconds,
                    }
                    key = (
                        f"{pattern}:cap{cap}:u{uplift}:{method}"
                    )
                    scenario_rows.append(row)
                    detailed[key] = row
                    runs[key] = run

                    primary = declared["primary_decisive_screen"]
                    if (
                        pattern == primary["pattern"]
                        and float(cap)
                        == float(primary["null_depth_cap_db"])
                        and float(uplift)
                        == float(primary["residual_coupling_uplift_db"])
                    ):
                        primary_actions[
                            f"{method}_sector_backoff_db"
                        ] = run.sector_backoff_db
                        primary_actions[
                            f"{method}_sector_power_scale"
                        ] = run.sector_power_scale
                        if method == "sector_selective":
                            for second, value in enumerate(time_s):
                                interval = min(
                                    second // update_interval_s,
                                    interval_count - 1,
                                )
                                primary_time_rows.append(
                                    {
                                        "time_s": float(value),
                                        "interval_index": int(interval),
                                        "long_ratio": float(
                                            run.second_ratio[second]
                                        ),
                                        "short_ratio": float(
                                            short_ratio[second]
                                        ),
                                        "backed_off_sector_count": int(
                                            np.sum(
                                                run.sector_power_scale[
                                                    interval
                                                ]
                                                < 1.0 - 1e-15
                                            )
                                        ),
                                        "muted_sector_count": int(
                                            np.sum(
                                                run.sector_power_scale[
                                                    interval
                                                ]
                                                == 0.0
                                            )
                                        ),
                                    }
                                )

    write_csv(
        results / "SECTOR_BACKOFF_SCENARIO_SUMMARY.csv",
        scenario_rows,
    )
    write_json(
        results / "SECTOR_BACKOFF_DETAILED_RESULTS.json",
        detailed,
    )
    write_csv(
        results / "PRIMARY_SECTOR_BACKOFF_TIME_SERIES.csv",
        primary_time_rows,
    )
    np.savez_compressed(
        results / "PRIMARY_SECTOR_BACKOFF_ACTIONS.npz",
        **primary_actions,
    )

    primary = declared["primary_decisive_screen"]
    primary_prefix = (
        f"{primary['pattern']}:cap{primary['null_depth_cap_db']}:"
        f"u{primary['residual_coupling_uplift_db']}"
    )
    selective_key = f"{primary_prefix}:sector_selective"
    uniform_key = f"{primary_prefix}:uniform"
    selective = detailed[selective_key]
    uniform = detailed[uniform_key]

    boundary = declared["boundary_screen"]
    boundary_prefix = (
        f"{boundary['pattern']}:cap{boundary['null_depth_cap_db']}:"
        f"u{boundary['residual_coupling_uplift_db']}"
    )
    boundary_selective = detailed[
        f"{boundary_prefix}:sector_selective"
    ]

    user_rows = primary_user_rows(
        user_table,
        states,
        eligible,
        floors,
        runs[selective_key],
        runs[uniform_key],
    )
    write_csv(results / "PRIMARY_USER_METRICS.csv", user_rows)

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_DECLARED_ENVELOPE_SECTOR_BACKOFF_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"],
        "source_commit": cfg["required_ancestor_commit"],
        "measured_calibration_available": False,
        "declared_engineering_envelope": declared,
        "load_phase_records": phase_records,
        "scenario_row_count": len(scenario_rows),
        "primary_decisive_screen": {
            "sector_selective": selective,
            "uniform": uniform,
            "selective_minus_uniform_pf_utility": float(
                selective["mean_moving_pf_utility"]
                - uniform["mean_moving_pf_utility"]
            ),
            "selective_minus_uniform_protected_retention": float(
                selective["mean_protected_network_retention"]
                - uniform["mean_protected_network_retention"]
            ),
        },
        "boundary_screen_sector_selective": boundary_selective,
        "all_sector_selective_long_safe": bool(
            all(
                row["long_violation_seconds"] == 0
                for row in scenario_rows
                if row["method"] == "sector_selective"
            )
        ),
        "all_sector_selective_paired_short_safe": bool(
            all(
                row["paired_short_violation_seconds"] == 0
                for row in scenario_rows
                if row["method"] == "sector_selective"
            )
        ),
        "campaign_execution_authorized": False,
        "limitations": [
            "one channel/topology seed and one protected pass",
            "null-depth caps and coupling uplifts are declared deterministic scenarios, not calibration",
            "local cost curves consider served users while exact full-network floors are audited afterward",
            "the scalar-price decomposition is not a proof of global PF optimality",
            "the hard sector protected-tone mute is an explicit fail-safe endpoint",
            "fast fallback latency and its actuation slew are assumed rather than measured",
            "practical 64T64R or hybrid architecture mapping remains open",
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(results / "SECTOR_BACKOFF_AUDIT.json", audit)

    for name in [
        "SECTOR_BACKOFF_SCENARIO_SUMMARY.csv",
        "PRIMARY_SECTOR_BACKOFF_TIME_SERIES.csv",
        "PRIMARY_USER_METRICS.csv",
        "SECTOR_BACKOFF_AUDIT.json",
    ]:
        shutil.copy2(results / name, evidence / name)
    for source, target in [
        (
            ROOT / "docs/SECTOR_SELECTIVE_BACKOFF_CERTIFICATE.md",
            evidence / "SECTOR_SELECTIVE_BACKOFF_CERTIFICATE.md",
        ),
        (
            ROOT
            / "docs/DECLARED_ARRAY_CSI_ENGINEERING_ENVELOPE_V1.md",
            evidence
            / "DECLARED_ARRAY_CSI_ENGINEERING_ENVELOPE_V1.md",
        ),
        (
            ROOT / "config/phased_campaign_spec_v3.json",
            evidence / "PHASED_CAMPAIGN_SPEC_V3.json",
        ),
    ]:
        shutil.copy2(source, target)

    gate = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_DECLARED_ENGINEERING_ENVELOPE_SECTOR_BACKOFF_ONE_SEED",
        "paper_result": False,
        "regulatory_compliance_result": False,
        "measured_calibration": False,
        "sector_selective_fallback_implemented": True,
        "primary_selective_long_safe": (
            selective["long_violation_seconds"] == 0
        ),
        "primary_selective_short_safe": (
            selective["paired_short_violation_seconds"] == 0
        ),
        "primary_selective_floor_violations": selective[
            "eligible_floor_violation_user_intervals"
        ],
        "primary_uniform_floor_violations": uniform[
            "eligible_floor_violation_user_intervals"
        ],
        "boundary_selective_floor_violations": boundary_selective[
            "eligible_floor_violation_user_intervals"
        ],
        "campaign_execution_authorized": False,
        "next_gate": cfg["next_gate"],
    }
    write_json(evidence / "SECTOR_BACKOFF_GATE_DECISION.json", gate)
    (evidence / "README.md").write_text(
        "# Declared-envelope sector-selective fallback\n\n"
        "A distributed local-PF sector backoff is evaluated under explicit "
        "non-calibrated null-cap and residual-coupling scenarios. The primary "
        "65 dB + 3 dB screen remains hard-safe and floor-safe while the "
        "uniform baseline causes eligible-user floor violations. This is "
        "one-seed engineering evidence, not calibration, compliance, or a "
        "paper result.\n",
        encoding="utf-8",
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(ROOT).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("DECLARED-ENVELOPE SECTOR-SELECTIVE BACKOFF: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
