#!/usr/bin/env python3
"""Ingest and independently analyze the validated full-topology export."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from fr3_cbf.dynamic_readiness import (
    expand_interval_values,
    interference_ratio_from_attenuation_db,
    interval_maximum,
    minimal_slew_majorant,
    network_rates_for_common_attenuation,
    required_common_attenuation_db,
    simulate_myopic_common_command,
    user_rates_for_mode_scales,
    weakest_mode_preservation_scales,
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
        raise ValueError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def quantiles(values: np.ndarray) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    return {
        name: float(np.quantile(x, q))
        for name, q in [
            ("minimum", 0.0),
            ("p01", 0.01),
            ("p05", 0.05),
            ("p10", 0.10),
            ("p25", 0.25),
            ("median", 0.50),
            ("p75", 0.75),
            ("p90", 0.90),
            ("p95", 0.95),
            ("p99", 0.99),
            ("maximum", 1.0),
        ]
    }


def jain_index(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    return float(x.sum() ** 2 / (len(x) * np.sum(x * x)))


def verify_array_manifest(output: Path) -> tuple[dict[str, np.ndarray], dict]:
    manifest = json.loads(
        (output / "OUTPUT_ARRAY_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    arrays: dict[str, np.ndarray] = {}
    for name, record in manifest["arrays"].items():
        path = output / name
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"Array hash mismatch: {name}")
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if list(value.shape) != record["shape"]:
            raise ValueError(f"Array shape mismatch: {name}")
        if str(value.dtype) != record["dtype"]:
            raise ValueError(f"Array dtype mismatch: {name}")
        if not np.all(np.isfinite(value)):
            raise ValueError(f"Array has non-finite values: {name}")
        arrays[name] = value
    for name, record in manifest["tables"].items():
        path = output / name
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"Table hash mismatch: {name}")
    return arrays, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-zip", required=True)
    parser.add_argument("--review-zip", required=True)
    parser.add_argument(
        "--config",
        default="config/full_topology_ingest_v4.json",
    )
    args = parser.parse_args()

    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    full_zip = Path(args.full_zip).expanduser().resolve()
    review_zip = Path(args.review_zip).expanduser().resolve()
    if sha256_file(full_zip) != expected["full_zip_sha256"]:
        raise ValueError("Full-return ZIP SHA-256 mismatch")
    if sha256_file(review_zip) != expected["review_zip_sha256"]:
        raise ValueError("Compact-review ZIP SHA-256 mismatch")

    for path in [full_zip, review_zip]:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise RuntimeError(f"Corrupt ZIP member: {bad}")

    local_data = ROOT / cfg["paths"]["local_data_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    results = ROOT / cfg["paths"]["results_dir"]
    for path in [local_data, evidence, results]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    with zipfile.ZipFile(full_zip) as archive:
        archive.extractall(local_data)
    output = local_data / "output"

    validation = json.loads(
        (output / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json").read_text(
            encoding="utf-8"
        )
    )
    audit = json.loads(
        (output / "FULL_TOPOLOGY_EXPORT_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    comparison = json.loads(
        (output / "FULL_VS_CHUNKED_COMPARISON.json").read_text(
            encoding="utf-8"
        )
    )
    environment = json.loads(
        (output / "FULL_TOPOLOGY_EXPORT_ENVIRONMENT.json").read_text(
            encoding="utf-8"
        )
    )
    if validation["status"] != expected["validation_status"]:
        raise ValueError("V4 validation status did not pass")
    if validation["failures"]:
        raise ValueError("V4 validation contains failures")
    if audit["full_topology"]["mode"] != (
        "one_topology_call_all_228_users"
    ):
        raise ValueError("Full-topology mode is wrong")
    if audit["full_topology"]["response_shape"] != [228, 57, 128, 9]:
        raise ValueError("Full-topology response shape is wrong")
    if not comparison["legacy_numeric_reproduction"]["pass"]:
        raise ValueError("Legacy chunked reference was not reproduced")

    source_sacct = (
        local_data / "runtime/logs/sacct-18696267.txt"
    ).read_text(encoding="utf-8")
    validation_sacct = (
        local_data
        / "validation_recovery/logs/sacct-18704028.txt"
    ).read_text(encoding="utf-8")
    if (
        "18696267|fr3-fulltopo-export-v1|FAILED|1:0|"
        not in source_sacct
    ):
        raise ValueError("Source H100 Slurm provenance mismatch")
    if (
        "18704028|fr3-fulltopo-val-v4|COMPLETED|0:0|"
        not in validation_sacct
    ):
        raise ValueError("CPU validation Slurm provenance mismatch")

    arrays, manifest = verify_array_manifest(output)

    with zipfile.ZipFile(full_zip) as full_archive:
        full_members = set(full_archive.namelist())
    with zipfile.ZipFile(review_zip) as review_archive:
        review_members = set(review_archive.namelist())
    expected_full_only = {
        "output/frequency_response.npy",
        "output/nominal_amplitude_by_frequency.npy",
    }
    expected_review_only = {
        "validation_recovery/COMPACT_REVIEW_EXCLUSIONS.json",
    }
    if full_members - review_members != expected_full_only:
        raise ValueError("Unexpected full-only ZIP members")
    if review_members - full_members != expected_review_only:
        raise ValueError("Unexpected compact-review-only ZIP members")
    with zipfile.ZipFile(full_zip) as full_archive, zipfile.ZipFile(
        review_zip
    ) as review_archive:
        for name in sorted(full_members & review_members):
            if hashlib.sha256(full_archive.read(name)).digest() != (
                hashlib.sha256(review_archive.read(name)).digest()
            ):
                raise ValueError(f"Full/review member differs: {name}")

    weights = np.asarray(arrays["frequency_weights.npy"], dtype=float)
    protected_weight = float(weights[4])
    nominal_user = np.asarray(
        arrays["nominal_total_weighted_rate_per_user.npy"],
        dtype=float,
    )
    protected_nominal = np.asarray(
        arrays["nominal_protected_rate_per_user.npy"],
        dtype=float,
    )
    other_rate = np.asarray(
        arrays["other_frequency_weighted_rate_per_user.npy"],
        dtype=float,
    )
    common_rate = np.asarray(
        arrays["common_scale_user_rate.npy"],
        dtype=float,
    )
    common_scale = np.asarray(
        arrays["common_scale_reference.npy"],
        dtype=float,
    )
    nominal_aggregate = np.asarray(
        arrays["nominal_aggregate_interference_w.npy"],
        dtype=float,
    )
    allowance = np.asarray(
        arrays["aggregate_allowance_w.npy"],
        dtype=float,
    )
    time_s = np.asarray(arrays["protected_time_s.npy"], dtype=float)
    serving = np.asarray(
        arrays["serving_bs_index.npy"],
        dtype=np.int64,
    )
    stream = np.asarray(
        arrays["serving_stream_index.npy"],
        dtype=np.int64,
    )
    a0 = np.asarray(arrays["protected_amp_perpendicular.npy"])
    a1 = np.asarray(arrays["protected_amp_pol1.npy"])
    a2 = np.asarray(arrays["protected_amp_pol2.npy"])
    leakage = np.asarray(arrays["nominal_mode_leakage_w.npy"])
    kappa = np.asarray(arrays["kappa_time_sector.npy"])
    noise = float(
        np.asarray(arrays["noise_power_by_frequency_w.npy"])[4]
    )
    users = pd.read_csv(output / "USER_TOPOLOGY.csv")
    sectors = pd.read_csv(output / "SECTOR_TOPOLOGY.csv")

    network_nominal = float(nominal_user.sum())
    network_safe = common_rate.sum(axis=1)
    network_retention = network_safe / network_nominal
    protected_safe = (
        common_rate - other_rate[None, :]
    ) / protected_weight
    network_protected_retention = (
        protected_safe.sum(axis=1) / protected_nominal.sum()
    )
    user_worst_total_retention = (
        common_rate.min(axis=0) / nominal_user
    )
    user_worst_protected_retention = (
        protected_safe.min(axis=0) / protected_nominal
    )
    worst_time_index = int(np.argmax(nominal_aggregate))
    worst_time_s = float(time_s[worst_time_index])

    received_sector = (
        kappa * leakage.sum(axis=1)[None, :]
    )
    if not np.allclose(
        received_sector.sum(axis=1),
        nominal_aggregate,
        rtol=1e-12,
        atol=1e-24,
    ):
        raise ValueError("Sector incumbent contributions do not reconstruct")
    sector_order = np.argsort(
        received_sector[worst_time_index]
    )[::-1]
    cumulative = np.cumsum(
        received_sector[worst_time_index, sector_order]
    ) / nominal_aggregate[worst_time_index]
    leaders = np.argmax(received_sector, axis=1)
    leader_ids, leader_counts = np.unique(
        leaders,
        return_counts=True,
    )

    required_db = required_common_attenuation_db(
        nominal_aggregate,
        allowance,
    )
    dynamic_rows: list[dict[str, object]] = []
    for update_interval in cfg["dynamic_screen"][
        "update_interval_s"
    ]:
        for delay in cfg["dynamic_screen"][
            "message_delay_intervals"
        ]:
            for slew in cfg["dynamic_screen"][
                "slew_db_per_update"
            ]:
                bucket, command, myopic_applied = (
                    simulate_myopic_common_command(
                        required_db,
                        int(update_interval),
                        int(delay),
                        float(slew),
                    )
                )
                predictive_bucket = minimal_slew_majorant(
                    bucket,
                    float(slew),
                )
                predictive_applied = expand_interval_values(
                    predictive_bucket,
                    int(update_interval),
                    len(required_db),
                )
                myopic_ratio = (
                    interference_ratio_from_attenuation_db(
                        nominal_aggregate,
                        allowance,
                        myopic_applied,
                    )
                )
                predictive_ratio = (
                    interference_ratio_from_attenuation_db(
                        nominal_aggregate,
                        allowance,
                        predictive_applied,
                    )
                )
                myopic_rate = network_rates_for_common_attenuation(
                    myopic_applied,
                    a0,
                    a1,
                    a2,
                    serving,
                    stream,
                    noise,
                    other_rate,
                    protected_weight,
                )
                predictive_rate = (
                    network_rates_for_common_attenuation(
                        predictive_applied,
                        a0,
                        a1,
                        a2,
                        serving,
                        stream,
                        noise,
                        other_rate,
                        protected_weight,
                    )
                )
                dynamic_rows.append(
                    {
                        "update_interval_s": int(update_interval),
                        "message_delay_intervals": int(delay),
                        "slew_db_per_update": float(slew),
                        "myopic_violation_samples": int(
                            np.sum(myopic_ratio > 1.0 + 1e-12)
                        ),
                        "myopic_maximum_excess_db": float(
                            10.0 * np.log10(np.max(myopic_ratio))
                        ),
                        "perfect_lookahead_violation_samples": int(
                            np.sum(predictive_ratio > 1.0 + 1e-12)
                        ),
                        "perfect_lookahead_maximum_excess_db": float(
                            10.0
                            * np.log10(np.max(predictive_ratio))
                        ),
                        "myopic_mean_network_retention": float(
                            np.mean(myopic_rate) / network_nominal
                        ),
                        "perfect_lookahead_mean_network_retention": float(
                            np.mean(predictive_rate)
                            / network_nominal
                        ),
                        "myopic_minimum_network_retention": float(
                            np.min(myopic_rate) / network_nominal
                        ),
                        "perfect_lookahead_minimum_network_retention": float(
                            np.min(predictive_rate)
                            / network_nominal
                        ),
                        "maximum_myopic_attenuation_deficit_db": float(
                            np.max(required_db - myopic_applied)
                        ),
                        "mean_perfect_lookahead_extra_attenuation_db": float(
                            np.mean(predictive_applied - required_db)
                        ),
                        "interpretation": (
                            "geometry-only common-attenuation readiness "
                            "screen; perfect-lookahead is an offline "
                            "preloaded reference, not the proposed CBF"
                        ),
                    }
                )

    # A non-utility-aware static opportunity screen.
    weak_rates = np.empty_like(common_rate)
    weak_protected = np.empty_like(protected_safe)
    full_mode_counts = []
    zero_mode_counts = []
    for index in range(len(time_s)):
        scale_matrix = weakest_mode_preservation_scales(
            kappa[index, :, None] * leakage,
            float(allowance[index]),
        )
        total_rate, protected_rate = user_rates_for_mode_scales(
            scale_matrix[:, 0],
            scale_matrix[:, 1],
            a0,
            a1,
            a2,
            serving,
            stream,
            noise,
            other_rate,
            protected_weight,
        )
        weak_rates[index] = total_rate
        weak_protected[index] = protected_rate
        full_mode_counts.append(int(np.sum(scale_matrix == 1.0)))
        zero_mode_counts.append(int(np.sum(scale_matrix == 0.0)))

    weak_network_retention = (
        weak_rates.sum(axis=1) / network_nominal
    )
    weak_protected_retention = (
        weak_protected.sum(axis=1)
        / protected_nominal.sum()
    )

    worst_total_index = int(
        np.argmin(user_worst_total_retention)
    )
    worst_protected_index = int(
        np.argmin(user_worst_protected_retention)
    )
    scientific_metrics = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_VALIDATED_FULL_TOPOLOGY_EXPORT_INGESTION",
        "claim_boundary": cfg["claim_boundary"],
        "source_provenance": {
            "source_h100_job_id": expected["source_h100_job_id"],
            "source_h100_state": expected["source_h100_job_state"],
            "source_export_status": "PASS",
            "validation_cpu_job_id": expected[
                "validation_cpu_job_id"
            ],
            "validation_cpu_state": expected[
                "validation_cpu_job_state"
            ],
            "full_zip_sha256": expected["full_zip_sha256"],
            "review_zip_sha256": expected["review_zip_sha256"],
        },
        "dimensions": audit["dimensions"],
        "runtime_seconds": audit["runtime_seconds"],
        "environment": environment,
        "validation_status": validation["status"],
        "legacy_reproduction": comparison[
            "legacy_numeric_reproduction"
        ],
        "full_vs_chunked": comparison["full_vs_chunked"],
        "incumbent_challenge": {
            "allowance_dbw": float(
                10.0 * np.log10(allowance[0])
            ),
            "nominal_aggregate_dbw_quantiles": quantiles(
                10.0 * np.log10(nominal_aggregate)
            ),
            "required_common_attenuation_db_quantiles": quantiles(
                required_db
            ),
            "worst_time_s": worst_time_s,
        },
        "common_scale_reference": {
            "nominal_network_sum_se_bps_hz": network_nominal,
            "total_band_network_retention_quantiles": quantiles(
                network_retention
            ),
            "protected_band_network_retention_quantiles": quantiles(
                network_protected_retention
            ),
            "user_worst_total_band_retention_quantiles": quantiles(
                user_worst_total_retention
            ),
            "user_worst_protected_band_retention_quantiles": quantiles(
                user_worst_protected_retention
            ),
            "nominal_total_band_jain_index": jain_index(
                nominal_user
            ),
            "worst_time_total_band_jain_index": jain_index(
                common_rate[worst_time_index]
            ),
            "worst_total_band_user": {
                "user_id": str(
                    users.loc[worst_total_index, "user_id"]
                ),
                "nominal_se_bps_hz": float(
                    nominal_user[worst_total_index]
                ),
                "minimum_safe_se_bps_hz": float(
                    common_rate[:, worst_total_index].min()
                ),
                "retention": float(
                    user_worst_total_retention[
                        worst_total_index
                    ]
                ),
            },
            "worst_protected_band_user": {
                "user_id": str(
                    users.loc[worst_protected_index, "user_id"]
                ),
                "nominal_protected_se_bps_hz": float(
                    protected_nominal[worst_protected_index]
                ),
                "minimum_safe_protected_se_bps_hz": float(
                    protected_safe[
                        :, worst_protected_index
                    ].min()
                ),
                "retention": float(
                    user_worst_protected_retention[
                        worst_protected_index
                    ]
                ),
            },
        },
        "sector_sparsity_at_worst_time": {
            "top_1_share": float(cumulative[0]),
            "top_2_share": float(cumulative[1]),
            "top_5_share": float(cumulative[4]),
            "top_10_share": float(cumulative[9]),
            "top_15_share": float(cumulative[14]),
            "leading_sector_counts": {
                str(sectors.loc[index, "sector_id"]): int(count)
                for index, count in sorted(
                    zip(leader_ids, leader_counts),
                    key=lambda item: item[1],
                    reverse=True,
                )
            },
            "interpretation_boundary": (
                "common sector azimuths and the modelled earth-station "
                "placement may amplify sparsity; rotation and placement "
                "sensitivity remain mandatory"
            ),
        },
        "static_nonuniform_opportunity_screen": {
            "method": (
                "preserve weakest received modes, partially use one "
                "boundary mode, null stronger modes; not utility-aware"
            ),
            "common_total_band_retention_quantiles": quantiles(
                network_retention
            ),
            "screen_total_band_retention_quantiles": quantiles(
                weak_network_retention
            ),
            "common_protected_band_retention_quantiles": quantiles(
                network_protected_retention
            ),
            "screen_protected_band_retention_quantiles": quantiles(
                weak_protected_retention
            ),
            "common_user_worst_total_retention_quantiles": quantiles(
                user_worst_total_retention
            ),
            "screen_user_worst_total_retention_quantiles": quantiles(
                weak_rates.min(axis=0) / nominal_user
            ),
            "full_mode_count_quantiles": quantiles(
                np.asarray(full_mode_counts)
            ),
            "zero_mode_count_quantiles": quantiles(
                np.asarray(zero_mode_counts)
            ),
            "conclusion": (
                "nonuniform actions improve aggregate/protected-band "
                "retention but can worsen the worst user; the next "
                "controller must be utility- and fairness-aware"
            ),
        },
        "dynamic_geometry_screen": {
            "status": (
                "PASS_NATURAL_RATE_LIMIT_TRAP_EXISTS"
                if any(
                    row["myopic_violation_samples"] > 0
                    and row[
                        "perfect_lookahead_violation_samples"
                    ]
                    == 0
                    for row in dynamic_rows
                )
                else "NO_RATE_LIMIT_TRAP_FOUND"
            ),
            "largest_one_second_required_attenuation_rise_db": float(
                np.max(np.diff(required_db))
            ),
            "boundary": (
                "common-attenuation geometry-only screen; does not "
                "establish a practical predictive-controller utility gain"
            ),
        },
        "limitations": audit["limitations"]
        + [
            "the full versus chunked comparison cannot isolate correlation from random-number mapping",
            "the geometry-only dynamic screen uses a perfect-lookahead preloaded reference",
            "the static nonuniform opportunity screen is not utility-aware",
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(
        evidence / "FULL_TOPOLOGY_SCIENTIFIC_METRICS.json",
        scientific_metrics,
    )
    write_json(
        evidence / "FULL_TOPOLOGY_GATE_DECISION.json",
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": (
                "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_ONE_SEED"
            ),
            "paper_result": False,
            "full_228_user_topology_validated": True,
            "legacy_chunked_reference_reproduced": True,
            "dynamic_controller_proven": False,
            "statistical_generality_proven": False,
            "robustness_proven": False,
            "next_gate": cfg["next_gate"],
        },
    )
    write_csv(
        evidence / "DYNAMIC_RATE_LIMIT_GEOMETRY_SCREEN.csv",
        dynamic_rows,
    )
    write_csv(
        evidence / "USER_WORST_TOTAL_RETENTION_QUANTILES.csv",
        [
            {"quantile": key, "value": value}
            for key, value in quantiles(
                user_worst_total_retention
            ).items()
        ],
    )
    write_csv(
        evidence
        / "USER_WORST_PROTECTED_RETENTION_QUANTILES.csv",
        [
            {"quantile": key, "value": value}
            for key, value in quantiles(
                user_worst_protected_retention
            ).items()
        ],
    )
    write_csv(
        evidence / "NETWORK_RETENTION_TIME_SERIES.csv",
        [
            {
                "time_s": float(time_s[index]),
                "required_common_attenuation_db": float(
                    required_db[index]
                ),
                "common_total_band_network_retention": float(
                    network_retention[index]
                ),
                "common_protected_band_network_retention": float(
                    network_protected_retention[index]
                ),
                "weak_mode_screen_total_band_retention": float(
                    weak_network_retention[index]
                ),
                "weak_mode_screen_protected_band_retention": float(
                    weak_protected_retention[index]
                ),
            }
            for index in range(len(time_s))
        ],
    )
    write_csv(
        evidence / "WORST_TIME_SECTOR_CONTRIBUTIONS.csv",
        [
            {
                "rank": rank,
                "time_s": worst_time_s,
                "sector_id": str(
                    sectors.loc[sector_index, "sector_id"]
                ),
                "received_interference_w": float(
                    received_sector[
                        worst_time_index, sector_index
                    ]
                ),
                "share": float(
                    received_sector[
                        worst_time_index, sector_index
                    ]
                    / nominal_aggregate[worst_time_index]
                ),
                "cumulative_share": float(
                    cumulative[rank - 1]
                ),
            }
            for rank, sector_index in enumerate(
                sector_order,
                start=1,
            )
        ],
    )

    # Preserve the compact review and concise source records in Git evidence.
    shutil.copy2(
        review_zip,
        evidence / expected["review_zip_name"],
    )
    (evidence / f"{expected['review_zip_name']}.sha256").write_text(
        f"{expected['review_zip_sha256']}  "
        f"{expected['review_zip_name']}\n",
        encoding="utf-8",
    )
    for name in [
        "FULL_TOPOLOGY_EXPORT_AUDIT.json",
        "FULL_TOPOLOGY_EXPORT_ENVIRONMENT.json",
        "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json",
        "FULL_VS_CHUNKED_COMPARISON.json",
        "OUTPUT_ARRAY_MANIFEST.json",
    ]:
        shutil.copy2(output / name, evidence / name)

    source_hashes = {
        "full_return": {
            "name": expected["full_zip_name"],
            "sha256": expected["full_zip_sha256"],
            "bytes": full_zip.stat().st_size,
            "storage": "local_only_not_committed",
        },
        "compact_review": {
            "name": expected["review_zip_name"],
            "sha256": expected["review_zip_sha256"],
            "bytes": review_zip.stat().st_size,
            "storage": "committed_evidence",
        },
        "array_manifest_entries": len(manifest["arrays"]),
    }
    write_json(evidence / "SOURCE_HASHES.json", source_hashes)

    readme = f"""# Validated full-topology export: jobs 18696267 and 18704028

