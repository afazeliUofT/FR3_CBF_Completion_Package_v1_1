#!/usr/bin/env python3
"""Run one excluded Nibi deployment smoke using the immutable phase-1 package.

This script imports the reviewed immutable seed-worker implementation but does
not call its campaign-only ``main`` entry point. The smoke seed is outside the
confirmatory list and every output is explicitly excluded from phase-1
confirmatory analysis.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time

import numpy as np
import pandas as pd

SMOKE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SMOKE_ROOT))

from validate_smoke_token import validate as validate_token  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_array(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_immutable_worker(job_root: Path):
    sys.path.insert(0, str(job_root))
    sys.path.insert(0, str(job_root / "src"))
    source = job_root / "phase1_seed_worker.py"
    if not source.is_file():
        raise FileNotFoundError(source)
    spec = importlib.util.spec_from_file_location(
        "immutable_phase1_seed_worker",
        source,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load immutable seed worker: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-package-root", required=True)
    parser.add_argument("--smoke-contract", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--environment-lock", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--smoke-package-sha256", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--smoke-seed", type=int, required=True)
    args = parser.parse_args()

    job_root = Path(args.job_package_root).expanduser().resolve()
    contract_path = Path(args.smoke_contract).expanduser().resolve()
    token_path = Path(args.token).expanduser().resolve()
    env_lock_path = Path(args.environment_lock).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    token = validate_token(
        token_path,
        env_lock_path,
        contract_path,
        args.source_commit,
        args.smoke_package_sha256,
    )
    seed = int(args.smoke_seed)
    if seed != int(contract["smoke_seed"]):
        raise ValueError("requested smoke seed differs from the reviewed contract")
    if seed in {int(value) for value in contract["confirmatory_seed_list"]}:
        raise ValueError("smoke seed overlaps the confirmatory campaign")
    if seed != int(token["smoke_seed"]):
        raise ValueError("smoke seed differs from the authorization token")

    worker = load_immutable_worker(job_root)
    immutable_contract = json.loads(
        (job_root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8")
    )
    if immutable_contract["package_id"] != contract["job_package_id"]:
        raise ValueError("immutable package ID mismatch")
    if immutable_contract["campaign_seed_list"] != contract[
        "confirmatory_seed_list"
    ]:
        raise ValueError("confirmatory seed list differs from immutable package")
    if seed in immutable_contract["campaign_seed_list"]:
        raise ValueError("noncampaign smoke seed unexpectedly enters campaign list")

    smoke_root = output_root / f"noncampaign_smoke_seed_{seed}"
    channel_root = smoke_root / "channel"
    result_root = smoke_root / "result"
    pass_temp = smoke_root / "pass_extract"
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True)

    started = time.perf_counter()
    channel_record = worker.generate_channel(seed, channel_root)
    data = worker.load_channel(channel_root)
    campaign_contract = json.loads(
        (job_root / "PHASE1_CAMPAIGN_CONTRACT_V3.json").read_text(
            encoding="utf-8"
        )
    )
    pass_roots = [
        worker.extract_pass(slot, pass_temp)
        for slot in range(5)
    ]
    pass_lengths = [
        len(np.load(path / "protected_time_s.npy", allow_pickle=False))
        for path in pass_roots
    ]
    (
        architecture,
        _h_effective,
        full_state,
        architecture_audit,
        schedules,
        state_cache,
    ) = worker.create_states(data, campaign_contract, pass_lengths)

    result_root.mkdir(parents=True)
    cell_rows: list[dict[str, object]] = []
    pass_audits: list[dict[str, object]] = []
    for slot, pass_root in enumerate(pass_roots):
        rows, audit = worker.pass_evaluation(
            slot,
            pass_root,
            data,
            campaign_contract,
            architecture,
            full_state,
            schedules[slot],
            state_cache,
            result_root,
        )
        for row in rows:
            row.update(
                {
                    "campaign_seed": seed,
                    "smoke_seed": seed,
                    "array_index": -1,
                    "confirmatory_analysis_included": False,
                    "analysis_scope": (
                        "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
                    ),
                    "deployment_smoke": True,
                }
            )
        audit.update(
            {
                "smoke_seed": seed,
                "confirmatory_analysis_included": False,
                "analysis_scope": (
                    "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
                ),
            }
        )
        cell_rows.extend(rows)
        pass_audits.append(audit)

    cells = pd.DataFrame(cell_rows)
    if len(cells) != 40:
        raise RuntimeError(f"smoke result has {len(cells)} cells, expected 40")
    cells.to_csv(result_root / "CELL_SUMMARY.csv", index=False)

    pred = (
        "robust_predictive_constrained_pf_with_sector_selective_fallback"
    )
    static = (
        "static_robust_constrained_pf_with_sector_selective_fallback"
    )
    primary = (
        cells.loc[cells["method_id"].isin({pred, static})]
        .pivot(
            index="pass_slot",
            columns="method_id",
            values="final_moving_pf_utility",
        )
    )
    primary["predictive_minus_static_final_pf"] = (
        primary[pred] - primary[static]
    )
    primary = primary.reset_index()
    primary["smoke_seed"] = seed
    primary["confirmatory_analysis_included"] = False
    primary["analysis_scope"] = (
        "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
    )
    primary.to_csv(
        result_root / "PRIMARY_PAIRED_EFFECTS.csv",
        index=False,
    )

    channel_fingerprints = {
        "schema_version": 1,
        "smoke_seed": seed,
        "user_seed": 2 * seed,
        "channel_seed": 2 * seed + 1,
        "frequency_response_sha256_array_bytes": channel_record[
            "frequency_response_sha256_array_bytes"
        ],
        "channel_generation_record": channel_record["channel_generation"],
        "channel_file_records": channel_record["files"],
        "confirmatory_analysis_included": False,
    }
    write_json(
        result_root / "SMOKE_CHANNEL_FINGERPRINTS.json",
        channel_fingerprints,
    )

    result_files: dict[str, dict[str, object]] = {}
    for path in sorted(result_root.iterdir()):
        if path.is_file():
            result_files[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }

    predictive = cells.loc[cells["method_id"] == pred]
    reactive = cells.loc[
        cells["method_id"]
        == "delayed_myopic_constrained_pf_with_reactive_sector_fallback"
    ]
    unshielded = cells.loc[
        cells["method_id"] == "delayed_myopic_constrained_pf_unshielded"
    ]
    virtual = cells.loc[
        cells["method_id"] == "virtual_queue_unshielded"
    ]
    audit = {
        "schema_version": 1,
        "status": (
            "PASS_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_"
            "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
        ),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "deployment_smoke": True,
        "smoke_seed": seed,
        "user_seed": 2 * seed,
        "channel_seed": 2 * seed + 1,
        "confirmatory_analysis_included": False,
        "analysis_scope": "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS",
        "full_campaign_execution_authorized": False,
        "merge_authorized": False,
        "package_id": immutable_contract["package_id"],
        "job_package_sha256": contract["job_package_sha256"],
        "candidate_v3_sha256": immutable_contract["candidate_v3"][
            "zip_sha256"
        ],
        "reviewed_job_package_commit": contract[
            "reviewed_job_package_commit"
        ],
        "job_package_review_commit": contract[
            "job_package_review_commit"
        ],
        "smoke_package_sha256": args.smoke_package_sha256,
        "smoke_source_commit": args.source_commit,
        "environment_lock_sha256": sha256_file(env_lock_path),
        "authorization_token_sha256": sha256_file(token_path),
        "channel_record": channel_record,
        "architecture": {
            "architecture_id": architecture.architecture_id,
            "rf_chains": architecture.rf_chains,
            "analog_phase_bits": architecture.analog_phase_bits,
            "full_load_audit": architecture_audit,
            "nominal_total_sum_se_bps_hz": float(
                full_state.nominal_total_rate.sum()
            ),
        },
        "pass_audits": pass_audits,
        "cell_count": len(cells),
        "method_ids": list(worker.METHOD_IDS),
        "primary_paired_effects": {
            "mean_over_five_passes": float(
                primary["predictive_minus_static_final_pf"].mean()
            ),
            "minimum_over_five_passes": float(
                primary["predictive_minus_static_final_pf"].min()
            ),
            "maximum_over_five_passes": float(
                primary["predictive_minus_static_final_pf"].max()
            ),
        },
        "scientific_gate_summary": {
            "predictive_long_violation_seconds": int(
                predictive["long_violation_seconds"].sum()
            ),
            "predictive_short_violation_seconds": int(
                predictive["short_violation_seconds"].sum()
            ),
            "predictive_floor_violation_user_seconds": int(
                predictive[
                    "eligible_floor_violation_user_seconds"
                ].sum()
            ),
            "reactive_myopic_long_violation_seconds": int(
                reactive["long_violation_seconds"].sum()
            ),
            "unshielded_myopic_long_violation_seconds": int(
                unshielded["long_violation_seconds"].sum()
            ),
            "virtual_queue_long_violation_seconds": int(
                virtual["long_violation_seconds"].sum()
            ),
        },
        "result_files": result_files,
        "runtime_seconds": time.perf_counter() - started,
        "paper_claim_boundary": (
            "NONCAMPAIGN_DEPLOYMENT_SMOKE_NOT_PHASE1_RESULT_"
            "NOT_CALIBRATION_NOT_COMPLIANCE"
        ),
    }
    write_json(result_root / "NONCAMPAIGN_SMOKE_RESULT.json", audit)

    result_files["NONCAMPAIGN_SMOKE_RESULT.json"] = {
        "bytes": (result_root / "NONCAMPAIGN_SMOKE_RESULT.json").stat().st_size,
        "sha256": sha256_file(
            result_root / "NONCAMPAIGN_SMOKE_RESULT.json"
        ),
    }
    write_json(
        result_root / "SMOKE_RESULT_FILE_MANIFEST.json",
        result_files,
    )

    print("NONCAMPAIGN NIBI DEPLOYMENT SMOKE COMPUTATION: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
