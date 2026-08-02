#!/usr/bin/env python3
"""Build a compact success/diagnostic return for the excluded final-worker smoke."""
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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_file(source: Path, target: Path) -> bool:
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def copy_tree(source: Path, target: Path, excluded_names: set[str] | None = None) -> int:
    if not source.is_dir():
        return 0
    excluded_names = excluded_names or set()
    count = 0
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.name not in excluded_names:
            relative = path.relative_to(source)
            copy_file(path, target / relative)
            count += 1
    return count


def read_json_if(path: Path):
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--smoke-package-root", required=True)
    parser.add_argument("--job-package-root", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--slurm-state", required=True)
    parser.add_argument("--slurm-exit-code", required=True)
    parser.add_argument("--worker-exit-code", required=True, type=int)
    parser.add_argument("--structural-validator-exit-code", required=True, type=int)
    parser.add_argument("--pass-validator-exit-code", required=True, type=int)
    parser.add_argument("--independent-audit-exit-code", required=True, type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    run = Path(args.run_root).expanduser().resolve()
    smoke = Path(args.smoke_package_root).expanduser().resolve()
    job = Path(args.job_package_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    seed_root = run / "results/seed_43999"
    result = seed_root / "result"
    channel = seed_root / "channel"

    with tempfile.TemporaryDirectory(prefix="fr3-final-worker-return-") as temp_name:
        temp = Path(temp_name)
        payload = temp / f"FR3_RORQUAL_V4_3_FINAL_WORKER_SMOKE_43999_{args.job_id}"
        payload.mkdir()

        copy_tree(result, payload / "result")
        copy_file(channel / "CHANNEL_RECORD.json", payload / "channel/CHANNEL_RECORD.json")
        copy_file(channel / "USER_TOPOLOGY.csv", payload / "channel/USER_TOPOLOGY.csv")
        copy_file(channel / "SECTOR_TOPOLOGY.csv", payload / "channel/SECTOR_TOPOLOGY.csv")
        copy_tree(
            run / "provenance",
            payload / "provenance",
            excluded_names={"FINAL_WORKER_SMOKE_AUTHORIZATION.json"},
        )
        copy_tree(run / "logs", payload / "logs")
        for source, relative in [
            (smoke / "PACKAGE_VERSION.json", "smoke_package/PACKAGE_VERSION.json"),
            (smoke / "PACKAGE_MANIFEST.sha256", "smoke_package/PACKAGE_MANIFEST.sha256"),
            (smoke / "SOURCE_PAYLOAD_MANIFEST.sha256", "smoke_package/SOURCE_PAYLOAD_MANIFEST.sha256"),
            (smoke / "config/FINAL_WORKER_SMOKE_CONTRACT.json", "smoke_package/FINAL_WORKER_SMOKE_CONTRACT.json"),
            (smoke / "immutable_bindings/IMMUTABLE_INPUT_BINDINGS.json", "smoke_package/IMMUTABLE_INPUT_BINDINGS.json"),
            (smoke / "immutable_bindings/ROUTING_CORRECTION_RECORD.json", "smoke_package/ROUTING_CORRECTION_RECORD.json"),
            (job / "JOB_PACKAGE_CONTRACT.json", "locked_job/JOB_PACKAGE_CONTRACT.json"),
            (job / "PHASE1_CAMPAIGN_CONTRACT_V4_3.json", "locked_job/PHASE1_CAMPAIGN_CONTRACT_V4_3.json"),
            (job / "PACKAGE_ID.txt", "locked_job/PACKAGE_ID.txt"),
            (job / "PACKAGE_MANIFEST.sha256", "locked_job/PACKAGE_MANIFEST.sha256"),
            (job / "CANDIDATE_V4_3_SOURCE_MANIFEST.sha256", "locked_job/CANDIDATE_V4_3_SOURCE_MANIFEST.sha256"),
        ]:
            copy_file(source, payload / relative)

        audit = read_json_if(run / "provenance/FINAL_WORKER_SMOKE_AUDIT.json")
        scientific_pass = bool(
            audit
            and audit.get("status")
            == "PASS_EXCLUDED_RORQUAL_FINAL_CAMPAIGN_WORKER_SMOKE_SEED43999"
        )
        state_completed = str(args.slurm_state).startswith("COMPLETED")
        all_exit_pass = all(
            value == 0
            for value in [
                args.worker_exit_code,
                args.structural_validator_exit_code,
                args.pass_validator_exit_code,
                args.independent_audit_exit_code,
            ]
        )
        status = (
            "PASS_EXCLUDED_RORQUAL_FINAL_WORKER_SMOKE_RETURN_READY"
            if state_completed and all_exit_pass and scientific_pass
            else "DIAGNOSTIC_EXCLUDED_RORQUAL_FINAL_WORKER_SMOKE_RETURN_READY"
        )
        metadata = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "job_id": str(args.job_id),
            "slurm_state": str(args.slurm_state),
            "slurm_exit_code": str(args.slurm_exit_code),
            "worker_exit_code": int(args.worker_exit_code),
            "structural_validator_exit_code": int(args.structural_validator_exit_code),
            "scientific_pass_validator_exit_code": int(args.pass_validator_exit_code),
            "independent_audit_exit_code": int(args.independent_audit_exit_code),
            "campaign_seed": 43999,
            "execution_cluster": "rorqual",
            "superseded_nibi_job_id": "18953376",
            "superseded_nibi_result_classification": "ROUTING_CORRECTION_NOT_SCIENTIFIC_EVIDENCE",
            "execution_stage": "EXCLUDED_FINAL_WORKER_SMOKE_SEED43999",
            "channel_regenerated": True,
            "preserved_channel_reused": False,
            "slurm_array_used": False,
            "merge_job_submitted": False,
            "confirmatory_analysis_included": False,
            "full_campaign_execution_authorized": False,
            "authorization_token_included": False,
            "raw_frequency_response_included": False,
            "scientific_smoke_status": audit.get("status") if audit else None,
            "next_gate": (
                "BUILD_AND_INDEPENDENTLY_REVIEW_RORQUAL_NATIVE_LOCKED_30_SEED_CAMPAIGN_PACKAGE"
                if status == "PASS_EXCLUDED_RORQUAL_FINAL_WORKER_SMOKE_RETURN_READY"
                else "DIAGNOSE_FINAL_CAMPAIGN_WORKER_OR_RORQUAL_CHANNEL_REPRODUCTION_BEFORE_ANY_CAMPAIGN_AUTHORIZATION"
            ),
        }
        (payload / "RETURN_METADATA.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        forbidden = [
            path
            for path in payload.rglob("*")
            if path.is_file()
            and (
                "AUTHORIZATION.json" in path.name
                or path.name == "frequency_response.npy"
                or "__pycache__" in path.parts
                or path.suffix in {".pyc", ".pyo"}
            )
        ]
        if forbidden:
            raise RuntimeError(f"forbidden return files: {forbidden}")

        manifest = payload / "RETURN_MANIFEST.sha256"
        lines = []
        for path in sorted(payload.rglob("*")):
            if path.is_file() and path != manifest:
                lines.append(
                    f"{sha256_file(path)}  {path.relative_to(payload).as_posix()}"
                )
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        sidecar = Path(str(output) + ".sha256")
        if sidecar.exists():
            sidecar.unlink()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as bundle:
            for path in sorted(payload.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(temp).as_posix())
        with zipfile.ZipFile(output) as bundle:
            bad = bundle.testzip()
            if bad is not None:
                raise RuntimeError(f"return ZIP CRC failure: {bad}")
        digest = sha256_file(output)
        sidecar.write_text(f"{digest}  {output.name}\n", encoding="utf-8")

    print("FINAL_WORKER_SMOKE_RETURN_PACKAGING=PASS")
    print(f"FINAL_WORKER_SMOKE_RETURN_ZIP={output}")
    print(f"FINAL_WORKER_SMOKE_RETURN_ZIP_SHA256={sha256_file(output)}")
    print(f"FINAL_WORKER_SMOKE_RETURN_STATUS={status}")
    print("AUTHORIZATION_TOKEN_INCLUDED=NO")
    print("RAW_FREQUENCY_RESPONSE_INCLUDED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
