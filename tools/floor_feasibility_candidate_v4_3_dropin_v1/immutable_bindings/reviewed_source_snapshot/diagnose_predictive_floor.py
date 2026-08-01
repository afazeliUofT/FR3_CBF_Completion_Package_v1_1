#!/usr/bin/env python3
"""Diagnose predictive service-floor feasibility using a preserved channel.

This is a diagnostic-only calculation. It imports the immutable reviewed
phase-1 package, reuses an existing seed-43999 channel, evaluates all five
fixed passes and all eight methods, and records hard-gate outcomes without
aborting. It does not generate a channel and does not create a campaign result.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import time

import numpy as np
import pandas as pd


PRED = "robust_predictive_constrained_pf_with_sector_selective_fallback"


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


def load_worker(package_root: Path):
    path = package_root / "phase1_seed_worker.py"
    spec = importlib.util.spec_from_file_location(
        "phase1_seed_worker_diagnostic_import", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create worker import specification")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(package_root))
    sys.path.insert(0, str(package_root / "src"))
    sys.path.insert(0, str(package_root / "channel_generator"))
    spec.loader.exec_module(module)
    return module


def severity(
    total_user_seconds: int,
    minimum_ratio: float | None,
    maximum_normalized_shortfall: float,
) -> str:
    if total_user_seconds == 0:
        return "NONE"
    if (
        minimum_ratio is not None
        and minimum_ratio >= 1.0 - 1e-8
        and maximum_normalized_shortfall <= 1e-8
    ):
        return "NUMERICAL_SCALE"
    if minimum_ratio is not None and minimum_ratio >= 0.99:
        return "SMALL_BUT_REAL"
    return "MATERIAL"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--channel-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--original-job-id", default="18041525")
    args = parser.parse_args()

    package = Path(args.package_root).expanduser().resolve()
    channel = Path(args.channel_root).expanduser().resolve()
    output = Path(args.output_root).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    worker = load_worker(package)
    from fr3_cbf.dual_criterion_controller import interval_reduce
    from fr3_cbf.online_pf_load_transition import (
        exponential_average_alpha,
    )
    from fr3_cbf.phase1_job_runtime import (
        run_phase1_methods,
        summarize_method,
    )

    data = worker.load_channel(channel)
    contract = json.loads(
        (package / "PHASE1_CAMPAIGN_CONTRACT_V3.json").read_text(
            encoding="utf-8"
        )
    )
    users = data["users"].reset_index().rename(
        columns={"index": "user_index"}
    )

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(
        prefix="fr3_floor_diag_passes_"
    ) as temp_name:
        pass_temp = Path(temp_name)
        pass_roots = [
            worker.extract_pass(slot, pass_temp) for slot in range(5)
        ]
        pass_lengths = [
            len(np.load(path / "protected_time_s.npy"))
            for path in pass_roots
        ]
        (
            architecture,
            _h_effective,
            full_state,
            architecture_audit,
            schedules,
            state_cache,
        ) = worker.create_states(data, contract, pass_lengths)

        all_rows: list[dict[str, object]] = []
        pass_rows: list[dict[str, object]] = []
        user_rows: list[dict[str, object]] = []
        interval_rows: list[dict[str, object]] = []
        pass_audits: list[dict[str, object]] = []

        for slot, pass_root in enumerate(pass_roots):
            schedule, phase_records = schedules[slot]
            states = []
            matrix_indices = []
            unique_keys: list[bytes] = []
            for mask in schedule:
                key = mask.tobytes()
                state, _matrix, _audit = state_cache[key]
                states.append(state)
                if key not in unique_keys:
                    unique_keys.append(key)
                matrix_indices.append(unique_keys.index(key))
            matrices = [state_cache[key][1] for key in unique_keys]

            long_kappa = np.load(
                pass_root / "kappa_long_multiple.npy"
            )
            short_kappa = np.load(
                pass_root / "kappa_short_multiple.npy"
            )
            long_allowance = np.load(
                pass_root / "allowance_long_exact_w.npy"
            )
            short_allowance = np.load(
                pass_root / "allowance_short_exact_w.npy"
            )
            if len(states) != math.ceil(len(long_kappa) / 5):
                raise RuntimeError(
                    f"pass {slot}: state/interval count mismatch"
                )

            kappa_interval, interval_lengths = interval_reduce(
                long_kappa, 5, "max"
            )
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
                np.asarray(
                    full_state.nominal_total_rate,
                    dtype=float,
                )
                >= float(
                    fairness["serviceability_threshold_bps_hz"]
                )
            )
            floors = np.zeros((len(states), 228), dtype=float)
            for index, state in enumerate(states):
                active = (
                    np.asarray(state.active_user, dtype=bool)
                    & eligible
                )
                floors[index, active] = np.maximum(
                    float(
                        fairness[
                            "absolute_total_band_floor_bps_hz"
                        ]
                    ),
                    float(
                        fairness[
                            "relative_current_load_floor_fraction"
                        ]
                    )
                    * np.asarray(state.nominal_total_rate)[active],
                )

            alpha = exponential_average_alpha(
                float(primary["timing"]["update_interval_s"]),
                float(
                    primary["moving_average_pf"][
                        "time_constant_s"
                    ]
                ),
            )
            method_started = time.perf_counter()
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
                initial_average=np.asarray(
                    full_state.nominal_total_rate
                ).copy(),
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
            method_runtime = time.perf_counter() - method_started

            for method_id in worker.METHOD_IDS:
                if method_id not in methods:
                    raise RuntimeError(
                        f"pass {slot}: method missing: {method_id}"
                    )
                row = summarize_method(
                    methods[method_id],
                    eligible,
                    interval_lengths,
                    epsilon=0.001,
                )
                row.update(
                    {
                        "pass_slot": slot,
                        "protected_sample_count": int(
                            len(long_kappa)
                        ),
                        "interval_count": len(states),
                    }
                )
                all_rows.append(row)

            pred_run = methods[PRED]
            active = np.asarray(
                [
                    np.asarray(state.active_user, dtype=bool)
                    for state in states
                ],
                dtype=bool,
            )
            eligible_2d = np.broadcast_to(
                eligible[None, :], floors.shape
            )
            delivered = np.asarray(
                pred_run.delivered_total_rate,
                dtype=np.float64,
            )
            valid = active & eligible_2d & (floors > 0.0)
            violations = (
                valid & (delivered < floors - 1e-12)
            )
            ratios = np.full(
                floors.shape, np.nan, dtype=np.float64
            )
            ratios[valid] = delivered[valid] / floors[valid]
            normalized_shortfall = np.zeros_like(floors)
            normalized_shortfall[valid] = np.maximum(
                0.0,
                (floors[valid] - delivered[valid])
                / floors[valid],
            )

            np.savez_compressed(
                output
                / f"PREDICTIVE_FLOOR_DIAGNOSTIC_PASS_{slot}.npz",
                pass_slot=np.asarray(slot, dtype=np.int64),
                active_user=active,
                eligible=eligible,
                floors=floors,
                delivered_total_rate=delivered,
                delivered_protected_rate=np.asarray(
                    pred_run.delivered_protected_rate
                ),
                moving_average_rate=np.asarray(
                    pred_run.moving_average_rate
                ),
                floor_violation_mask=violations,
                floor_ratio=ratios,
                interval_lengths=np.asarray(
                    interval_lengths, dtype=np.int64
                ),
                q_db=np.asarray(pred_run.q_db),
                sector_power_scale=np.asarray(
                    pred_run.sector_power_scale
                ),
            )

            interval_counts = violations.sum(axis=1)
            user_seconds = (
                violations * interval_lengths[:, None]
            ).sum(axis=0)
            user_intervals = violations.sum(axis=0)
            violating_users = np.flatnonzero(
                user_seconds > 0
            )
            minimum_ratio = (
                float(np.min(ratios[violations]))
                if np.any(violations)
                else None
            )
            max_norm = (
                float(np.max(normalized_shortfall[violations]))
                if np.any(violations)
                else 0.0
            )
            max_abs = (
                float(
                    np.max(
                        (floors - delivered)[violations]
                    )
                )
                if np.any(violations)
                else 0.0
            )
            total_seconds = int(
                (violations * interval_lengths[:, None]).sum()
            )

            pred_summary = next(
                row
                for row in all_rows
                if row["pass_slot"] == slot
                and row["method_id"] == PRED
            )
            pass_rows.append(
                {
                    "pass_slot": slot,
                    "protected_sample_count": int(
                        len(long_kappa)
                    ),
                    "interval_count": len(states),
                    "floor_violation_user_intervals": int(
                        violations.sum()
                    ),
                    "floor_violation_user_seconds": total_seconds,
                    "intervals_with_any_floor_violation": int(
                        np.sum(interval_counts > 0)
                    ),
                    "unique_violating_users": int(
                        len(violating_users)
                    ),
                    "minimum_violating_floor_ratio": (
                        minimum_ratio
                    ),
                    "maximum_normalized_shortfall": max_norm,
                    "maximum_absolute_shortfall_bps_hz": max_abs,
                    "long_violation_seconds": int(
                        pred_summary[
                            "long_violation_seconds"
                        ]
                    ),
                    "short_violation_seconds": int(
                        pred_summary[
                            "short_violation_seconds"
                        ]
                    ),
                    "severity": severity(
                        total_seconds,
                        minimum_ratio,
                        max_norm,
                    ),
                    "method_runtime_seconds": method_runtime,
                }
            )

            for user_index in violating_users:
                mask = violations[:, user_index]
                record = {
                    "pass_slot": slot,
                    "user_index": int(user_index),
                    "violation_intervals": int(
                        user_intervals[user_index]
                    ),
                    "violation_user_seconds": int(
                        user_seconds[user_index]
                    ),
                    "minimum_floor_ratio": float(
                        np.min(ratios[mask, user_index])
                    ),
                    "maximum_normalized_shortfall": float(
                        np.max(
                            normalized_shortfall[
                                mask, user_index
                            ]
                        )
                    ),
                    "maximum_absolute_shortfall_bps_hz": float(
                        np.max(
                            floors[mask, user_index]
                            - delivered[mask, user_index]
                        )
                    ),
                }
                if user_index < len(users):
                    for key, value in users.iloc[
                        user_index
                    ].to_dict().items():
                        if key not in record:
                            record[key] = value
                user_rows.append(record)

            for interval in np.flatnonzero(
                interval_counts > 0
            ):
                mask = violations[interval]
                interval_rows.append(
                    {
                        "pass_slot": slot,
                        "interval_index": int(interval),
                        "interval_seconds": int(
                            interval_lengths[interval]
                        ),
                        "violating_user_count": int(
                            interval_counts[interval]
                        ),
                        "minimum_floor_ratio": float(
                            np.min(ratios[interval, mask])
                        ),
                        "maximum_normalized_shortfall": float(
                            np.max(
                                normalized_shortfall[
                                    interval, mask
                                ]
                            )
                        ),
                    }
                )

            pass_audits.append(
                {
                    "pass_slot": slot,
                    "phase_records": phase_records,
                    "method_runtime_seconds": method_runtime,
                    "predictive_floor_violation_user_seconds": (
                        total_seconds
                    ),
                    "diagnostic_hard_gates_enforced": False,
                }
            )

    cells = pd.DataFrame(all_rows)
    passes = pd.DataFrame(pass_rows)
    violating_users_frame = pd.DataFrame(user_rows)
    intervals = pd.DataFrame(interval_rows)

    cells.to_csv(
        output / "ALL_METHOD_CELL_SUMMARY.csv",
        index=False,
    )
    passes.to_csv(
        output / "PREDICTIVE_FLOOR_PASS_SUMMARY.csv",
        index=False,
    )
    violating_users_frame.to_csv(
        output / "PREDICTIVE_FLOOR_VIOLATING_USERS.csv",
        index=False,
    )
    intervals.to_csv(
        output / "PREDICTIVE_FLOOR_VIOLATING_INTERVALS.csv",
        index=False,
    )

    total_user_seconds = int(
        passes["floor_violation_user_seconds"].sum()
    )
    minimum_values = passes[
        "minimum_violating_floor_ratio"
    ].dropna()
    minimum_ratio = (
        float(minimum_values.min())
        if len(minimum_values)
        else None
    )
    max_norm = float(
        passes["maximum_normalized_shortfall"].max()
    )
    predictive = cells.loc[cells["method_id"] == PRED]

    audit = {
        "schema_version": 1,
        "status": (
            "PASS_RORQUAL_PREDICTIVE_FLOOR_"
            "DIAGNOSTIC_REVIEW_REQUIRED"
        ),
        "created_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "original_h100_job_id": args.original_job_id,
        "diagnostic_seed": 43999,
        "channel_record_sha256": sha256_file(
            channel / "CHANNEL_RECORD.json"
        ),
        "frequency_response_sha256_array_bytes": data[
            "record"
        ]["frequency_response_sha256_array_bytes"],
        "channel_reused": True,
        "h100_channel_regenerated": False,
        "diagnostic_hard_gates_enforced": False,
        "pass_count": 5,
        "method_count": 8,
        "eligible_user_count": int(eligible.sum()),
        "total_predictive_floor_violation_user_seconds": (
            total_user_seconds
        ),
        "total_predictive_floor_violation_user_intervals": int(
            passes[
                "floor_violation_user_intervals"
            ].sum()
        ),
        "unique_pass_user_pairs": int(
            len(violating_users_frame)
        ),
        "minimum_violating_floor_ratio": minimum_ratio,
        "maximum_normalized_shortfall": max_norm,
        "overall_floor_violation_classification": severity(
            total_user_seconds, minimum_ratio, max_norm
        ),
        "predictive_long_violation_seconds": int(
            predictive["long_violation_seconds"].sum()
        ),
        "predictive_short_violation_seconds": int(
            predictive["short_violation_seconds"].sum()
        ),
        "architecture_audit": architecture_audit,
        "pass_audits": pass_audits,
        "runtime_seconds": time.perf_counter() - started,
        "confirmatory_campaign_authorized": False,
        "paper_result": False,
        "claim_boundary": (
            "DIAGNOSTIC_RERUN_USING_PRESERVED_"
            "NONCAMPAIGN_CHANNEL_HARD_GATES_RECORDED_"
            "NOT_ENFORCED"
        ),
        "decision_rule": {
            "NONE": "original floor failure was not reproduced",
            "NUMERICAL_SCALE": (
                "consider only a separately reviewed numerical "
                "tolerance repair"
            ),
            "SMALL_BUT_REAL": (
                "do not relax the gate; strengthen fallback or "
                "floor feasibility"
            ),
            "MATERIAL": (
                "block confirmatory execution and revise the "
                "algorithm/envelope"
            ),
        },
    }
    write_json(
        output / "PREDICTIVE_FLOOR_DIAGNOSTIC_AUDIT.json",
        audit,
    )

    manifest = {}
    for path in sorted(output.iterdir()):
        if path.is_file():
            manifest[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    write_json(
        output / "DIAGNOSTIC_FILE_MANIFEST.json",
        manifest,
    )

    print("RORQUAL PREDICTIVE-FLOOR DIAGNOSTIC: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
