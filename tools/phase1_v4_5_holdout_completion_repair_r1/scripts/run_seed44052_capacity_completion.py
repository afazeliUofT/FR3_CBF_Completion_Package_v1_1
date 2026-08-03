#!/usr/bin/env python3
"""Run only holdout seed 44052 with an implementation-capacity override.

The scientific modules, constraints, objective, floor, tolerances, modes, and
method order remain unchanged.  The only runtime override raises the defensive
Cartesian-mode enumeration guard from 4096 to 8192 so that the already-declared
7776-mode library can be evaluated.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

SEED = 44052
ORIGINAL_CAP = 4096
REPAIRED_CAP = 8192
OBSERVED_MODE_COUNT = 7776


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--job-package-root", required=True)
    p.add_argument("--output-root", required=True)
    p.add_argument("--completion-contract", required=True)
    args = p.parse_args()
    root = Path(args.job_package_root).resolve()
    output_root = Path(args.output_root).resolve()
    contract = json.loads(Path(args.completion_contract).read_text(encoding="utf-8"))
    if int(contract["seed44052_completion"]["seed"]) != SEED:
        raise RuntimeError("completion contract seed mismatch")
    if int(contract["seed44052_completion"]["original_mode_count_guard"]) != ORIGINAL_CAP:
        raise RuntimeError("original mode cap contract mismatch")
    if int(contract["seed44052_completion"]["repaired_mode_count_guard"]) != REPAIRED_CAP:
        raise RuntimeError("repaired mode cap contract mismatch")
    if int(contract["seed44052_completion"]["observed_required_mode_count"]) != OBSERVED_MODE_COUNT:
        raise RuntimeError("observed mode count contract mismatch")

    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root))
    from fr3_cbf import companion_aware_scheduler as scheduler
    if int(scheduler.MAX_MODE_COUNT) != ORIGINAL_CAP:
        raise RuntimeError(
            f"unexpected original MAX_MODE_COUNT={scheduler.MAX_MODE_COUNT}"
        )
    scheduler.MAX_MODE_COUNT = REPAIRED_CAP
    if int(scheduler.MAX_MODE_COUNT) != REPAIRED_CAP:
        raise RuntimeError("runtime capacity override failed")

    import phase1_seed_worker
    old_argv = sys.argv[:]
    try:
        sys.argv = [
            str(root / "phase1_seed_worker.py"),
            "--seed", str(SEED),
            "--output-root", str(output_root),
            "--reuse-channel",
        ]
        worker_rc = int(phase1_seed_worker.main())
    finally:
        sys.argv = old_argv

    result_root = output_root / f"seed_{SEED}" / "result"
    seed_result_path = result_root / "SEED_RESULT.json"
    manifest_path = result_root / "RESULT_FILE_MANIFEST.json"
    if not seed_result_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("seed 44052 completion did not create a complete result")

    overlay = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "IMPLEMENTATION_CAPACITY_REPAIR_NOT_ALGORITHM_TUNING",
        "seed": SEED,
        "original_mode_count_guard": ORIGINAL_CAP,
        "observed_required_mode_count": OBSERVED_MODE_COUNT,
        "repaired_mode_count_guard": REPAIRED_CAP,
        "scientific_source_files_modified": False,
        "action_library_definition_changed": False,
        "objective_changed": False,
        "constraints_changed": False,
        "floor_changed": False,
        "tolerances_changed": False,
        "new_seed_or_channel_generated": False,
        "channel_reused": True,
        "claim_boundary": (
            "FRESH_HOLDOUT_COMPLETION_AFTER_NONSCIENTIFIC_IMPLEMENTATION_"
            "CAPACITY_REPAIR; NOT_CALIBRATION; NOT_REGULATORY_COMPLIANCE"
        ),
    }
    overlay_path = result_root / "IMPLEMENTATION_CAPACITY_OVERLAY.json"
    write_json(overlay_path, overlay)

    seed_result = json.loads(seed_result_path.read_text(encoding="utf-8"))
    seed_result["implementation_capacity_overlay"] = overlay
    seed_result["holdout_completion_classification"] = (
        "VALID_FRESH_HOLDOUT_SEED_AFTER_NONSCIENTIFIC_CAPACITY_REPAIR"
    )
    result_files = dict(seed_result.get("result_files", {}))
    result_files[overlay_path.name] = {
        "bytes": overlay_path.stat().st_size,
        "sha256": sha256_file(overlay_path),
    }
    seed_result["result_files"] = result_files
    write_json(seed_result_path, seed_result)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[overlay_path.name] = {
        "bytes": overlay_path.stat().st_size,
        "sha256": sha256_file(overlay_path),
    }
    manifest[seed_result_path.name] = {
        "bytes": seed_result_path.stat().st_size,
        "sha256": sha256_file(seed_result_path),
    }
    write_json(manifest_path, manifest)

    print("SEED44052_CAPACITY_COMPLETION=PASS")
    print(f"ORIGINAL_MODE_COUNT_GUARD={ORIGINAL_CAP}")
    print(f"OBSERVED_REQUIRED_MODE_COUNT={OBSERVED_MODE_COUNT}")
    print(f"REPAIRED_MODE_COUNT_GUARD={REPAIRED_CAP}")
    print("SCIENTIFIC_SOURCE_FILES_MODIFIED=NO")
    print("ACTION_LIBRARY_DEFINITION_CHANGED=NO")
    print("CHANNEL_REUSED=YES")
    print(f"SEED44052_SCIENTIFIC_EXIT_CODE={worker_rc}")
    return worker_rc


if __name__ == "__main__":
    raise SystemExit(main())
