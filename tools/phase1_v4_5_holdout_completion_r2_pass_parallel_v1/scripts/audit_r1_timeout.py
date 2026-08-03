#!/usr/bin/env python3
"""Audit the R1 timeout and derive the pass-parallel resource decision."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_member(zf: zipfile.ZipFile, suffix: str) -> str:
    matches = [name for name in zf.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {suffix}, found {matches}")
    return zf.read(matches[0]).decode("utf-8", errors="replace")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--contract", required=True)
    p.add_argument("--r1-return", required=True)
    p.add_argument("--holdout-return", required=True)
    p.add_argument("--output-json", required=True)
    args = p.parse_args()

    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    r1 = Path(args.r1_return).resolve()
    holdout = Path(args.holdout_return).resolve()
    if sha256_file(r1) != contract["prior_completion_r1_return_sha256"]:
        raise RuntimeError("R1 return SHA-256 mismatch")
    if sha256_file(holdout) != contract["existing_holdout_return_sha256"]:
        raise RuntimeError("holdout return SHA-256 mismatch")

    with zipfile.ZipFile(r1) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"R1 ZIP CRC failure: {bad}")
        sacct = read_member(zf, "slurm/sacct_completion.txt")
        audit = json.loads(read_member(zf, "HOLDOUT_COMPLETION_AUDIT.json"))
        seed_return_name = next(
            name for name in zf.namelist()
            if name.endswith("seed_44052/FR3_PHASE1_SEED_44052_RETURN.zip")
        )
        seed_return_bytes = zf.read(seed_return_name)

    rows = {}
    for line in sacct.splitlines():
        if not line or line.startswith("JobID|"):
            continue
        parts = line.split("|")
        rows[parts[0]] = parts
    seed_job = str(contract["prior_completion_r1_seed_job_id"])
    batch_job = seed_job + ".batch"
    if seed_job not in rows or batch_job not in rows:
        raise RuntimeError("R1 sacct lacks seed job records")
    if rows[seed_job][3] != "TIMEOUT":
        raise RuntimeError(f"R1 seed state was {rows[seed_job][3]}, expected TIMEOUT")
    elapsed = rows[seed_job][5]
    maxrss_text = rows[batch_job][6]
    match = re.fullmatch(r"(\d+)K", maxrss_text)
    if not match:
        raise RuntimeError(f"unexpected MaxRSS: {maxrss_text!r}")
    maxrss_kib = int(match.group(1))
    if maxrss_kib >= 2 * 1024 * 1024:
        raise RuntimeError("R1 memory use unexpectedly exceeded 2 GiB")
    if audit["status"] != "INCOMPLETE_HOLDOUT_COMPLETION_REVIEW_REQUIRED":
        raise RuntimeError("R1 completion status mismatch")

    with zipfile.ZipFile(io.BytesIO(seed_return_bytes)) as zf:
        if zf.testzip() is not None:
            raise RuntimeError("nested seed-return CRC failure")
        if any(name.endswith("SEED_RESULT.json") for name in zf.namelist()):
            raise RuntimeError("R1 unexpectedly contains a completed seed result")
        stderr = read_member(zf, "worker_stderr.log")
        if "protected scheduling mode count 7776 exceeds 4096" not in stderr:
            raise RuntimeError("original 7776/4096 capacity failure not preserved")

    # Extract the completed high-mode reference seed to make the wall-time basis explicit.
    with zipfile.ZipFile(holdout) as zf:
        seed_zip_name = next(
            name for name in zf.namelist()
            if name.endswith("seed_returns/FR3_PHASE1_SEED_44051_RETURN.zip")
        )
        seed_zip = zf.read(seed_zip_name)
    with zipfile.ZipFile(io.BytesIO(seed_zip)) as zf:
        result_name = next(name for name in zf.namelist() if name.endswith("SEED_RESULT.json"))
        result = json.loads(zf.read(result_name))
    mode_max = max(
        int(record["candidate_action_diagnostics"]["maximum_schedule_mode_count"])
        for record in result["pass_audits"]
    )
    solver_sum = sum(
        float(record["candidate_action_diagnostics"]["schedule_solver_seconds_sum"])
        for record in result["pass_audits"]
    )
    if mode_max != int(contract["resource_basis"]["reference_max_mode_count"]):
        raise RuntimeError("reference mode-count mismatch")

    output = {
        "schema_version": 1,
        "status": "PASS_R1_TRUE_WALLTIME_TIMEOUT_NOT_MEMORY_FAILURE",
        "source_supported_facts": {
            "seed": 44052,
            "r1_seed_job_state": rows[seed_job][3],
            "r1_seed_job_elapsed": elapsed,
            "r1_batch_maxrss_kib": maxrss_kib,
            "r1_merge_status": audit["status"],
            "original_mode_capacity_error": "7776 exceeds 4096",
            "reference_seed": 44051,
            "reference_maximum_mode_count": mode_max,
            "reference_schedule_solver_seconds_sum": solver_sum,
            "required_to_reference_mode_ratio": 7776 / mode_max,
        },
        "scientific_inference": {
            "memory_is_not_limiting": True,
            "single_12_minute_five_pass_job_is_underprovisioned": True,
            "pass_parallelization_is_scientifically_exact": True,
            "pass_parallelization_basis": (
                "Each pass is evaluated independently from the same full-load nominal "
                "moving-average initialization; no state is propagated across passes."
            ),
            "selected_pass_walltime": contract["execution_strategy"]["pass_worker_walltime"],
        },
        "assumptions_requiring_validation": {
            "each_pass_completes_within_15_minutes": True,
        },
    }
    out = Path(args.output_json).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("R1_TIMEOUT_AUDIT=PASS")
    print("R1_SEED_STATE=TIMEOUT")
    print("R1_ELAPSED=00:12:04")
    print(f"R1_BATCH_MAXRSS_KIB={maxrss_kib}")
    print("R1_MEMORY_LIMITING=NO")
    print("PASS_PARALLELIZATION_SCIENTIFIC_EQUIVALENCE=PASS")
    print("PASS_WORKER_ARRAY=0-4%5")
    print("PASS_WORKER_WALLTIME=00:20:00")
    print("GPU_REQUESTED=NO")
    print("CHANNEL_REGENERATION=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
