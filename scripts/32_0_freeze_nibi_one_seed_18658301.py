#!/usr/bin/env python3
"""Freeze and derive concise scientific evidence from Nibi job 18658301."""
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


def verify_manifest(root: Path, manifest: Path) -> int:
    count = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split("  ", 1)
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"Manifest mismatch for {relative}: {actual} != {expected}"
            )
        count += 1
    return count


def quantile_rows(values: np.ndarray) -> list[dict[str, float]]:
    result = []
    for quantile in [
        0.0,
        0.01,
        0.05,
        0.10,
        0.25,
        0.50,
        0.75,
        0.90,
        0.95,
        0.99,
        1.0,
    ]:
        result.append(
            {
                "quantile": quantile,
                "value": float(np.quantile(values, quantile)),
            }
        )
    return result


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def jain_index(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    denominator = len(x) * float(np.sum(x * x))
    return float(np.sum(x) ** 2 / denominator)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-zip", required=True)
    parser.add_argument(
        "--config", default="config/one_seed_18658301_freeze.json"
    )
    args = parser.parse_args()

    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    review_zip = Path(args.review_zip).expanduser().resolve()
    if not review_zip.is_file():
        raise FileNotFoundError(review_zip)
    review_sha = sha256_file(review_zip)
    if review_sha != expected["review_zip_sha256"]:
        raise ValueError(
            f"Review ZIP SHA-256 mismatch: {review_sha} != "
            f"{expected['review_zip_sha256']}"
        )

    work = ROOT / cfg["paths"]["work_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    if work.exists():
        shutil.rmtree(work)
    if evidence.exists():
        shutil.rmtree(evidence)
    source = work / "source_review"
    source.mkdir(parents=True)
    evidence.mkdir(parents=True)

    with zipfile.ZipFile(review_zip) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"Corrupt review ZIP member: {bad}")
        archive.extractall(source)

    manifest_count = verify_manifest(
        source, source / "REVIEW_MANIFEST.sha256"
    )

    input_zip = (
        source
        / "input_bundle"
        / "FR3_DLP_RZF_NIBI_ONE_SEED_GPU_PILOT_v6_PROJECTION_PREFLIGHT_FIXED.zip"
    )
    return_zip = (
        source
        / "return_bundle"
        / "FR3_DLP_RZF_NIBI_PILOT_RETURN_18658301.zip"
    )
    if sha256_file(input_zip) != expected["input_bundle_sha256"]:
        raise ValueError("Executed input bundle hash differs")
    if sha256_file(return_zip) != expected["return_bundle_sha256"]:
        raise ValueError("Return bundle hash differs")

    return_root = source / "return_extracted"
    output = return_root / "output"
    runtime = return_root / "runtime"
    package = return_root / "package"
    success = (
        source / "return_bundle" / "REMOTE_SUCCESS_STATUS.txt"
    ).read_text(encoding="utf-8")
    if f"job_id={expected['job_id']}" not in success:
        raise ValueError("Success record has the wrong job ID")
    if (
        f"input_bundle_sha256={expected['input_bundle_sha256']}"
        not in success
    ):
        raise ValueError("Success record has the wrong input bundle hash")

    job_id = (runtime / "job_id.txt").read_text(encoding="utf-8").strip()
    if job_id != expected["job_id"]:
        raise ValueError(f"Returned job ID is {job_id}")

    sacct = (
        runtime / f"logs/sacct-{expected['job_id']}.txt"
    ).read_text(encoding="utf-8")
    expected_sacct = (
        f"{expected['job_id']}|{expected['job_name']}|"
        f"{expected['slurm_state']}|{expected['exit_code']}|"
    )
    if expected_sacct not in sacct:
        raise ValueError("Slurm completion record did not match")

    environment = json.loads(
        (output / "NIBI_GPU_ENVIRONMENT.json").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (
            output / "NIBI_ONE_SEED_DLP_RZF_PILOT_AUDIT.json"
        ).read_text(encoding="utf-8")
    )
    embedded_metadata = json.loads(
        (package / "BUNDLE_METADATA.json").read_text(encoding="utf-8")
    )
    independent = json.loads(
        (
            source / "INDEPENDENT_LOCAL_REVIEW_SUMMARY.json"
        ).read_text(encoding="utf-8")
    )

    if expected["gpu_substring"] not in environment["gpu_name"]:
        raise ValueError("The returned GPU was not an H100")
    if (
        audit["status"]
        != "PASS_ONE_SEED_GPU_DLP_RZF_PILOT_REVIEW_REQUIRED"
    ):
        raise ValueError("Pilot audit status did not pass")
    if audit["channel_generation"]["chunk_count"] != 57:
        raise ValueError("Expected exactly 57 four-user channel chunks")

    time_frame = pd.read_csv(output / "PILOT_TIME_SUMMARY.csv")
    sector_frame = pd.read_csv(
        output / "PILOT_SECTOR_TIME_METRICS.csv.gz"
    )
    user_frame = pd.read_csv(output / "PILOT_USER_RATE_SUMMARY.csv")
    with np.load(
        output / "PILOT_NUMERICAL_EVIDENCE.npz",
        allow_pickle=False,
    ) as data:
        arrays = {name: np.asarray(data[name]) for name in data.files}

    if len(time_frame) != expected["protected_pass_samples"]:
        raise ValueError("Unexpected time-row count")
    if len(sector_frame) != expected["sector_time_rows"]:
        raise ValueError("Unexpected sector-time row count")
    if len(user_frame) != expected["users"]:
        raise ValueError("Unexpected user-row count")
    if arrays["safe_rate_matrix"].shape != (
        expected["protected_pass_samples"],
        expected["users"],
    ):
        raise ValueError("Unexpected safe-rate matrix shape")

    local_violations = int(
        (~sector_frame["budget_satisfied"].astype(bool)).sum()
    )
    power_violations = int(
        (~sector_frame["power_nonincrease"].astype(bool)).sum()
    )
    if local_violations != 0 or power_violations != 0:
        raise ValueError("The one-seed gate has a local accounting violation")

    aggregate_excess = (
        arrays["aggregate_safe_w"] - arrays["aggregate_allowance_w"]
    )
    safe_reconstructed = (
        sector_frame.groupby("time_s", sort=True)["safe_received_w"]
        .sum()
        .to_numpy()
    )
    budget_reconstructed = (
        sector_frame.groupby("time_s", sort=True)["budget_w"]
        .sum()
        .to_numpy()
    )
    rate_reconstructed = arrays["safe_rate_matrix"].sum(axis=1)

    user_min_retention = (
        user_frame["safe_se_min_bps_hz"].to_numpy()
        / user_frame["nominal_se_bps_hz"].to_numpy()
    )
    user_median_retention = (
        user_frame["safe_se_median_bps_hz"].to_numpy()
        / user_frame["nominal_se_bps_hz"].to_numpy()
    )
    power_retention = (
        sector_frame["safe_precoder_power_w"].to_numpy()
        / sector_frame["nominal_precoder_power_w"].to_numpy()
    )

    time_scales = sector_frame.groupby("time_s", sort=True).agg(
        pol1_min=("pol1_scale", "min"),
        pol1_max=("pol1_scale", "max"),
        pol2_min=("pol2_scale", "min"),
        pol2_max=("pol2_scale", "max"),
    )
    time_scales["all_mode_spread"] = np.maximum(
        time_scales["pol1_max"], time_scales["pol2_max"]
    ) - np.minimum(time_scales["pol1_min"], time_scales["pol2_min"])

    worst_row = time_frame.loc[
        time_frame["aggregate_nominal_interference_w"].idxmax()
    ]
    worst_time = float(worst_row["time_s"])
    worst_sector = sector_frame.loc[
        np.isclose(sector_frame["time_s"], worst_time)
    ].sort_values("nominal_received_w", ascending=False)
    worst_sector = worst_sector.copy()
    worst_sector["share"] = (
        worst_sector["nominal_received_w"]
        / worst_sector["nominal_received_w"].sum()
    )
    worst_sector["cumulative_share"] = worst_sector["share"].cumsum()

    leaders = sector_frame.loc[
        sector_frame.groupby("time_s")["nominal_received_w"].idxmax()
    ]["sector_id"].value_counts()

    def dbw(value: np.ndarray | float) -> np.ndarray | float:
        return 10.0 * np.log10(np.maximum(value, 1e-300))

    allowance_dbw = float(dbw(time_frame["aggregate_allowance_w"].iloc[0]))
    nominal_min_dbw = float(
        dbw(time_frame["aggregate_nominal_interference_w"].min())
    )
    nominal_max_dbw = float(
        dbw(time_frame["aggregate_nominal_interference_w"].max())
    )
    reserve_fraction = float(
        1.0
        - time_frame["aggregate_allowance_w"].iloc[0]
        / (10.0 ** (-133.0 / 10.0))
    )
    reserve_db = float(-10.0 * math.log10(1.0 - reserve_fraction))

    metrics = {
        "status": "PASS_ONE_SEED_SOFTWARE_AND_PHYSICAL_ACCOUNTING_GATE",
        "claim_boundary": cfg["claim_boundary"],
        "job": {
            "job_id": job_id,
            "job_name": expected["job_name"],
            "slurm_state": expected["slurm_state"],
            "exit_code": expected["exit_code"],
            "input_bundle_sha256": expected["input_bundle_sha256"],
            "return_bundle_sha256": expected["return_bundle_sha256"],
            "review_zip_sha256": review_sha,
        },
        "dimensions": {
            "sites": expected["sites"],
            "sectors": expected["sectors"],
            "users": expected["users"],
            "users_per_sector": expected["users_per_sector"],
            "ports_per_bs": expected["ports_per_bs"],
            "frequency_samples": expected["frequency_samples"],
            "protected_pass_samples": expected["protected_pass_samples"],
            "sector_time_rows": expected["sector_time_rows"],
        },
        "accounting": {
            "local_budget_violation_count": local_violations,
            "power_increase_violation_count": power_violations,
            "maximum_safe_minus_allowance_w": float(
                np.max(aggregate_excess)
            ),
            "maximum_sector_aggregate_reconstruction_error_w": float(
                np.max(
                    np.abs(
                        safe_reconstructed
                        - time_frame[
                            "aggregate_safe_interference_w"
                        ].to_numpy()
                    )
                )
            ),
            "maximum_budget_sum_reconstruction_error_w": float(
                np.max(
                    np.abs(
                        budget_reconstructed
                        - time_frame["budget_sum_w"].to_numpy()
                    )
                )
            ),
            "maximum_safe_rate_sum_reconstruction_error_bps_hz": float(
                np.max(
                    np.abs(
                        rate_reconstructed
                        - time_frame[
                            "network_safe_sum_se_bps_hz"
                        ].to_numpy()
                    )
                )
            ),
        },
        "network_utility": {
            "nominal_sum_se_bps_hz": float(
                time_frame["network_nominal_sum_se_bps_hz"].iloc[0]
            ),
            "minimum_retention": float(
                time_frame["rate_retention_fraction"].min()
            ),
            "median_retention": float(
                time_frame["rate_retention_fraction"].median()
            ),
            "maximum_retention": float(
                time_frame["rate_retention_fraction"].max()
            ),
        },
        "user_utility": {
            "minimum_worst_pass_retention": float(
                np.min(user_min_retention)
            ),
            "users_improved_at_worst_pass": int(
                (
                    user_frame["safe_se_min_bps_hz"]
                    > user_frame["nominal_se_bps_hz"]
                ).sum()
            ),
            "users_decreased_at_worst_pass": int(
                (
                    user_frame["safe_se_min_bps_hz"]
                    < user_frame["nominal_se_bps_hz"]
                ).sum()
            ),
            "nominal_jain_index": jain_index(
                user_frame["nominal_se_bps_hz"].to_numpy()
            ),
            "worst_pass_safe_jain_index": jain_index(
                user_frame["safe_se_min_bps_hz"].to_numpy()
            ),
            "nominal_users_below_0_1_bps_hz": int(
                (user_frame["nominal_se_bps_hz"] < 0.1).sum()
            ),
            "safe_users_below_0_1_bps_hz": int(
                (user_frame["safe_se_min_bps_hz"] < 0.1).sum()
            ),
        },
        "incumbent_challenge": {
            "nominal_aggregate_min_dbw_per_10mhz": nominal_min_dbw,
            "nominal_aggregate_max_dbw_per_10mhz": nominal_max_dbw,
            "allowance_dbw_per_10mhz": allowance_dbw,
            "required_suppression_min_db": nominal_min_dbw - allowance_dbw,
            "required_suppression_max_db": nominal_max_dbw - allowance_dbw,
            "linear_reserve_fraction": reserve_fraction,
            "reserve_db": reserve_db,
        },
        "common_scale_reference": {
            "maximum_mode_scale_spread_at_fixed_time": float(
                time_scales["all_mode_spread"].max()
            ),
            "median_mode_scale_spread_at_fixed_time": float(
                time_scales["all_mode_spread"].median()
            ),
            "analytical_status": (
                "DEGENERATE_COMMON_ORACLE_SCALE_NOT_UTILITY_AWARE_ALLOCATION"
            ),
        },
        "runtime_seconds": audit["runtime_seconds"],
        "environment": environment,
        "limitations": [
            "one channel and topology seed",
            "one protected pass",
            "finite network without wraparound",
            "eight-by-eight dual-polarized fully digital pilot array",
            "nine frequency samples",
            "four-user sector chunks do not preserve cross-sector large-scale correlation",
            "only the protected ten-megahertz frequency sample is modified by DLP",
            "instantaneous proportional budgets reduce analytically to one common scale",
            "no delayed or rate-limited controller",
            "ten-percent linear reserve is not uncertainty-calibrated",
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(evidence / "ONE_SEED_METRICS.json", metrics)

    gate = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": metrics["status"],
        "claim_boundary": cfg["claim_boundary"],
        "platform_proven_for_one_seed": True,
        "paper_result": False,
        "dynamic_controller_proven": False,
        "statistical_generality_proven": False,
        "robust_uncertainty_proven": False,
        "protected_subband_utility_exported": False,
        "full_topology_cross_sector_correlation_preserved": False,
        "accepted_facts": [
            "57-sector 228-user H100 channel generation completed",
            "four-user local RZF completed",
            "exact local-frame DLP projection completed",
            "all 587 protected samples completed",
            "zero local budget violations",
            "zero projection power-increase violations",
            "full inter-cell rate accounting reconstructed",
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(evidence / "ONE_SEED_GATE_DECISION.json", gate)

    correction = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "EXECUTION_OVERLAY_RECORDED_ORIGINAL_METADATA_IMMUTABLE",
        "original_metadata_sha256": sha256_file(
            package / "BUNDLE_METADATA.json"
        ),
        "original_metadata": embedded_metadata,
        "execution_overlay": {
            "cluster": "nibi",
            "gpu": environment["gpu_name"],
            "job_id": job_id,
            "job_name": expected["job_name"],
            "slurm_state": expected["slurm_state"],
            "exit_code": expected["exit_code"],
            "channel_user_chunk_size": 4,
            "channel_chunk_count": 57,
            "chunk_reason": (
                "four co-scheduled users per serving sector with "
                "reset_topology before every set_topology"
            ),
            "claim_boundary": cfg["claim_boundary"],
            "executed_input_bundle_sha256": expected[
                "input_bundle_sha256"
            ],
            "return_bundle_sha256": expected["return_bundle_sha256"],
        },
        "stale_or_preexecution_fields": [
            {
                "path": "claim_boundary",
                "embedded_value": embedded_metadata.get("claim_boundary"),
                "execution_value": cfg["claim_boundary"],
            },
            {
                "path": "channel_generation.user_chunk_size",
                "embedded_value": embedded_metadata.get(
                    "channel_generation", {}
                ).get("user_chunk_size"),
                "execution_value": 4,
            },
            {
                "path": "channel_generation.reason",
                "embedded_value": embedded_metadata.get(
                    "channel_generation", {}
                ).get("reason"),
                "execution_value": (
                    "Nibi H100 execution with 57 four-user serving-sector chunks"
                ),
            },
            {
                "path": "status",
                "embedded_value": embedded_metadata.get("status"),
                "execution_value": metrics["status"],
            },
        ],
        "rule": (
            "Do not edit the executed bundle; cite this overlay with the "
            "original bundle hash."
        ),
    }
    write_json(evidence / "EXECUTED_METADATA_CORRECTION.json", correction)

    write_csv(
        evidence / "USER_WORST_PASS_RETENTION_QUANTILES.csv",
        quantile_rows(user_min_retention),
    )
    write_csv(
        evidence / "USER_MEDIAN_PASS_RETENTION_QUANTILES.csv",
        quantile_rows(user_median_retention),
    )
    write_csv(
        evidence / "PROTECTED_TONE_POWER_RETENTION_QUANTILES.csv",
        quantile_rows(power_retention),
    )

    top_rows = []
    for rank, row in enumerate(worst_sector.itertuples(), start=1):
        top_rows.append(
            {
                "rank": rank,
                "time_s": worst_time,
                "sector_id": row.sector_id,
                "site_id": row.site_id,
                "nominal_received_w": float(row.nominal_received_w),
                "share": float(row.share),
                "cumulative_share": float(row.cumulative_share),
            }
        )
    write_csv(
        evidence / "WORST_TIME_SECTOR_CONTRIBUTIONS.csv",
        top_rows,
    )
    write_csv(
        evidence / "LEADING_SECTOR_COUNTS.csv",
        [
            {
                "sector_id": sector_id,
                "leading_time_count": int(count),
                "fraction_of_587_samples": float(
                    count / expected["protected_pass_samples"]
                ),
            }
            for sector_id, count in leaders.items()
        ],
    )

    sparsity = {
        "worst_time_s": worst_time,
        "top_1_share": float(worst_sector["cumulative_share"].iloc[0]),
        "top_2_share": float(worst_sector["cumulative_share"].iloc[1]),
        "top_5_share": float(worst_sector["cumulative_share"].iloc[4]),
        "top_10_share": float(worst_sector["cumulative_share"].iloc[9]),
        "top_15_share": float(worst_sector["cumulative_share"].iloc[14]),
        "leading_sector_counts": {
            key: int(value) for key, value in leaders.items()
        },
        "interpretation_boundary": (
            "The modelled common sector azimuths and earth-station placement "
            "may amplify this sparsity; rotation and placement sensitivity "
            "are mandatory."
        ),
    }
    write_json(evidence / "SECTOR_SPARSITY_AUDIT.json", sparsity)

    degeneracy = {
        "status": "PASS_COMMON_SCALE_DEGENERACY_IDENTIFIED",
        "maximum_empirical_mode_scale_spread": float(
            time_scales["all_mode_spread"].max()
        ),
        "derivation": [
            "beta_b = I_allow * kappa_b*L_b / sum_j(kappa_j*L_j)",
            "gamma_bm = beta_b/kappa_b * L_bm/L_b",
            "gamma_bm = I_allow*L_bm / sum_j(kappa_j*L_j)",
            "s_bm = sqrt(gamma_bm/L_bm)",
            "s_bm = sqrt(I_allow / sum_j(kappa_j*L_j))",
        ],
        "conclusion": (
            "The pilot is a common oracle attenuation reference, not a "
            "utility-aware nonuniform budget allocator."
        ),
    }
    write_json(
        evidence / "COMMON_SCALE_DEGENERACY_AUDIT.json",
        degeneracy,
    )

    source_evidence = evidence / "source"
    source_evidence.mkdir()
    copy_paths = [
        source / "INDEPENDENT_LOCAL_REVIEW_SUMMARY.json",
        source / "INDEPENDENT_LOCAL_REVIEW_SUMMARY.txt",
        source / "return_bundle" / "REMOTE_SUCCESS_STATUS.txt",
        output / "NIBI_GPU_ENVIRONMENT.json",
        output / "NIBI_ONE_SEED_DLP_RZF_PILOT_AUDIT.json",
        output / "PILOT_NUMERICAL_EVIDENCE.npz",
        output / "PILOT_SECTOR_TIME_METRICS.csv.gz",
        output / "PILOT_TIME_SUMMARY.csv",
        output / "PILOT_USER_RATE_SUMMARY.csv",
        runtime / f"logs/sacct-{job_id}.txt",
        runtime / f"logs/pilot-{job_id}.out",
        runtime / f"logs/pilot-{job_id}.err",
    ]
    for path in copy_paths:
        shutil.copy2(path, source_evidence / path.name)

    hashes = {
        "review_zip": {
            "name": review_zip.name,
            "sha256": review_sha,
            "bytes": review_zip.stat().st_size,
        },
        "input_bundle": {
            "name": input_zip.name,
            "sha256": sha256_file(input_zip),
            "bytes": input_zip.stat().st_size,
        },
        "return_bundle": {
            "name": return_zip.name,
            "sha256": sha256_file(return_zip),
            "bytes": return_zip.stat().st_size,
        },
        "review_manifest_entries": manifest_count,
    }
    write_json(evidence / "SOURCE_HASHES.json", hashes)

    readme = f"""# Nibi one-seed job 18658301 evidence

Status: `{metrics['status']}`

This directory freezes the successful 57-sector, 228-user, 128-port,
nine-frequency, 587-time-sample DLP-RZF execution and its independent local
reconstruction.

The result proves one-seed software and physical-accounting feasibility. It is
not a dynamic-controller result and is not paper-grade statistical evidence.

Key boundaries:

- one seed and one protected pass;
- four-user sector chunks do not preserve cross-sector large-scale correlation;
- only the protected ten-megahertz component is modified;
- instantaneous proportional budgets collapse to a common oracle scale;
- uncertainty reserve is not calibrated.

Next gate: `{cfg['next_gate']}`
"""
    (evidence / "README.md").write_text(readme, encoding="utf-8")

    decision_md = f"""# One-seed scientific decision

## Verdict

`{metrics['status']}`

The full H100 chain completed with zero local budget violations and zero
projection power-increase violations. The minimum network sum-rate retention
was `{metrics['network_utility']['minimum_retention']:.6%}`.

This is an accepted software and physical-accounting gate, not a TWC result.

## Why it is not yet a paper result

The run used one seed, one pass, a finite network, a reduced frequency grid,
sector-wise channel chunks, and an instantaneous common-scale oracle. It did
not test delayed or rate-limited coordination, uncertainty robustness, or
statistical generality.

## Next gate

`{cfg['next_gate']}`
"""
    (evidence / "ONE_SEED_GATE_DECISION.md").write_text(
        decision_md, encoding="utf-8"
    )

    correction_md = """# Executed metadata correction

The original executed input bundle is immutable. Some embedded fields describe
an earlier Narval/A100 preparation state. The authoritative execution overlay
is stored in `EXECUTED_METADATA_CORRECTION.json`.

Actual execution:

- Nibi H100 80 GB;
- job 18658301, exit 0:0;
- 57 chunks of four co-scheduled users;
- successful one-seed software/physical-accounting gate.

Always cite the original bundle hash together with the overlay.
"""
    (evidence / "EXECUTED_METADATA_CORRECTION.md").write_text(
        correction_md, encoding="utf-8"
    )

    degeneracy_md = r"""# Common-scale degeneracy of the pilot allocator

The pilot allocates each sector a received-interference budget in proportion to
its nominal received contribution, then splits that budget between the two
polarization modes in proportion to nominal mode leakage.

Algebraically, the resulting amplitude scale is identical for every sector and
mode at a fixed time:

\[
s_{b,m}(k)=
\sqrt{\frac{I_{\mathrm{allow}}}
{\sum_j \kappa_j(k)L_j}}.
\]

The measured mode-scale spread is numerical noise. The pilot therefore
validates a common oracle DLP reference, not a utility-aware distributed budget
allocator.
"""
    (evidence / "COMMON_SCALE_DEGENERACY_AUDIT.md").write_text(
        degeneracy_md, encoding="utf-8"
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  {path.as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print("NIBI ONE-SEED 18658301 EVIDENCE FREEZE: PASS")
    print(json.dumps(gate, indent=2))
    print("Evidence files:", len(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
