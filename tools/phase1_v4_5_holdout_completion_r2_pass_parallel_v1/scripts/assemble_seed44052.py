#!/usr/bin/env python3
"""Assemble five independently evaluated pass results into one canonical seed result."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pandas as pd

SEED = 44052
ARRAY_INDEX = 22
CANDIDATE = "candidate_v4_5_companion_aware_protected_subband_scheduling"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_pass(pass_dir: Path, slot: int) -> tuple[pd.DataFrame, dict, dict]:
    required = [
        "PASS_CELL_SUMMARY.csv",
        "PASS_AUDIT.json",
        "PASS_RESULT_METADATA.json",
        "PASS_RESULT_MANIFEST.json",
        f"PASS_{slot}_METHOD_TRACES.npz",
        f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz",
    ]
    for name in required:
        if not (pass_dir / name).is_file():
            raise FileNotFoundError(pass_dir / name)
    manifest = load_json(pass_dir / "PASS_RESULT_MANIFEST.json")
    for name, record in manifest.items():
        path = pass_dir / name
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"pass {slot} manifest mismatch: {name}")
    frame = pd.read_csv(pass_dir / "PASS_CELL_SUMMARY.csv")
    if len(frame) != 9 or frame["pass_slot"].unique().tolist() != [slot]:
        raise RuntimeError(f"pass {slot} cell summary mismatch")
    audit = load_json(pass_dir / "PASS_AUDIT.json")
    metadata = load_json(pass_dir / "PASS_RESULT_METADATA.json")
    if int(audit["pass_slot"]) != slot or int(metadata["pass_slot"]) != slot:
        raise RuntimeError(f"pass {slot} metadata mismatch")
    if metadata["status"] != "PASS_SEED44052_PROTECTED_PASS_COMPLETE":
        raise RuntimeError(f"pass {slot} incomplete")
    return frame, audit, metadata


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--job-package-root", required=True)
    p.add_argument("--seed-root", required=True)
    p.add_argument("--pass-output-root", required=True)
    p.add_argument("--completion-contract", required=True)
    p.add_argument("--authorization-file", required=True)
    args = p.parse_args()

    root = Path(args.job_package_root).resolve()
    seed_root = Path(args.seed_root).resolve()
    pass_root = Path(args.pass_output_root).resolve()
    contract = load_json(Path(args.completion_contract).resolve())
    if contract["seed"] != SEED or contract["pass_slots"] != [0, 1, 2, 3, 4]:
        raise RuntimeError("R2 assembly scope mismatch")

    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root))
    os.environ["PHASE1_AUTHORIZATION_FILE"] = str(Path(args.authorization_file).resolve())
    from authorization_guard import require_authorization
    import phase1_seed_worker as worker

    job_contract = load_json(root / "JOB_PACKAGE_CONTRACT.json")
    authorization = require_authorization(job_contract)
    if SEED not in authorization["allowed_seeds"]:
        raise RuntimeError("native authorization does not permit seed 44052")

    frames: list[pd.DataFrame] = []
    audits: list[dict] = []
    metadata: list[dict] = []
    for slot in range(5):
        frame, audit, meta = verify_pass(pass_root / f"pass_{slot}", slot)
        if frame["method_id"].tolist() != worker.METHOD_IDS:
            raise RuntimeError(f"pass {slot} method order mismatch")
        frames.append(frame)
        audits.append(audit)
        metadata.append(meta)

    base = metadata[0]
    invariant_keys = [
        "package_id",
        "candidate_source_manifest_sha256",
        "channel_record_sha256",
        "architecture_id",
        "rf_chains",
        "analog_phase_bits",
        "nominal_total_sum_se_bps_hz",
    ]
    for meta in metadata[1:]:
        for key in invariant_keys:
            if meta[key] != base[key]:
                raise RuntimeError(f"pass metadata invariant mismatch: {key}")

    temp = seed_root / "result_r2_assembly_tmp"
    final = seed_root / "result"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    for slot in range(5):
        source = pass_root / f"pass_{slot}"
        for name in (
            f"PASS_{slot}_METHOD_TRACES.npz",
            f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz",
        ):
            shutil.copy2(source / name, temp / name)

    cells = pd.concat(frames, ignore_index=True)
    cells.to_csv(temp / "CELL_SUMMARY.csv", index=False)
    paired_rows = []
    for pass_slot, frame in cells.groupby("pass_slot", sort=True):
        indexed = frame.set_index("method_id")
        candidate_row = indexed.loc[CANDIDATE]
        static_row = indexed.loc[
            "static_robust_constrained_pf_with_sector_selective_fallback"
        ]
        predictive_row = indexed.loc[
            "robust_predictive_constrained_pf_with_sector_selective_fallback"
        ]
        paired_rows.append(
            {
                "pass_slot": int(pass_slot),
                "candidate_minus_static_final_pf": float(
                    candidate_row["final_moving_pf_utility"]
                    - static_row["final_moving_pf_utility"]
                ),
                "candidate_minus_static_duration_mean_pf": float(
                    candidate_row["duration_weighted_mean_moving_pf_utility"]
                    - static_row["duration_weighted_mean_moving_pf_utility"]
                ),
                "candidate_minus_predictive_final_pf": float(
                    candidate_row["final_moving_pf_utility"]
                    - predictive_row["final_moving_pf_utility"]
                ),
                "candidate_minus_predictive_duration_mean_pf": float(
                    candidate_row["duration_weighted_mean_moving_pf_utility"]
                    - predictive_row["duration_weighted_mean_moving_pf_utility"]
                ),
            }
        )
    pd.DataFrame(paired_rows).to_csv(temp / "PRIMARY_PAIRED_EFFECTS.csv", index=False)

    overlay = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "IMPLEMENTATION_CAPACITY_REPAIR_NOT_ALGORITHM_TUNING",
        "orchestration_classification": "PASS_PARALLEL_ORCHESTRATION_ONLY",
        "seed": SEED,
        "original_mode_count_guard": 4096,
        "observed_required_mode_count": 7776,
        "runtime_mode_count_guard": 8192,
        "pass_slots": [0, 1, 2, 3, 4],
        "scientific_source_files_modified": False,
        "action_library_definition_changed": False,
        "objective_changed": False,
        "constraints_changed": False,
        "floor_changed": False,
        "tolerances_changed": False,
        "new_seed_or_channel_generated": False,
        "channel_reused": True,
        "gpu_requested": False,
        "claim_boundary": (
            "FRESH_HOLDOUT_COMPLETION_AFTER_NONSCIENTIFIC_CAPACITY_AND_"
            "PASS_PARALLEL_ORCHESTRATION_REPAIR; NOT_CALIBRATION; NOT_COMPLIANCE"
        ),
    }
    worker.write_json(temp / "IMPLEMENTATION_CAPACITY_OVERLAY.json", overlay)

    result_files = {}
    for path in sorted(temp.iterdir()):
        if path.is_file():
            result_files[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    channel_record = load_json(seed_root / "channel" / "CHANNEL_RECORD.json")
    audit = {
        "schema_version": 1,
        "status": "PENDING_CANDIDATE_HARD_GATE_CLASSIFICATION",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_seed": SEED,
        "array_index": ARRAY_INDEX,
        "package_id": job_contract["package_id"],
        "candidate_source_manifest_sha256": job_contract["candidate_v4_5"][
            "source_manifest_sha256"
        ],
        "authorization_token_sha256": authorization["authorization_file_sha256"],
        "execution_stage": "FRESH_V4_5_HOLDOUT_30_SEED",
        "channel_record": channel_record,
        "architecture": {
            "architecture_id": base["architecture_id"],
            "rf_chains": int(base["rf_chains"]),
            "analog_phase_bits": int(base["analog_phase_bits"]),
            "full_load_audit": base["architecture_audit"],
            "nominal_total_sum_se_bps_hz": float(
                base["nominal_total_sum_se_bps_hz"]
            ),
        },
        "pass_audits": audits,
        "cell_count": len(cells),
        "method_ids": worker.METHOD_IDS,
        "result_files": result_files,
        "runtime_seconds": float(sum(float(item["elapsed_seconds"]) for item in metadata)),
        "execution_boundary": (
            "DECLARED_ENGINEERING_SCENARIOS_NOT_CALIBRATION_NOT_COMPLIANCE"
        ),
        "implementation_capacity_overlay": overlay,
        "holdout_completion_classification": (
            "VALID_FRESH_HOLDOUT_SEED_AFTER_NONSCIENTIFIC_CAPACITY_AND_"
            "PASS_PARALLEL_ORCHESTRATION_REPAIR"
        ),
    }
    candidate_cells = cells.loc[cells["method_id"] == CANDIDATE]
    candidate_hard_pass = bool(
        int(candidate_cells["long_violation_seconds"].sum()) == 0
        and int(candidate_cells["short_violation_seconds"].sum()) == 0
        and int(candidate_cells["eligible_floor_violation_user_seconds"].sum()) == 0
        and int(candidate_cells["eligible_floor_violation_user_intervals"].sum()) == 0
        and float(
            candidate_cells["candidate_maximum_strict_post_mode_power_ratio"].max()
        )
        <= 1.0 + 1e-10
        and all(
            record["candidate_hard_gates"]["strict_local_scope_gate"] == "PASS"
            and record["candidate_hard_gates"][
                "strict_post_mode_selected_power_gate"
            ]
            == "PASS"
            and record["candidate_hard_gates"]["q0_envelope_deployable_actions"]
            == 0
            and record["candidate_hard_gates"]["unresolved_deployable_intervals"]
            == 0
            and record["candidate_hard_gates"]["network_wide_shutdown_intervals"]
            == 0
            for record in audits
        )
    )
    audit["status"] = (
        "PASS_FRESH_V4_5_HOLDOUT_SEED_ALL_HARD_GATES"
        if candidate_hard_pass
        else "VALID_FRESH_V4_5_HOLDOUT_SEED_FEASIBILITY_CONDITIONED_FLOOR"
    )
    audit["candidate_hard_gates_pass"] = candidate_hard_pass
    audit["scientific_exit_code"] = 0 if candidate_hard_pass else 42
    worker.write_json(temp / "SEED_RESULT.json", audit)

    result_files["SEED_RESULT.json"] = {
        "bytes": (temp / "SEED_RESULT.json").stat().st_size,
        "sha256": sha256_file(temp / "SEED_RESULT.json"),
    }
    worker.write_json(temp / "RESULT_FILE_MANIFEST.json", result_files)

    backup = seed_root / "result_before_r2"
    if backup.exists():
        shutil.rmtree(backup)
    if final.exists():
        final.rename(backup)
    temp.rename(final)

    print("SEED44052_PASS_PARALLEL_ASSEMBLY=PASS")
    print("SEED44052_PASS_RESULT_COUNT=5")
    print("SEED44052_CELL_COUNT=45")
    print("SEED44052_SCIENTIFIC_EXIT_CODE=" + str(audit["scientific_exit_code"]))
    print("SEED44052_CANDIDATE_HARD_GATES_PASS=" + str(candidate_hard_pass))
    print("SCIENTIFIC_SOURCE_FILES_MODIFIED=NO")
    print("ACTION_LIBRARY_DEFINITION_CHANGED=NO")
    print("CHANNEL_REGENERATION=NO")
    print("GPU_REQUESTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
