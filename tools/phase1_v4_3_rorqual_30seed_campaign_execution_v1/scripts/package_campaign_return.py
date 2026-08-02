#!/usr/bin/env python3
"""Build a portable, failure-preserving full-campaign return bundle."""
from __future__ import annotations

import argparse
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


def copy_tree_files(src: Path, dst: Path) -> int:
    count = 0
    if not src.is_dir():
        return count
    for path in sorted(src.rglob("*")):
        if path.is_file():
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            count += 1
    return count


def read_int(path: Path, default: int = 99) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return default


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-root", required=True)
    p.add_argument("--job-package-root", required=True)
    p.add_argument("--authorization-contract", required=True)
    p.add_argument("--authorization-token", default="")
    p.add_argument("--authorization-token-metadata", default="")
    p.add_argument("--authorization-package-sha256", required=True)
    p.add_argument("--array-job-id", required=True)
    p.add_argument("--merge-job-id", required=True)
    p.add_argument("--finalizer-job-id", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--pip-freeze", default="")
    args = p.parse_args()

    run = Path(args.run_root).expanduser().resolve()
    job = Path(args.job_package_root).expanduser().resolve()
    auth_contract_path = Path(args.authorization_contract).expanduser().resolve()
    auth_token_path = Path(args.authorization_token).expanduser().resolve() if args.authorization_token else None
    auth_token_metadata_path = Path(args.authorization_token_metadata).expanduser().resolve() if args.authorization_token_metadata else None
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    job_contract = json.loads((job / "JOB_PACKAGE_CONTRACT.json").read_text(encoding="utf-8"))
    decision = json.loads(auth_contract_path.read_text(encoding="utf-8"))
    if auth_token_path is not None and auth_token_path.is_file():
        token = json.loads(auth_token_path.read_text(encoding="utf-8"))
        token_sha256 = sha256_file(auth_token_path)
    elif auth_token_metadata_path is not None and auth_token_metadata_path.is_file():
        token_meta_input = json.loads(auth_token_metadata_path.read_text(encoding="utf-8"))
        token = token_meta_input["token_public_fields"]
        token_sha256 = token_meta_input["authorization_token_sha256"]
    else:
        raise FileNotFoundError("authorization token or token metadata is required")
    seeds = list(range(44000, 44030))
    if job_contract["campaign_seed_list"] != seeds:
        raise RuntimeError("job package seed list changed")
    if token["allowed_seeds"] != seeds:
        raise RuntimeError("authorization token seed list changed")

    seed_records: list[dict] = []
    complete_seed_returns = 0
    valid_seed_audits = 0
    hard_gate_seed_count = 0
    seed_scientific_failures = 0

    with tempfile.TemporaryDirectory(prefix="fr3-campaign-return-") as tmp_name:
        tmp = Path(tmp_name)
        payload_name = f"FR3_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_{args.array_job_id}"
        payload = tmp / payload_name
        payload.mkdir()

        bindings = payload / "bindings"
        bindings.mkdir()
        copy_if_file(auth_contract_path, bindings / "FULL_CAMPAIGN_AUTHORIZATION_CONTRACT.json")
        for name in (
            "PACKAGE_ID.txt",
            "PACKAGE_MANIFEST.sha256",
            "JOB_PACKAGE_CONTRACT.json",
            "PHASE1_CAMPAIGN_CONTRACT_V4_3.json",
            "RORQUAL_R2_BINDING.json",
            "CANDIDATE_V4_3_SOURCE_MANIFEST.sha256",
            "NEW_JOB_SOURCE_MANIFEST.sha256",
        ):
            copy_if_file(job / name, bindings / name)

        token_metadata = {
            "schema_version": 1,
            "authorization_token_sha256": token_sha256,
            "authorization_decision_id": token["authorization_decision_id"],
            "authorization_package_sha256": args.authorization_package_sha256,
            "authorization_expires_utc": token["authorization_expires_utc"],
            "execution_stage": token["execution_stage"],
            "authorized_seed_count": len(token["allowed_seeds"]),
            "authorized_seed_first": min(token["allowed_seeds"]),
            "authorized_seed_last": max(token["allowed_seeds"]),
            "authorization_token_included": False,
        }
        write_json(bindings / "AUTHORIZATION_TOKEN_METADATA.json", token_metadata)

        copy_tree_files(run / "slurm", payload / "slurm")
        copy_tree_files(run / "logs", payload / "logs")
        copy_tree_files(run / "status", payload / "status")
        copy_tree_files(run / "merged", payload / "merged")
        if args.pip_freeze:
            copy_if_file(Path(args.pip_freeze), payload / "environment" / "pip_freeze.txt")

        seed_returns = payload / "seed_returns"
        seed_summaries = payload / "seed_summaries"
        for seed in seeds:
            seed_root = run / "results" / f"seed_{seed}"
            result = seed_root / "result"
            return_zip = seed_root / f"FR3_PHASE1_SEED_{seed}_RETURN.zip"
            return_sidecar = Path(str(return_zip) + ".sha256")
            record: dict[str, object] = {
                "campaign_seed": seed,
                "seed_result_present": False,
                "seed_return_zip_present": False,
                "candidate_hard_gates_pass": False,
                "scientific_exit_code": None,
            }
            if return_zip.is_file() and return_sidecar.is_file():
                copy_if_file(return_zip, seed_returns / return_zip.name)
                copy_if_file(return_sidecar, seed_returns / return_sidecar.name)
                record["seed_return_zip_present"] = True
                record["seed_return_zip_sha256"] = sha256_file(return_zip)
                complete_seed_returns += 1
            for name in (
                "SEED_RESULT.json",
                "RESULT_FILE_MANIFEST.json",
                "CELL_SUMMARY.csv",
                "PRIMARY_PAIRED_EFFECTS.csv",
            ):
                copy_if_file(result / name, seed_summaries / f"seed_{seed}" / name)
            copy_if_file(
                seed_root / "channel" / "CHANNEL_RECORD.json",
                seed_summaries / f"seed_{seed}" / "CHANNEL_RECORD.json",
            )
            audit_path = result / "SEED_RESULT.json"
            if audit_path.is_file():
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                record["seed_result_present"] = True
                record["candidate_hard_gates_pass"] = bool(audit.get("candidate_hard_gates_pass", False))
                record["scientific_exit_code"] = int(audit.get("scientific_exit_code", 99))
                record["seed_result_sha256"] = sha256_file(audit_path)
                valid_seed_audits += 1
                if record["candidate_hard_gates_pass"]:
                    hard_gate_seed_count += 1
                if record["scientific_exit_code"] != 0:
                    seed_scientific_failures += 1
            seed_records.append(record)
        write_json(payload / "SEED_COMPLETION_INDEX.json", seed_records)

        merged_audit_path = run / "merged" / "PHASE1_MERGED_AUDIT.json"
        merged_audit = None
        if merged_audit_path.is_file():
            merged_audit = json.loads(merged_audit_path.read_text(encoding="utf-8"))
        array_summary_rc = read_int(run / "status" / "ARRAY_SUMMARY_EXIT_CODE.txt")
        merge_worker_rc = read_int(run / "status" / "MERGE_WORKER_EXIT_CODE.txt")
        merged_validator_rc = read_int(run / "status" / "MERGED_VALIDATOR_EXIT_CODE.txt")

        all_seed_returns = complete_seed_returns == 30
        all_seed_audits = valid_seed_audits == 30
        all_seed_hard = hard_gate_seed_count == 30 and seed_scientific_failures == 0
        merged_present = merged_audit is not None
        merged_hard = bool(merged_audit and merged_audit.get("all_hard_gates_pass", False))
        go = bool(merged_audit and merged_audit.get("go_condition_met", False))
        structural_pass = merged_validator_rc == 0

        if all_seed_returns and all_seed_audits and all_seed_hard and merged_present and merged_hard and structural_pass:
            if go:
                status = "PASS_RORQUAL_V4_3_R2_30SEED_HARD_GATES_AND_PRIMARY_SUPERIORITY_REVIEW_REQUIRED"
            else:
                status = "VALID_RORQUAL_V4_3_R2_30SEED_HARD_GATES_PASS_PRIMARY_SUPERIORITY_NOT_MET_REVIEW_REQUIRED"
            scientific_exit_code = 0
        elif all_seed_returns and merged_present:
            status = "FAIL_RORQUAL_V4_3_R2_30SEED_SCIENTIFIC_OR_VALIDATION_GATES_REVIEW_REQUIRED"
            scientific_exit_code = 42
        else:
            status = "INCOMPLETE_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_REVIEW_REQUIRED"
            scientific_exit_code = 42

        primary = (merged_audit or {}).get("primary_bootstrap", {})
        metadata = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "scientific_exit_code": scientific_exit_code,
            "claim_boundary": "CAMPAIGN_OUTPUT_REQUIRES_INDEPENDENT_REVIEW_BEFORE_PAPER_USE",
            "paper_result": False,
            "campaign_execution_was_authorized": True,
            "authorization_decision_id": decision["authorization_decision_id"],
            "authorization_package_sha256": args.authorization_package_sha256,
            "authorization_token_sha256": token_sha256,
            "authorization_token_included": False,
            "package_id": job_contract["package_id"],
            "array_job_id": args.array_job_id,
            "merge_job_id": args.merge_job_id,
            "finalizer_job_id": args.finalizer_job_id,
            "seed_count_expected": 30,
            "seed_return_count": complete_seed_returns,
            "seed_audit_count": valid_seed_audits,
            "seed_hard_gate_pass_count": hard_gate_seed_count,
            "seed_scientific_failure_count": seed_scientific_failures,
            "all_seed_returns_present": all_seed_returns,
            "all_seed_audits_present": all_seed_audits,
            "all_seed_hard_gates_pass": all_seed_hard,
            "merged_audit_present": merged_present,
            "merged_all_hard_gates_pass": merged_hard,
            "merged_structural_validator_pass": structural_pass,
            "go_condition_met": go,
            "primary_point_estimate": primary.get("point_estimate"),
            "primary_lower_95": primary.get("lower_95"),
            "primary_upper_95": primary.get("upper_95"),
            "array_summary_exit_code": array_summary_rc,
            "merge_worker_exit_code": merge_worker_rc,
            "merged_validator_exit_code": merged_validator_rc,
            "information_exchange_locality_certified": False,
            "next_gate": "INDEPENDENT_SCIENTIFIC_REVIEW_AND_TWC_RESULTS_MANUSCRIPT_INTEGRATION",
        }
        write_json(payload / "CAMPAIGN_RETURN_METADATA.json", metadata)

        manifest_lines = []
        for path in sorted(payload.rglob("*")):
            if path.is_file() and path.name != "RETURN_MANIFEST.sha256":
                rel = path.relative_to(payload).as_posix()
                manifest_lines.append(f"{sha256_file(path)}  {rel}\n")
        (payload / "RETURN_MANIFEST.sha256").write_text("".join(manifest_lines), encoding="utf-8")

        output_zip = output_dir / f"FR3_RORQUAL_V4_3_R2_30SEED_CAMPAIGN_{args.array_job_id}.zip"
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for path in sorted(payload.rglob("*")):
                if path.is_file():
                    z.write(path, path.relative_to(tmp).as_posix())
        with zipfile.ZipFile(output_zip) as z:
            bad = z.testzip()
            if bad is not None:
                raise RuntimeError(f"campaign return ZIP CRC failure: {bad}")
        digest = sha256_file(output_zip)
        sidecar = Path(str(output_zip) + ".sha256")
        sidecar.write_text(f"{digest}  {output_zip.name}\n", encoding="utf-8")
        ready = {
            "return_zip": str(output_zip),
            "return_zip_sha256": digest,
            "return_status": status,
            "scientific_exit_code": scientific_exit_code,
        }
        write_json(output_dir / "RETURN_READY.json", ready)
        (output_dir / "RETURN_READY.env").write_text(
            "\n".join(
                [
                    f"CAMPAIGN_RETURN_ZIP={output_zip}",
                    f"CAMPAIGN_RETURN_ZIP_SHA256={digest}",
                    f"CAMPAIGN_RETURN_STATUS={status}",
                    f"CAMPAIGN_SCIENTIFIC_EXIT_CODE={scientific_exit_code}",
                ]
            ) + "\n",
            encoding="utf-8",
        )

    print("FULL_CAMPAIGN_RETURN_PACKAGING=PASS")
    print(f"CAMPAIGN_RETURN_ZIP={output_zip}")
    print(f"CAMPAIGN_RETURN_ZIP_SHA256={digest}")
    print(f"CAMPAIGN_RETURN_STATUS={status}")
    print(f"CAMPAIGN_SCIENTIFIC_EXIT_CODE={scientific_exit_code}")
    print(f"SEED_RETURN_COUNT={complete_seed_returns}")
    print(f"SEED_HARD_GATE_PASS_COUNT={hard_gate_seed_count}")
    print(f"MERGED_HARD_GATES={'PASS' if merged_hard else 'FAIL_OR_UNAVAILABLE'}")
    print(f"GO_CONDITION_MET={'YES' if go else 'NO'}")
    return scientific_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
