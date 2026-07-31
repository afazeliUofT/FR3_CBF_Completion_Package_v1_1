#!/usr/bin/env python3
"""Exact local slot-0 smoke for all eight immutable job-package methods."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
import zipfile

import numpy as np
import pandas as pd

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/phase1_nibi_job_package_builder_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    package = ROOT / cfg["paths"]["job_package_dir"]
    smoke = ROOT / cfg["paths"]["local_smoke_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    if smoke.exists():
        shutil.rmtree(smoke)
    smoke.mkdir(parents=True)
    evidence.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(package / "src"))
    from fr3_cbf.dual_criterion_controller import interval_reduce
    from fr3_cbf.online_pf_load_transition import (
        build_rotating_load_schedule,
        exponential_average_alpha,
    )
    from fr3_cbf.phase1_job_runtime import (
        run_phase1_methods,
        summarize_method,
    )
    from fr3_cbf.practical_architecture_mapping import (
        build_architecture,
        effective_channel,
        recompute_architecture_load_state,
    )

    data = ROOT / "data/real/full_topology_export_18696267_validated_v4/output"
    required = [
        "frequency_response.npy",
        "USER_TOPOLOGY.csv",
        "SECTOR_TOPOLOGY.csv",
        "serving_bs_index.npy",
        "serving_stream_index.npy",
        "transmit_power_by_frequency_w.npy",
        "noise_power_by_frequency_w.npy",
        "frequency_weights.npy",
        "protected_steering_pol1.npy",
        "protected_steering_pol2.npy",
        "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json",
    ]
    for name in required:
        if not (data / name).is_file():
            raise FileNotFoundError(data / name)
    validation = json.loads(
        (data / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json").read_text(
            encoding="utf-8"
        )
    )
    if validation["status"] != (
        "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
    ):
        raise ValueError("local full-topology data are not V4 validated")

    pass_zip = (
        package
        / "input/protected_pass_records/FR3_PROTECTED_PASS_SLOT_0.zip"
    )
    pass_root = smoke / "slot_0"
    pass_root.mkdir()
    with zipfile.ZipFile(pass_zip) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("slot-0 pass archive is corrupt")
        archive.extractall(pass_root)

    contract = json.loads(
        (package / "PHASE1_CAMPAIGN_CONTRACT_V3.json").read_text(
            encoding="utf-8"
        )
    )
    h = np.load(data / "frequency_response.npy", mmap_mode="r")
    serving = np.load(data / "serving_bs_index.npy")
    stream = np.load(data / "serving_stream_index.npy")
    power = np.load(data / "transmit_power_by_frequency_w.npy")
    noise = np.load(data / "noise_power_by_frequency_w.npy")
    weights = np.load(data / "frequency_weights.npy")
    steering1 = np.load(data / "protected_steering_pol1.npy")
    steering2 = np.load(data / "protected_steering_pol2.npy")
    users = pd.read_csv(data / "USER_TOPOLOGY.csv")
    sectors = pd.read_csv(data / "SECTOR_TOPOLOGY.csv").sort_values(
        "bs_index"
    )
    ports = pd.read_csv(
        package / "channel_generator/input/SIONNA_8X8_DUAL_PORT_ORDER.csv"
    )

    primary = contract["primary_scenario"]
    architecture = build_architecture(
        primary["architecture_id"],
        int(primary["rf_chains"]),
        int(primary["analog_phase_bits"]),
        ports,
        users,
        sectors,
        steering1,
        steering2,
        8.15e9,
    )
    h_effective = effective_channel(h, architecture)
    full_state, _full_matrix, architecture_audit = (
        recompute_architecture_load_state(
            h_effective,
            np.ones(228, dtype=bool),
            serving,
            stream,
            power,
            noise,
            weights,
            4,
            architecture.effective_steering_pol1,
            architecture.effective_steering_pol2,
        )
    )

    long_kappa = np.load(pass_root / "kappa_long_multiple.npy")
    short_kappa = np.load(pass_root / "kappa_short_multiple.npy")
    long_allowance = np.load(pass_root / "allowance_long_exact_w.npy")
    short_allowance = np.load(pass_root / "allowance_short_exact_w.npy")
    interval_count = math.ceil(len(long_kappa) / 5)
    load = primary["load_schedule"]
    schedule, phase_records = build_rotating_load_schedule(
        serving,
        stream,
        interval_count,
        load["declared_phase_lengths_intervals"],
        load["active_streams_per_sector"],
    )
    cache = {}
    states = []
    unique_keys = []
    matrix_indices = []
    for mask in schedule:
        key = mask.tobytes()
        if key not in cache:
            cache[key] = recompute_architecture_load_state(
                h_effective,
                mask,
                serving,
                stream,
                power,
                noise,
                weights,
                4,
                architecture.effective_steering_pol1,
                architecture.effective_steering_pol2,
            )
            unique_keys.append(key)
        states.append(cache[key][0])
        matrix_indices.append(unique_keys.index(key))
    matrices = [cache[key][1] for key in unique_keys]

    fairness = primary["fairness"]
    eligible = (
        np.asarray(full_state.nominal_total_rate)
        >= float(fairness["serviceability_threshold_bps_hz"])
    )
    floors = np.zeros((interval_count, 228), dtype=float)
    for index, state in enumerate(states):
        active = np.asarray(state.active_user) & eligible
        floors[index, active] = np.maximum(
            float(fairness["absolute_total_band_floor_bps_hz"]),
            float(fairness["relative_current_load_floor_fraction"])
            * np.asarray(state.nominal_total_rate)[active],
        )

    kappa_interval, interval_lengths = interval_reduce(
        long_kappa, 5, "max"
    )
    contribution = np.asarray(
        [
            kappa_interval[index, :, None]
            * states[index].mode_leakage_w
            for index in range(interval_count)
        ]
    )
    alpha = exponential_average_alpha(
        5, float(primary["moving_average_pf"]["time_constant_s"])
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
        long_contribution=contribution,
        serving=serving,
        stream=stream,
        protected_noise_w=float(noise[4]),
        protected_weight=float(weights[4]),
        initial_average=np.asarray(full_state.nominal_total_rate).copy(),
        alpha=alpha,
        eligible=eligible,
        floors=floors,
        steering1=architecture.effective_steering_pol1,
        steering2=architecture.effective_steering_pol2,
    )
    elapsed = time.perf_counter() - started
    rows = [
        summarize_method(methods[method_id], eligible, interval_lengths)
        for method_id in contract["method_contracts"]
        for method_id in [method_id["id"]]
    ]
    pd.DataFrame(rows).to_csv(
        smoke / "EXACT_SLOT0_ALL8_METHOD_SUMMARY.csv", index=False
    )

    by_id = {row["method_id"]: row for row in rows}
    predictive = by_id[
        "robust_predictive_constrained_pf_with_sector_selective_fallback"
    ]
    static = by_id[
        "static_robust_constrained_pf_with_sector_selective_fallback"
    ]
    reactive = by_id[
        "delayed_myopic_constrained_pf_with_reactive_sector_fallback"
    ]
    unshielded = by_id["delayed_myopic_constrained_pf_unshielded"]
    virtual = by_id["virtual_queue_unshielded"]
    if predictive["long_violation_seconds"] != 0:
        raise RuntimeError("local smoke predictive long safety failed")
    if predictive["short_violation_seconds"] != 0:
        raise RuntimeError("local smoke predictive short safety failed")
    if predictive["eligible_floor_violation_user_seconds"] != 0:
        raise RuntimeError("local smoke predictive floor safety failed")
    if static["long_violation_seconds"] != 0:
        raise RuntimeError("local smoke static safety failed")
    if reactive["long_violation_seconds"] != 0:
        raise RuntimeError("local smoke reactive-myopic fallback safety failed")
    if reactive["eligible_floor_violation_user_seconds"] != 0:
        raise RuntimeError("local smoke reactive-myopic floor safety failed")
    if unshielded["long_violation_seconds"] <= 0:
        raise RuntimeError("local smoke unshielded-myopic negative control failed")
    if virtual["long_violation_seconds"] <= 0:
        raise RuntimeError("local smoke virtual-queue negative control failed")
    if predictive["final_moving_pf_utility"] <= static[
        "final_moving_pf_utility"
    ]:
        raise RuntimeError("local smoke primary utility direction failed")

    audit = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_EXACT_LOCAL_SLOT0_ALL8_METHOD_SMOKE",
        "validated_full_topology_status": validation["status"],
        "candidate_zip_sha256": cfg["candidate_v3"]["zip_sha256"],
        "package_id": (
            package / "PACKAGE_ID.txt"
        ).read_text(encoding="utf-8").strip(),
        "architecture_audit": architecture_audit,
        "nominal_64rf_network_sum_se_bps_hz": float(
            full_state.nominal_total_rate.sum()
        ),
        "protected_samples": int(len(long_kappa)),
        "interval_count": int(interval_count),
        "phase_records": phase_records,
        "eligible_user_count": int(eligible.sum()),
        "method_rows": rows,
        "primary_predictive_minus_static_final_pf": float(
            predictive["final_moving_pf_utility"]
            - static["final_moving_pf_utility"]
        ),
        "reactive_myopic_implemented_and_safe": True,
        "unshielded_myopic_violation_seconds": unshielded[
            "long_violation_seconds"
        ],
        "virtual_queue_violation_seconds": virtual[
            "long_violation_seconds"
        ],
        "runtime_seconds": elapsed,
        "claim_boundary": (
            "ONE_SEED_ONE_PASS_LOCAL_JOB_PACKAGE_SMOKE_NOT_CAMPAIGN_RESULT"
        ),
    }
    write_json(smoke / "EXACT_SLOT0_ALL8_METHOD_SMOKE_AUDIT.json", audit)
    shutil.copy2(
        smoke / "EXACT_SLOT0_ALL8_METHOD_SMOKE_AUDIT.json",
        evidence / "EXACT_SLOT0_ALL8_METHOD_SMOKE_AUDIT.json",
    )
    shutil.copy2(
        smoke / "EXACT_SLOT0_ALL8_METHOD_SUMMARY.csv",
        evidence / "EXACT_SLOT0_ALL8_METHOD_SUMMARY.csv",
    )

    print("EXACT LOCAL PHASE-1 JOB-PACKAGE SMOKE: PASS")
    print(
        json.dumps(
            {
                "status": audit["status"],
                "package_id": audit["package_id"],
                "eligible_user_count": audit["eligible_user_count"],
                "reactive_myopic_implemented_and_safe": audit[
                    "reactive_myopic_implemented_and_safe"
                ],
                "predictive_minus_static_final_pf": audit[
                    "primary_predictive_minus_static_final_pf"
                ],
                "unshielded_myopic_violation_seconds": audit[
                    "unshielded_myopic_violation_seconds"
                ],
                "virtual_queue_violation_seconds": audit[
                    "virtual_queue_violation_seconds"
                ],
                "runtime_seconds": audit["runtime_seconds"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
