#!/usr/bin/env python3
"""Evaluate exactly one protected pass for holdout seed 44052.

This is orchestration-only pass parallelization. The frozen candidate, all eight
comparators, the floor, EESS constraints, q commands, RZF directions, solver
tolerances, and declared 7776-mode scheduling library are unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

import numpy as np
import pandas as pd

SEED = 44052
ARRAY_INDEX = 22
ORIGINAL_CAP = 4096
RUNTIME_CAP = 8192
REQUIRED_MODE_COUNT = 7776


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--job-package-root", required=True)
    p.add_argument("--seed-root", required=True)
    p.add_argument("--pass-output-root", required=True)
    p.add_argument("--pass-slot", required=True, type=int)
    p.add_argument("--completion-contract", required=True)
    p.add_argument("--authorization-file", required=True)
    args = p.parse_args()

    slot = int(args.pass_slot)
    if slot not in range(5):
        raise ValueError(f"invalid pass slot {slot}")
    root = Path(args.job_package_root).resolve()
    seed_root = Path(args.seed_root).resolve()
    output = Path(args.pass_output_root).resolve() / f"pass_{slot}"
    contract = json.loads(Path(args.completion_contract).read_text(encoding="utf-8"))
    if contract["seed"] != SEED or contract["array_index"] != ARRAY_INDEX:
        raise RuntimeError("R2 seed/array-index contract mismatch")
    if contract["mode_capacity"] != {
        "classification": "IMPLEMENTATION_CAPACITY_REPAIR_NOT_ALGORITHM_TUNING",
        "original_guard": ORIGINAL_CAP,
        "required_count": REQUIRED_MODE_COUNT,
        "runtime_guard": RUNTIME_CAP,
    }:
        raise RuntimeError("R2 mode-capacity contract mismatch")

    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root))
    os.environ["PHASE1_AUTHORIZATION_FILE"] = str(Path(args.authorization_file).resolve())
    from authorization_guard import require_authorization

    job_contract = json.loads((root / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8"))
    authorization = require_authorization(job_contract)
    if SEED not in authorization["allowed_seeds"]:
        raise RuntimeError("native authorization does not permit seed 44052")

    from fr3_cbf import companion_aware_scheduler as scheduler

    if int(scheduler.MAX_MODE_COUNT) != ORIGINAL_CAP:
        raise RuntimeError(f"unexpected frozen MAX_MODE_COUNT={scheduler.MAX_MODE_COUNT}")
    scheduler.MAX_MODE_COUNT = RUNTIME_CAP
    if int(scheduler.MAX_MODE_COUNT) != RUNTIME_CAP:
        raise RuntimeError("runtime capacity override failed")

    import phase1_seed_worker as worker

    channel_root = seed_root / "channel"
    channel_record_path = channel_root / "CHANNEL_RECORD.json"
    if not channel_record_path.is_file():
        raise FileNotFoundError(channel_record_path)
    channel_record = json.loads(channel_record_path.read_text(encoding="utf-8"))
    if int(channel_record["campaign_seed"]) != SEED:
        raise RuntimeError("preserved channel seed mismatch")

    started = time.perf_counter()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    temp = output / "pass_extract"

    data = worker.load_channel(channel_root)
    campaign_contract = json.loads(
        (root / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json").read_text(encoding="utf-8")
    )
    pass_roots = [worker.extract_pass(index, temp) for index in range(5)]
    pass_lengths = [
        len(np.load(path / "protected_time_s.npy")) for path in pass_roots
    ]
    (
        architecture,
        _h_effective,
        full_state,
        architecture_audit,
        schedules,
        state_cache,
    ) = worker.create_states(data, campaign_contract, pass_lengths)

    print(f"SEED44052_PASS_BEGIN={slot}", flush=True)
    print("MAX_MODE_COUNT_RUNTIME=8192", flush=True)
    rows, audit = worker.pass_evaluation(
        slot,
        pass_roots[slot],
        data,
        campaign_contract,
        architecture,
        full_state,
        schedules[slot],
        state_cache,
        output,
    )
    for row in rows:
        row["campaign_seed"] = SEED
        row["array_index"] = ARRAY_INDEX
    pd.DataFrame(rows).to_csv(output / "PASS_CELL_SUMMARY.csv", index=False)
    worker.write_json(output / "PASS_AUDIT.json", audit)
    metadata = {
        "schema_version": 1,
        "status": "PASS_SEED44052_PROTECTED_PASS_COMPLETE",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "array_index": ARRAY_INDEX,
        "pass_slot": slot,
        "package_id": job_contract["package_id"],
        "candidate_source_manifest_sha256": job_contract["candidate_v4_5"]["source_manifest_sha256"],
        "authorization_token_sha256": authorization["authorization_file_sha256"],
        "mode_capacity_original": ORIGINAL_CAP,
        "mode_capacity_runtime": RUNTIME_CAP,
        "required_mode_count": REQUIRED_MODE_COUNT,
        "channel_reused": True,
        "channel_regenerated": False,
        "gpu_requested": False,
        "scientific_source_files_modified": False,
        "action_library_definition_changed": False,
        "elapsed_seconds": time.perf_counter() - started,
        "architecture_id": architecture.architecture_id,
        "rf_chains": architecture.rf_chains,
        "analog_phase_bits": architecture.analog_phase_bits,
        "architecture_audit": architecture_audit,
        "nominal_total_sum_se_bps_hz": float(full_state.nominal_total_rate.sum()),
        "channel_record_sha256": sha256_file(channel_record_path),
    }
    worker.write_json(output / "PASS_RESULT_METADATA.json", metadata)

    shutil.rmtree(temp, ignore_errors=True)
    manifest = {}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "PASS_RESULT_MANIFEST.json":
            manifest[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    worker.write_json(output / "PASS_RESULT_MANIFEST.json", manifest)
    print(f"SEED44052_PASS_COMPLETE={slot}", flush=True)
    print(f"SEED44052_PASS_ELAPSED_SECONDS={metadata['elapsed_seconds']}", flush=True)
    print("CHANNEL_REGENERATION=NO", flush=True)
    print("GPU_REQUESTED=NO", flush=True)
    print("SCIENTIFIC_SOURCE_FILES_MODIFIED=NO", flush=True)
    print("ACTION_LIBRARY_DEFINITION_CHANGED=NO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
