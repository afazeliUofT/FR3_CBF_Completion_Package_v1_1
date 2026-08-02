#!/usr/bin/env python3
"""Audit the failed v4.4 run and recover only preliminary, non-paper evidence."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

import numpy as np
import pandas as pd

FAILED_SEEDS = [44001, 44007, 44008, 44013, 44017, 44018, 44024, 44025, 44026, 44027, 44028]
CANDIDATE_V43 = "candidate_v4_3_floor_feasibility_repair"
CANDIDATE_V44 = "candidate_v4_4_floor_first_protected_subband_scheduling"
EXPECTED_RETURN_SHA = "8001c6dd16e10b92b4d3cce5a59a1b5e4eed641dc022b1449b51e72ec5a6606b"
EXPECTED_ERROR = "TypeError: Object of type ndarray is not JSON serializable"
COMPARE_COLUMNS = [
    "final_moving_pf_utility",
    "duration_weighted_mean_moving_pf_utility",
    "long_violation_seconds",
    "short_violation_seconds",
    "eligible_floor_violation_user_seconds",
    "eligible_floor_violation_user_intervals",
]


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_manifest(root: Path, manifest: Path) -> None:
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(maxsplit=1)
        path = root / relative.strip()
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"manifest mismatch: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    package_root = args.package_root.resolve()
    archive = package_root / "immutable_bindings/FR3_RORQUAL_V4_4_PROTECTED_SUBBAND_SCHEDULING_DEVELOPMENT_18153316.zip"
    if sha256_file(archive) != EXPECTED_RETURN_SHA:
        raise RuntimeError("prior return SHA-256 mismatch")

    reference_root = package_root / "immutable_bindings/v4_3_failed_seed_reference_cells"
    verify_manifest(reference_root, reference_root / "REFERENCE_MANIFEST.sha256")

    with zipfile.ZipFile(archive) as zf:
        if zf.testzip() is not None:
            raise RuntimeError("prior return ZIP CRC failure")
        roots = sorted({name.split("/", 1)[0] for name in zf.namelist() if "/" in name})
        if len(roots) != 1:
            raise RuntimeError("prior return must have one root")
        with tempfile.TemporaryDirectory() as temp:
            zf.extractall(temp)
            root = Path(temp) / roots[0]
            verify_manifest(root, root / "RETURN_MANIFEST.sha256")
            metadata = json.loads((root / "RETURN_METADATA.json").read_text(encoding="utf-8"))
            if metadata["status"] != "FAIL_INFRASTRUCTURE_NO_V44_SCHEDULING_SUMMARY":
                raise RuntimeError("unexpected prior-return classification")
            frames: list[pd.DataFrame] = []
            v43_frames: list[pd.DataFrame] = []
            maximum_comparator_error = 0.0
            error_count = 0
            result_trace_file_count = 0
            for seed in FAILED_SEEDS:
                seed_root = root / "seed_results" / f"seed_{seed}"
                if (seed_root / "process_exit_code.txt").read_text().strip() != "1":
                    raise RuntimeError(f"unexpected worker exit: seed {seed}")
                stderr = (seed_root / "stderr.log").read_text(encoding="utf-8")
                if EXPECTED_ERROR not in stderr:
                    raise RuntimeError(f"root exception mismatch: seed {seed}")
                if "PASS_AUDITS.json" not in stderr:
                    raise RuntimeError(f"failure point mismatch: seed {seed}")
                error_count += 1
                result = seed_root / "result"
                required = [result / "CELL_SUMMARY.csv"]
                required.extend(result / f"PASS_{slot}_METHOD_TRACES.npz" for slot in range(5))
                required.extend(result / f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz" for slot in range(5))
                for path in required:
                    if not path.is_file():
                        raise RuntimeError(f"completed pass artifact missing: {path}")
                result_trace_file_count += 10
                new = pd.read_csv(result / "CELL_SUMMARY.csv")
                new["campaign_seed"] = seed
                frames.append(new)
                old = pd.read_csv(reference_root / f"seed_{seed}/CELL_SUMMARY.csv")
                old["campaign_seed"] = seed
                v43_frames.append(old[old["method_id"] == CANDIDATE_V43].copy())
                for method in sorted(set(old["method_id"]) - {CANDIDATE_V43}):
                    old_rows = old[old["method_id"] == method].sort_values("pass_slot")
                    new_rows = new[new["method_id"] == method].sort_values("pass_slot")
                    if len(old_rows) != 5 or len(new_rows) != 5:
                        raise RuntimeError(f"comparator row-count mismatch: {seed}/{method}")
                    for column in COMPARE_COLUMNS:
                        error = float(np.max(np.abs(
                            old_rows[column].to_numpy(dtype=np.float64)
                            - new_rows[column].to_numpy(dtype=np.float64)
                        )))
                        maximum_comparator_error = max(maximum_comparator_error, error)

    cells = pd.concat(frames, ignore_index=True)
    candidate = cells[cells["method_id"] == CANDIDATE_V44].copy()
    old_candidate = pd.concat(v43_frames, ignore_index=True)
    if len(candidate) != 55 or len(old_candidate) != 55:
        raise RuntimeError("candidate cell-count mismatch")

    preliminary_floor_seconds = int(candidate["eligible_floor_violation_user_seconds"].sum())
    preliminary_floor_intervals = int(candidate["eligible_floor_violation_user_intervals"].sum())
    preliminary_unresolved = int(candidate["candidate_unresolved_deployable_intervals"].sum())
    v43_floor_seconds = int(old_candidate["eligible_floor_violation_user_seconds"].sum())
    v43_floor_intervals = int(old_candidate["eligible_floor_violation_user_intervals"].sum())
    v43_unresolved = int(old_candidate["candidate_unresolved_deployable_intervals"].sum())
    hard_pass_seeds = []
    failed_seeds = []
    for seed, group in candidate.groupby("campaign_seed"):
        hard = bool(
            int(group["eligible_floor_violation_user_seconds"].sum()) == 0
            and int(group["eligible_floor_violation_user_intervals"].sum()) == 0
            and int(group["candidate_unresolved_deployable_intervals"].sum()) == 0
            and int(group["long_violation_seconds"].sum()) == 0
            and int(group["short_violation_seconds"].sum()) == 0
        )
        (hard_pass_seeds if hard else failed_seeds).append(int(seed))

    extras = [ast.literal_eval(value) for value in candidate["extra"]]
    strict_local = all(str(value["strict_local_scope_gate"]) == "PASS" for value in extras)
    strict_power = all(str(value["strict_post_mode_selected_power_gate"]) == "PASS" for value in extras)
    q0_actions = int(sum(int(value["q0_envelope_deployable_actions"]) for value in extras))
    shutdowns = int(sum(int(value["network_wide_shutdown_intervals"]) for value in extras))
    scheduling_success = int(sum(int(value["protected_subband_scheduling_success_intervals"]) for value in extras))
    scheduling_failure = int(sum(int(value["protected_subband_scheduling_failure_intervals"]) for value in extras))

    expected_source_hashes = {
        "src/fr3_cbf/protected_subband_scheduler.py": "4dceabf6a3747310c653931df0b18a688dc5942a64103828f0b21a614d537775",
        "src/fr3_cbf/candidate_v4_4_scheduling_campaign.py": "4c81e7cd77458064b59e17f7998131a018e87e107c40309527177afc34ce8311",
    }
    for relative, expected in expected_source_hashes.items():
        if sha256_file(package_root / relative) != expected:
            raise RuntimeError(f"scientific source changed: {relative}")

    record = {
        "schema_version": 1,
        "status": "PASS_PRIOR_V44_INFRASTRUCTURE_FAILURE_AND_PRELIMINARY_SALVAGE_AUDIT",
        "prior_return_sha256": EXPECTED_RETURN_SHA,
        "prior_return_manifest": "PASS",
        "prior_worker_root_exception_count": error_count,
        "prior_worker_root_exception": EXPECTED_ERROR,
        "prior_completed_trace_file_count": result_trace_file_count,
        "prior_merge_summary_present": False,
        "root_cause": "NUMPY_NDARRAY_JSON_SERIALIZATION",
        "scientific_candidate_source_identity": "PASS",
        "preliminary_not_paper_evidence": True,
        "preliminary_comparator_maximum_absolute_error": maximum_comparator_error,
        "v43_floor_violation_user_seconds": v43_floor_seconds,
        "preliminary_v44_floor_violation_user_seconds": preliminary_floor_seconds,
        "preliminary_v44_floor_violation_user_seconds_reduction_percent": 100.0 * (v43_floor_seconds - preliminary_floor_seconds) / v43_floor_seconds,
        "v43_floor_violation_user_intervals": v43_floor_intervals,
        "preliminary_v44_floor_violation_user_intervals": preliminary_floor_intervals,
        "v43_unresolved_intervals": v43_unresolved,
        "preliminary_v44_unresolved_intervals": preliminary_unresolved,
        "preliminary_v44_unresolved_reduction_percent": 100.0 * (v43_unresolved - preliminary_unresolved) / v43_unresolved,
        "preliminary_hard_gate_pass_seeds": hard_pass_seeds,
        "preliminary_failed_seeds": failed_seeds,
        "preliminary_long_eess_violation_seconds": int(candidate["long_violation_seconds"].sum()),
        "preliminary_short_eess_violation_seconds": int(candidate["short_violation_seconds"].sum()),
        "preliminary_strict_local_scope": "PASS" if strict_local else "FAIL",
        "preliminary_strict_post_mode_power": "PASS" if strict_power else "FAIL",
        "preliminary_q0_headroom_actions": q0_actions,
        "preliminary_network_wide_shutdown_intervals": shutdowns,
        "preliminary_scheduling_success_intervals": scheduling_success,
        "preliminary_scheduling_failure_intervals": scheduling_failure,
        "next_gate": "RERUN_11_PRESERVED_FAILED_SEEDS_WITH_JSON_SERIALIZATION_REPAIR",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PRIOR_V44_INFRASTRUCTURE_FAILURE_AUDIT=PASS")
    print("PRIOR_V44_ROOT_CAUSE=NUMPY_NDARRAY_JSON_SERIALIZATION")
    print(f"PRIOR_V44_WORKER_ERROR_COUNT={error_count}")
    print(f"PRIOR_V44_COMPLETED_TRACE_FILE_COUNT={result_trace_file_count}")
    print(f"PRELIMINARY_COMPARATOR_MAXIMUM_ABSOLUTE_ERROR={maximum_comparator_error:.17g}")
    print(f"PRELIMINARY_V44_FLOOR_VIOLATION_USER_SECONDS={preliminary_floor_seconds}")
    print(f"PRELIMINARY_V44_UNRESOLVED_INTERVALS={preliminary_unresolved}")
    print("PRELIMINARY_HARD_GATE_PASS_SEEDS=" + ",".join(map(str, hard_pass_seeds)))
    print("PRELIMINARY_FAILED_SEEDS=" + ",".join(map(str, failed_seeds)))
    print("SCIENTIFIC_CANDIDATE_SOURCE_IDENTITY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