Status: `PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_ONE_SEED`

The source H100 job generated the complete 228-user full-topology export and
then exited because its original validator was superseded. CPU validation job
18704028 independently passed the source-linked V4 validation.

Strong accepted facts:

- one Sionna topology call with 228 users and 57 sectors;
- response shape `[228,57,128,9]`;
- full raw channel/precoder/amplitude linkage validated;
- legacy job-18658301 chunked reference reproduced bitwise;
- protected decomposition, mode leakage, incumbent aggregation, SINR and rate
  chains validated;
- controller-ready full channel is retained locally.

Boundary:

`{cfg['claim_boundary']}`

The result is a controller platform, not a TWC paper result. The immediate next
gate is `{cfg['next_gate']}`.
"""
    (evidence / "README.md").write_text(
        readme,
        encoding="utf-8",
    )

    # Local results for convenient review.
    shutil.copy2(
        evidence / "DYNAMIC_RATE_LIMIT_GEOMETRY_SCREEN.csv",
        results / "DYNAMIC_RATE_LIMIT_GEOMETRY_SCREEN.csv",
    )
    shutil.copy2(
        evidence / "NETWORK_RETENTION_TIME_SERIES.csv",
        results / "NETWORK_RETENTION_TIME_SERIES.csv",
    )
    shutil.copy2(
        evidence / "FULL_TOPOLOGY_SCIENTIFIC_METRICS.json",
        results / "FULL_TOPOLOGY_SCIENTIFIC_METRICS.json",
    )

    manifest_path = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest_path:
            lines.append(
                f"{sha256_file(path)}  {path.as_posix()}"
            )
    manifest_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("VALIDATED FULL-TOPOLOGY EXPORT INGESTION: PASS")
    print(json.dumps(scientific_metrics, indent=2))
    print("Evidence files:", len(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
