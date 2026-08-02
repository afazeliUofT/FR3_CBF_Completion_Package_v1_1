#!/usr/bin/env python3
"""Create a compact, failure-preserving fresh-v4.5 holdout return."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_if_file(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def read_int(path: Path, default: int = 99) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return default


def zip_tree(root: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(root.parent).as_posix())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-root", required=True)
    p.add_argument("--job-package-root", required=True)
    p.add_argument("--authorization-contract", required=True)
    p.add_argument("--authorization-token-metadata", required=True)
    p.add_argument("--authorization-package-sha256", required=True)
    p.add_argument("--array-job-id", required=True)
    p.add_argument("--merge-job-id", required=True)
    p.add_argument("--finalizer-job-id", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    run = Path(args.run_root).resolve()
    job = Path(args.job_package_root).resolve()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    decision = json.loads(Path(args.authorization_contract).read_text(encoding="utf-8"))
    job_contract = json.loads((job / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8"))
    token_meta = json.loads(Path(args.authorization_token_metadata).read_text(encoding="utf-8"))

    root_name = f"FR3_RORQUAL_V4_5_FRESH_HOLDOUT_{args.array_job_id}"
    with tempfile.TemporaryDirectory(prefix="fr3-v45-holdout-return-") as temp_name:
        payload = Path(temp_name) / root_name
        payload.mkdir()
        (payload / "seed_returns").mkdir()
        (payload / "seed_summaries").mkdir()
        (payload / "merged").mkdir()
        (payload / "slurm").mkdir()
        (payload / "logs").mkdir()
        (payload / "bindings").mkdir()

        seed_records = []
        complete_returns = 0
        valid_seed_audits = 0
        zero_floor_seed_count = 0
        safety_pass_seed_count = 0
        seed_scientific_nonzero_count = 0
        for seed in job_contract["campaign_seed_list"]:
            seed_root = run / "results" / f"seed_{seed}"
            result = seed_root / "result"
            return_zip = seed_root / f"FR3_PHASE1_SEED_{seed}_RETURN.zip"
            return_sidecar = Path(str(return_zip) + ".sha256")
            record = {
                "seed": seed,
                "seed_return_zip_present": False,
                "seed_result_present": False,
                "candidate_hard_gates_pass": False,
                "candidate_safety_gates_pass": False,
                "scientific_exit_code": None,
            }
            if return_zip.is_file() and return_sidecar.is_file():
                copy_if_file(return_zip, payload / "seed_returns" / return_zip.name)
                copy_if_file(return_sidecar, payload / "seed_returns" / return_sidecar.name)
                record["seed_return_zip_present"] = True
                record["seed_return_zip_sha256"] = sha256_file(return_zip)
                complete_returns += 1
            for name in ("SEED_RESULT.json", "RESULT_FILE_MANIFEST.json", "CELL_SUMMARY.csv", "PRIMARY_PAIRED_EFFECTS.csv"):
                copy_if_file(result / name, payload / "seed_summaries" / f"seed_{seed}" / name)
            copy_if_file(seed_root / "channel" / "CHANNEL_RECORD.json", payload / "seed_summaries" / f"seed_{seed}" / "CHANNEL_RECORD.json")
            audit_path = result / "SEED_RESULT.json"
            if audit_path.is_file():
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                record["seed_result_present"] = True
                record["candidate_hard_gates_pass"] = bool(audit.get("candidate_hard_gates_pass", False))
                record["scientific_exit_code"] = int(audit.get("scientific_exit_code", 99))
                record["seed_result_sha256"] = sha256_file(audit_path)
                pass_audits = audit.get("pass_audits", [])
                safety_pass = bool(pass_audits) and all(
                    int(pa.get("candidate_hard_gates", {}).get("long_violation_seconds", 1)) == 0
                    and int(pa.get("candidate_hard_gates", {}).get("short_violation_seconds", 1)) == 0
                    and pa.get("candidate_hard_gates", {}).get("strict_local_scope_gate") == "PASS"
                    and pa.get("candidate_hard_gates", {}).get("strict_post_mode_selected_power_gate") == "PASS"
                    and int(pa.get("candidate_hard_gates", {}).get("q0_envelope_deployable_actions", 1)) == 0
                    and int(pa.get("candidate_hard_gates", {}).get("network_wide_shutdown_intervals", 1)) == 0
                    for pa in pass_audits
                )
                record["candidate_safety_gates_pass"] = safety_pass
                valid_seed_audits += 1
                safety_pass_seed_count += int(safety_pass)
                zero_floor_seed_count += int(record["candidate_hard_gates_pass"])
                seed_scientific_nonzero_count += int(record["scientific_exit_code"] != 0)
            seed_records.append(record)
        write_json(payload / "SEED_COMPLETION_INDEX.json", seed_records)

        merged_src = run / "merged"
        for name in (
            "PHASE1_MERGED_AUDIT.json",
            "PHASE1_BOOTSTRAP_SUMMARY.json",
            "PHASE1_SEED_CLUSTER_EFFECTS.csv",
            "PHASE1_PRIMARY_PAIRED_EFFECTS.csv",
            "PHASE1_METHOD_ENDPOINT_SUMMARY.csv",
            "PHASE1_ALL_CELL_SUMMARY.csv",
            "PHASE1_LEAVE_ONE_PASS_OUT.csv",
            "PHASE1_SEED_RETURN_HASH_INDEX.csv",
            "PHASE1_ACTION_AND_RUNTIME_SUMMARY.json",
            "MERGED_FILE_MANIFEST.json",
            "FR3_PHASE1_MERGED_REVIEW_RETURN.zip",
            "FR3_PHASE1_MERGED_REVIEW_RETURN.zip.sha256",
            "PHASE1_MERGE_INCOMPLETE.json",
        ):
            copy_if_file(merged_src / name, payload / "merged" / name)

        for path in sorted((run / "slurm").glob("*")) if (run / "slurm").is_dir() else []:
            if path.is_file() and path.stat().st_size <= 5_000_000:
                copy_if_file(path, payload / "slurm" / path.name)
        for path in sorted((run / "logs").glob("*")) if (run / "logs").is_dir() else []:
            if path.is_file() and path.stat().st_size <= 5_000_000:
                copy_if_file(path, payload / "logs" / path.name)
        for name in ("JOB_PACKAGE_CONTRACT.json", "CANDIDATE_V4_5_SOURCE_MANIFEST.sha256", "PACKAGE_ID.txt"):
            copy_if_file(job / name, payload / "bindings" / name)
        write_json(payload / "bindings" / "AUTHORIZATION_PUBLIC_METADATA.json", token_meta)
        write_json(payload / "bindings" / "FREEZE_HOLDOUT_CONTRACT.json", decision)

        merged_audit_path = merged_src / "PHASE1_MERGED_AUDIT.json"
        merged_audit = json.loads(merged_audit_path.read_text(encoding="utf-8")) if merged_audit_path.is_file() else None
        valid_holdout = bool(merged_audit and merged_audit.get("valid_holdout_result", False))
        primary_superiority = bool(merged_audit and merged_audit.get("primary_superiority_met", False))
        if valid_holdout and primary_superiority:
            status = merged_audit["status"]
            scientific_exit_code = 0
        elif valid_holdout:
            status = merged_audit["status"]
            scientific_exit_code = 0
        elif complete_returns == 30 and merged_audit is not None:
            status = "FAIL_FRESH_V4_5_HOLDOUT_SAFETY_OR_VALIDATION_GATE_REVIEW_REQUIRED"
            scientific_exit_code = 42
        else:
            status = "INCOMPLETE_FRESH_V4_5_HOLDOUT_REVIEW_REQUIRED"
            scientific_exit_code = 42

        metadata = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "scientific_exit_code": scientific_exit_code,
            "claim_boundary": "FRESH_HOLDOUT_NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE; USER_FLOOR_FEASIBILITY_CONDITIONED",
            "paper_result": False,
            "authorization_package_sha256": args.authorization_package_sha256,
            "authorization_token_sha256": token_meta.get("authorization_token_sha256"),
            "authorization_token_included": False,
            "package_id": job_contract["package_id"],
            "array_job_id": args.array_job_id,
            "merge_job_id": args.merge_job_id,
            "finalizer_job_id": args.finalizer_job_id,
            "seed_count_expected": 30,
            "seed_return_count": complete_returns,
            "seed_audit_count": valid_seed_audits,
            "seed_zero_floor_pass_count": zero_floor_seed_count,
            "seed_safety_pass_count": safety_pass_seed_count,
            "seed_scientific_nonzero_count": seed_scientific_nonzero_count,
            "merged_audit_present": merged_audit is not None,
            "valid_holdout_result": valid_holdout,
            "primary_superiority_met": primary_superiority,
            "floor_zero": bool(merged_audit and merged_audit.get("floor_zero", False)),
            "primary_point_estimate": (merged_audit or {}).get("primary_bootstrap", {}).get("point_estimate"),
            "primary_lower_95": (merged_audit or {}).get("primary_bootstrap", {}).get("lower_95"),
            "primary_upper_95": (merged_audit or {}).get("primary_bootstrap", {}).get("upper_95"),
            "automatic_extra_seed_or_algorithm_tuning_authorized": False,
            "next_gate": (merged_audit or {}).get("next_gate", "REVIEW_HOLDOUT_WITHOUT_AUTOMATIC_EXTRA_PROBES"),
        }
        write_json(payload / "HOLDOUT_RETURN_METADATA.json", metadata)

        manifest_lines = []
        for path in sorted(payload.rglob("*")):
            if path.is_file() and path.name != "RETURN_MANIFEST.sha256":
                manifest_lines.append(f"{sha256_file(path)}  {path.relative_to(payload).as_posix()}")
        (payload / "RETURN_MANIFEST.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

        archive = out / f"FR3_RORQUAL_V4_5_FRESH_HOLDOUT_{args.array_job_id}.zip"
        zip_tree(payload, archive)
        digest = sha256_file(archive)
        Path(str(archive) + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")

    print("HOLDOUT_RETURN_ZIP=" + str(archive))
    print("HOLDOUT_RETURN_ZIP_SHA256=" + digest)
    print("HOLDOUT_RETURN_STATUS=" + status)
    print("HOLDOUT_SCIENTIFIC_EXIT_CODE=" + str(scientific_exit_code))
    print("HOLDOUT_SEED_RETURN_COUNT=" + str(complete_returns))
    print("HOLDOUT_SEED_SAFETY_PASS_COUNT=" + str(safety_pass_seed_count))
    print("HOLDOUT_SEED_ZERO_FLOOR_PASS_COUNT=" + str(zero_floor_seed_count))
    print("AUTOMATIC_EXTRA_PROBES_AUTHORIZED=NO")
    return scientific_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
