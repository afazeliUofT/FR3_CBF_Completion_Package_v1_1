#!/usr/bin/env python3
"""Strict validation of one phase-1 seed result."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

METHOD_IDS = [
    "robust_predictive_constrained_pf_with_sector_selective_fallback",
    "static_robust_constrained_pf_with_sector_selective_fallback",
    "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
    "delayed_myopic_constrained_pf_unshielded",
    "virtual_queue_unshielded",
    "uniform_protected_tone_backoff",
    "hard_spatial_null_or_exact_mute",
    "common_scale_instantaneous_noncausal_reference",
]
SAFE_IDS = {
    "robust_predictive_constrained_pf_with_sector_selective_fallback",
    "static_robust_constrained_pf_with_sector_selective_fallback",
    "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
    "uniform_protected_tone_backoff",
    "hard_spatial_null_or_exact_mute",
    "common_scale_instantaneous_noncausal_reference",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True)
    parser.add_argument("--package-contract", required=True)
    args = parser.parse_args()
    result = Path(args.result_dir).expanduser().resolve()
    package = json.loads(
        Path(args.package_contract).read_text(encoding="utf-8")
    )

    required = [
        "SEED_RESULT.json",
        "RESULT_FILE_MANIFEST.json",
        "CELL_SUMMARY.csv",
        "PRIMARY_PAIRED_EFFECTS.csv",
    ] + [f"PASS_{slot}_METHOD_TRACES.npz" for slot in range(5)]
    for name in required:
        if not (result / name).is_file():
            raise FileNotFoundError(result / name)

    audit = json.loads(
        (result / "SEED_RESULT.json").read_text(encoding="utf-8")
    )
    if audit["status"] != "PASS_PHASE1_SEED_RESULT_REVIEW_REQUIRED":
        raise ValueError("seed result status is wrong")
    if audit["package_id"] != package["package_id"]:
        raise ValueError("seed result package ID mismatch")
    if audit["candidate_zip_sha256"] != package["candidate_v3"][
        "zip_sha256"
    ]:
        raise ValueError("seed result candidate binding mismatch")
    if audit["cell_count"] != 40:
        raise ValueError("seed result does not have 40 method/pass cells")
    if audit["method_ids"] != METHOD_IDS:
        raise ValueError("seed result method order mismatch")
    if len(audit["pass_audits"]) != 5:
        raise ValueError("seed result does not have five pass audits")

    manifest = json.loads(
        (result / "RESULT_FILE_MANIFEST.json").read_text(encoding="utf-8")
    )
    for name, record in manifest.items():
        path = result / name
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"result manifest mismatch: {name}")

    cells = pd.read_csv(result / "CELL_SUMMARY.csv")
    if len(cells) != 40:
        raise ValueError("CELL_SUMMARY must have 40 rows")
    if sorted(cells["pass_slot"].unique().tolist()) != list(range(5)):
        raise ValueError("CELL_SUMMARY pass slots are wrong")
    for slot, frame in cells.groupby("pass_slot"):
        if frame["method_id"].tolist() != METHOD_IDS:
            raise ValueError(f"pass {slot}: method order mismatch")
    numeric = cells.select_dtypes(include=[np.number])
    if not np.isfinite(numeric.to_numpy(float)).all():
        raise ValueError("CELL_SUMMARY contains non-finite numeric values")

    predictive = cells.loc[
        cells["method_id"]
        == "robust_predictive_constrained_pf_with_sector_selective_fallback"
    ]
    if not (predictive["long_violation_seconds"] == 0).all():
        raise ValueError("predictive long-term hard gate failed")
    if not (predictive["short_violation_seconds"] == 0).all():
        raise ValueError("predictive short-term hard gate failed")
    if not (
        predictive["eligible_floor_violation_user_seconds"] == 0
    ).all():
        raise ValueError("predictive eligible-floor hard gate failed")

    for method_id in SAFE_IDS:
        frame = cells.loc[cells["method_id"] == method_id]
        if not (frame["long_violation_seconds"] == 0).all():
            raise ValueError(f"safe method long violation: {method_id}")
        if not (frame["short_violation_seconds"] == 0).all():
            raise ValueError(f"safe method short violation: {method_id}")

    paired = pd.read_csv(result / "PRIMARY_PAIRED_EFFECTS.csv")
    if len(paired) != 5:
        raise ValueError("PRIMARY_PAIRED_EFFECTS must have five rows")
    if not np.isfinite(
        paired["predictive_minus_static_final_pf"].to_numpy(float)
    ).all():
        raise ValueError("primary paired effect contains non-finite values")

    for slot in range(5):
        trace = np.load(result / f"PASS_{slot}_METHOD_TRACES.npz")
        if trace["method_ids"].tolist() != METHOD_IDS:
            raise ValueError(f"pass {slot}: trace method order mismatch")
        if trace["interval_lengths"].sum() != cells.loc[
            cells["pass_slot"] == slot,
            "protected_sample_count",
        ].iloc[0]:
            raise ValueError(f"pass {slot}: trace duration mismatch")

    print("PHASE-1 SEED RESULT STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "campaign_seed": audit["campaign_seed"],
                "cell_count": len(cells),
                "passes": 5,
                "methods": 8,
                "predictive_hard_gates": "PASS",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
