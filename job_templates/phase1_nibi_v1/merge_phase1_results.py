#!/usr/bin/env python3
"""Merge all 30 seed bundles and execute the preregistered analysis."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

import numpy as np
import pandas as pd

PRED = "robust_predictive_constrained_pf_with_sector_selective_fallback"
STATIC = "static_robust_constrained_pf_with_sector_selective_fallback"


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


def bootstrap_seed_clusters(values: np.ndarray, repetitions: int) -> dict:
    x = np.asarray(values, dtype=float)
    if x.shape != (30,):
        raise ValueError("bootstrap input must contain 30 seed-cluster effects")
    rng = np.random.default_rng(20260731)
    index = rng.integers(0, 30, size=(int(repetitions), 30))
    means = x[index].mean(axis=1)
    return {
        "point_estimate": float(x.mean()),
        "median": float(np.median(means)),
        "lower_95": float(np.quantile(means, 0.025)),
        "upper_95": float(np.quantile(means, 0.975)),
        "bootstrap_resamples": int(repetitions),
        "bootstrap_seed": 20260731,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-root", required=True)
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    seed_root = Path(args.seed_root).expanduser().resolve()
    package_root = Path(args.package_root).expanduser().resolve()
    output = Path(args.output_root).expanduser().resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    contract = json.loads(
        (package_root / "JOB_PACKAGE_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    campaign = json.loads(
        (package_root / "PHASE1_CAMPAIGN_CONTRACT_V3.json").read_text(
            encoding="utf-8"
        )
    )
    seeds = contract["campaign_seed_list"]
    all_cells = []
    all_primary = []
    seed_audits = []
    validator = package_root / "validate_seed_result.py"
    for seed in seeds:
        result_dir = seed_root / f"seed_{seed}/result"
        subprocess.run(
            [
                "python3",
                str(validator),
                "--result-dir",
                str(result_dir),
                "--package-contract",
                str(package_root / "JOB_PACKAGE_CONTRACT.json"),
            ],
            check=True,
        )
        cells = pd.read_csv(result_dir / "CELL_SUMMARY.csv")
        all_cells.append(cells)
        paired = pd.read_csv(result_dir / "PRIMARY_PAIRED_EFFECTS.csv")
        paired["campaign_seed"] = seed
        all_primary.append(paired)
        seed_audits.append(
            json.loads(
                (result_dir / "SEED_RESULT.json").read_text(
                    encoding="utf-8"
                )
            )
        )

    cells = pd.concat(all_cells, ignore_index=True)
    primary = pd.concat(all_primary, ignore_index=True)
    if len(cells) != 1200:
        raise RuntimeError(f"merged cell count is {len(cells)}, expected 1200")
    if len(primary) != 150:
        raise RuntimeError(
            f"merged primary paired count is {len(primary)}, expected 150"
        )
    cells.to_csv(output / "PHASE1_ALL_CELL_SUMMARY.csv", index=False)
    primary.to_csv(output / "PHASE1_PRIMARY_PAIRED_EFFECTS.csv", index=False)

    seed_effect = (
        primary.groupby("campaign_seed")[
            "predictive_minus_static_final_pf"
        ]
        .mean()
        .reindex(seeds)
    )
    if seed_effect.isna().any():
        raise RuntimeError("a seed-cluster primary effect is missing")
    seed_effect.reset_index().rename(
        columns={
            "predictive_minus_static_final_pf": (
                "mean_over_five_fixed_passes_predictive_minus_static_final_pf"
            )
        }
    ).to_csv(output / "PHASE1_SEED_CLUSTER_EFFECTS.csv", index=False)

    bootstrap = bootstrap_seed_clusters(
        seed_effect.to_numpy(float),
        int(campaign["statistics"]["bootstrap_resamples"]),
    )
    pass_effects = (
        primary.groupby("pass_slot")[
            "predictive_minus_static_final_pf"
        ]
        .agg(["mean", "median", "min", "max"])
        .reset_index()
    )
    pass_effects.to_csv(output / "PHASE1_PASS_SPECIFIC_EFFECTS.csv", index=False)

    leave_one = []
    for omitted in range(5):
        values = (
            primary.loc[primary["pass_slot"] != omitted]
            .groupby("campaign_seed")[
                "predictive_minus_static_final_pf"
            ]
            .mean()
            .reindex(seeds)
            .to_numpy(float)
        )
        summary = bootstrap_seed_clusters(values, 10000)
        summary["omitted_pass_slot"] = omitted
        leave_one.append(summary)
    pd.DataFrame(leave_one).to_csv(
        output / "PHASE1_LEAVE_ONE_PASS_OUT.csv", index=False
    )

    predictive = cells.loc[cells["method_id"] == PRED]
    hard_gates = {
        "zero_predictive_long_violation_seconds": int(
            predictive["long_violation_seconds"].sum()
        )
        == 0,
        "zero_predictive_short_violation_seconds": int(
            predictive["short_violation_seconds"].sum()
        )
        == 0,
        "zero_predictive_floor_violation_user_seconds": int(
            predictive["eligible_floor_violation_user_seconds"].sum()
        )
        == 0,
        "all_30_seed_results_present": len(seed_audits) == 30,
        "all_150_primary_cells_present": len(predictive) == 150,
    }
    all_hard = all(hard_gates.values())
    positive_ci = bootstrap["lower_95"] > 0.0
    go = all_hard and positive_ci

    summary = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_PHASE1_PRIMARY_GO_CONDITION"
            if go
            else "PHASE1_PRIMARY_GO_CONDITION_NOT_MET"
        ),
        "package_id": contract["package_id"],
        "candidate_zip_sha256": contract["candidate_v3"]["zip_sha256"],
        "seed_count": 30,
        "fixed_pass_count": 5,
        "cell_count": 1200,
        "primary_estimand": campaign["statistics"]["primary_estimand"],
        "bootstrap": bootstrap,
        "hard_gates": hard_gates,
        "all_hard_gates_pass": all_hard,
        "positive_lower_95_bound": positive_ci,
        "go_condition_met": go,
        "claim_scope": campaign["statistics"]["claim_scope"],
        "paper_result_boundary": (
            "CAMPAIGN_OUTPUT_REQUIRES_INDEPENDENT_REVIEW_BEFORE_PAPER_USE"
        ),
    }
    write_json(output / "PHASE1_MERGED_AUDIT.json", summary)

    files = {}
    for path in sorted(output.iterdir()):
        if path.is_file():
            files[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    write_json(output / "MERGED_FILE_MANIFEST.json", files)

    review = output / "FR3_PHASE1_MERGED_REVIEW_RETURN.zip"
    with zipfile.ZipFile(review, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.iterdir()):
            if path.is_file() and path != review:
                archive.write(path, path.name)
    with zipfile.ZipFile(review) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("merged review ZIP is corrupt")
    Path(str(review) + ".sha256").write_text(
        f"{sha256_file(review)}  {review.name}\n",
        encoding="utf-8",
    )

    print("PHASE-1 MERGE AND STATISTICAL ANALYSIS: PASS")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
