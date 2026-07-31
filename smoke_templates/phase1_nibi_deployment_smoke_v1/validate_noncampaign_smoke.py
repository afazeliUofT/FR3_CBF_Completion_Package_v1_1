#!/usr/bin/env python3
"""Strict validation of one excluded noncampaign Nibi deployment smoke."""
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
    parser.add_argument("--smoke-contract", required=True)
    parser.add_argument("--environment-lock", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    root = Path(args.result_dir).expanduser().resolve()
    contract = json.loads(
        Path(args.smoke_contract).read_text(encoding="utf-8")
    )
    env_lock = Path(args.environment_lock).expanduser().resolve()
    token = Path(args.token).expanduser().resolve()
    required = [
        "NONCAMPAIGN_SMOKE_RESULT.json",
        "SMOKE_RESULT_FILE_MANIFEST.json",
        "CELL_SUMMARY.csv",
        "PRIMARY_PAIRED_EFFECTS.csv",
        "SMOKE_CHANNEL_FINGERPRINTS.json",
    ] + [f"PASS_{slot}_METHOD_TRACES.npz" for slot in range(5)]
    for name in required:
        if not (root / name).is_file():
            raise FileNotFoundError(root / name)

    audit = json.loads(
        (root / "NONCAMPAIGN_SMOKE_RESULT.json").read_text(
            encoding="utf-8"
        )
    )
    if audit["status"] != (
        "PASS_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_"
        "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
    ):
        raise ValueError("deployment smoke status is wrong")
    if audit["deployment_smoke"] is not True:
        raise ValueError("deployment smoke flag is false")
    if audit["confirmatory_analysis_included"] is not False:
        raise ValueError("smoke result entered confirmatory analysis")
    if audit["analysis_scope"] != (
        "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
    ):
        raise ValueError("smoke analysis scope is wrong")
    if audit["full_campaign_execution_authorized"] is not False:
        raise ValueError("smoke result authorizes the full campaign")
    if audit["merge_authorized"] is not False:
        raise ValueError("smoke result authorizes merge")
    if int(audit["smoke_seed"]) != int(contract["smoke_seed"]):
        raise ValueError("smoke seed mismatch")
    if int(audit["smoke_seed"]) in {
        int(value) for value in contract["confirmatory_seed_list"]
    }:
        raise ValueError("smoke seed overlaps confirmatory seeds")
    if audit["package_id"] != contract["job_package_id"]:
        raise ValueError("job-package ID mismatch")
    if audit["job_package_sha256"] != contract["job_package_sha256"]:
        raise ValueError("job-package SHA-256 mismatch")
    if audit["candidate_v3_sha256"] != contract["candidate_v3_sha256"]:
        raise ValueError("candidate-v3 SHA-256 mismatch")
    if audit["environment_lock_sha256"] != sha256_file(env_lock):
        raise ValueError("environment-lock SHA-256 mismatch")
    if audit["authorization_token_sha256"] != sha256_file(token):
        raise ValueError("smoke-token SHA-256 mismatch")
    if audit["cell_count"] != 40 or audit["method_ids"] != METHOD_IDS:
        raise ValueError("smoke method/cell dimensions are wrong")
    if len(audit["pass_audits"]) != 5:
        raise ValueError("smoke pass-audit count is wrong")

    manifest = json.loads(
        (root / "SMOKE_RESULT_FILE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    for name, record in manifest.items():
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"smoke result manifest mismatch: {name}")

    cells = pd.read_csv(root / "CELL_SUMMARY.csv")
    if len(cells) != 40:
        raise ValueError("CELL_SUMMARY must contain 40 rows")
    if sorted(cells["pass_slot"].unique().tolist()) != list(range(5)):
        raise ValueError("smoke pass slots are wrong")
    if not (cells["confirmatory_analysis_included"] == False).all():  # noqa: E712
        raise ValueError("a smoke cell entered confirmatory analysis")
    if not (
        cells["analysis_scope"]
        == "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
    ).all():
        raise ValueError("a smoke cell has the wrong analysis scope")
    if sorted(cells["method_id"].unique().tolist()) != sorted(METHOD_IDS):
        raise ValueError("smoke method set is wrong")
    for slot, frame in cells.groupby("pass_slot"):
        if frame["method_id"].tolist() != METHOD_IDS:
            raise ValueError(f"pass {slot}: method order is wrong")
    numeric = cells.select_dtypes(include=[np.number])
    if not np.isfinite(numeric.to_numpy(float)).all():
        raise ValueError("smoke cells contain non-finite numeric values")

    predictive = cells.loc[
        cells["method_id"]
        == "robust_predictive_constrained_pf_with_sector_selective_fallback"
    ]
    if not (predictive["long_violation_seconds"] == 0).all():
        raise ValueError("predictive long-term hard gate failed in smoke")
    if not (predictive["short_violation_seconds"] == 0).all():
        raise ValueError("predictive short-term hard gate failed in smoke")
    if not (
        predictive["eligible_floor_violation_user_seconds"] == 0
    ).all():
        raise ValueError("predictive floor hard gate failed in smoke")

    for method_id in SAFE_IDS:
        frame = cells.loc[cells["method_id"] == method_id]
        if not (frame["long_violation_seconds"] == 0).all():
            raise ValueError(f"safe method long violation: {method_id}")
        if not (frame["short_violation_seconds"] == 0).all():
            raise ValueError(f"safe method short violation: {method_id}")

    paired = pd.read_csv(root / "PRIMARY_PAIRED_EFFECTS.csv")
    if len(paired) != 5:
        raise ValueError("smoke primary paired table must have five rows")
    if not (paired["confirmatory_analysis_included"] == False).all():  # noqa: E712
        raise ValueError("paired smoke effects entered confirmatory analysis")
    if not np.isfinite(
        paired["predictive_minus_static_final_pf"].to_numpy(float)
    ).all():
        raise ValueError("smoke paired effects contain non-finite values")

    for slot in range(5):
        trace = np.load(
            root / f"PASS_{slot}_METHOD_TRACES.npz",
            allow_pickle=False,
        )
        if trace["method_ids"].tolist() != METHOD_IDS:
            raise ValueError(f"pass {slot}: trace method order is wrong")
        expected_duration = int(
            cells.loc[
                cells["pass_slot"] == slot,
                "protected_sample_count",
            ].iloc[0]
        )
        if int(trace["interval_lengths"].sum()) != expected_duration:
            raise ValueError(f"pass {slot}: trace duration mismatch")

    channel = json.loads(
        (root / "SMOKE_CHANNEL_FINGERPRINTS.json").read_text(
            encoding="utf-8"
        )
    )
    seed = int(contract["smoke_seed"])
    if channel["smoke_seed"] != seed:
        raise ValueError("channel fingerprint smoke seed mismatch")
    if channel["user_seed"] != 2 * seed:
        raise ValueError("channel fingerprint user seed mismatch")
    if channel["channel_seed"] != 2 * seed + 1:
        raise ValueError("channel fingerprint channel seed mismatch")
    if channel["confirmatory_analysis_included"] is not False:
        raise ValueError("channel fingerprint entered confirmatory analysis")

    print("NONCAMPAIGN NIBI DEPLOYMENT SMOKE STRICT VALIDATION: PASS")
    print(json.dumps(
        {
            "smoke_seed": seed,
            "cells": len(cells),
            "passes": 5,
            "methods": 8,
            "predictive_hard_gates": "PASS",
            "confirmatory_analysis_included": False,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
