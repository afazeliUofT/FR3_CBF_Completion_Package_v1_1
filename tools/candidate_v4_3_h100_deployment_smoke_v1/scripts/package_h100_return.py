#!/usr/bin/env python3
"""Create the compact success/failure return for the excluded H100 smoke."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--payload-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", required=True, choices=("PASS", "FAIL"))
    parser.add_argument("--wrapper-exit", required=True, type=int)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--slurm-exit", required=True)
    parser.add_argument("--maxrss", required=True)
    parser.add_argument("--candidate-exit", required=True)
    parser.add_argument("--audit-exit", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    run = Path(args.run_root).expanduser().resolve()
    payload = Path(args.payload_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    entries: list[tuple[Path, str]] = []

    def add(path: Path, arcname: str) -> None:
        if path.is_file():
            entries.append((path, arcname))

    # Package/source bindings and the exact review/smoke implementation.
    for relative in (
        "PACKAGE_VERSION.json",
        "PACKAGE_MANIFEST.sha256",
        "SOURCE_PAYLOAD_MANIFEST.sha256",
        "README.md",
        "requirements.txt",
        "config/H100_DEPLOYMENT_SMOKE_CONTRACT.json",
        "immutable_bindings/V4_3_RETURN_BINDING.json",
        "local_diagnostics/INDEPENDENT_V4_3_REVIEW.json",
        "local_diagnostics/INDEPENDENT_V4_3_REVIEW.env",
        "scripts/independent_review_v4_3.py",
        "scripts/capture_h100_environment.py",
        "scripts/audit_h100_deployment_smoke.py",
        "scripts/package_h100_return.py",
        "wrappers/REMOTE_ORCHESTRATE_V4_3_H100_DEPLOYMENT_SMOKE.sh",
        "wrappers/RUN_V4_3_H100_DEPLOYMENT_SMOKE_FROM_WSL.sh",
        "candidate_v4_3_package/PACKAGE_VERSION.json",
        "candidate_v4_3_package/SOURCE_PAYLOAD_MANIFEST.sha256",
        "candidate_v4_3_package/config/CANDIDATE_V4_3_CONTRACT.json",
        "candidate_v4_3_package/scripts/run_seed43999_floor_feasibility_candidate_v4_3.py",
        "candidate_v4_3_package/src/fr3_cbf/floor_feasibility_repair.py",
        "candidate_v4_3_package/src/fr3_cbf/__init__.py",
    ):
        add(payload / relative, f"package/{relative}")

    docs = payload / "docs"
    if docs.is_dir():
        for path in sorted(docs.rglob("*")):
            if path.is_file():
                add(path, f"package/docs/{path.relative_to(docs).as_posix()}")

    # Runtime and Slurm records.
    for relative in (
        "REMOTE_RUN_SUMMARY.env",
        "REMOTE_PREJOB_FAILURE.env",
        "scientific_stdout.txt",
        "scientific_stderr.txt",
        "candidate_exit_code.txt",
        "audit_stdout.txt",
        "audit_stderr.txt",
        "audit_exit_code.txt",
        "python_environment.txt",
        "pip_freeze_exact.txt",
        "nvidia_smi.txt",
        "H100_ENVIRONMENT.json",
        "H100_DEPLOYMENT_SMOKE_AUDIT.json",
        "H100_DEPLOYMENT_SMOKE_STATUS.env",
        "CANDIDATE_UTILITY_SUMMARY.csv",
        "slurm_job_id.txt",
    ):
        add(run / relative, f"runtime/{relative}")

    slurm = run / "slurm"
    if slurm.is_dir():
        for path in sorted(slurm.rglob("*")):
            if path.is_file():
                add(path, f"slurm/{path.relative_to(slurm).as_posix()}")

    summary = run / "summary"
    if summary.is_dir():
        for path in sorted(summary.rglob("*")):
            if path.is_file():
                add(path, f"summary/{path.relative_to(summary).as_posix()}")

    # Immutable channel record only; never return the large channel arrays.
    add(run / "CHANNEL_RECORD.json", "immutable_channel/CHANNEL_RECORD.json")

    metadata = {
        "schema_version": 1,
        "status": "PASS_RETURN_READY" if args.mode == "PASS" else "FAIL_RETURN_READY",
        "mode": args.mode,
        "candidate_version": "v4.3",
        "execution_scope": "SINGLE_EXCLUDED_H100_DEPLOYMENT_SMOKE_ONLY",
        "excluded_seed": 43999,
        "remote_wrapper_exit_code": args.wrapper_exit,
        "slurm_job_id": args.job_id,
        "slurm_account": args.account,
        "slurm_state": args.state,
        "slurm_exit_code": args.slurm_exit,
        "slurm_maxrss": args.maxrss,
        "candidate_script_exit_code": args.candidate_exit,
        "independent_audit_exit_code": args.audit_exit,
        "candidate_source_commit": args.source_commit,
        "channel_reused": True,
        "channel_regenerated": False,
        "confirmatory_campaign_authorized": False,
    }
    metadata_path = run / "RETURN_METADATA.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    add(metadata_path, "RETURN_METADATA.json")

    # Deterministic archive order and no duplicates.
    dedup: dict[str, Path] = {}
    for path, arcname in entries:
        dedup[arcname] = path
    entries = [(path, arc) for arc, path in sorted(dedup.items())]

    manifest_lines = [
        f"{sha256_file(path)}  {arcname}" for path, arcname in entries
    ]
    manifest_path = run / "RETURN_CONTENT_MANIFEST.sha256"
    manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    entries.append((manifest_path, "RETURN_CONTENT_MANIFEST.sha256"))

    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
    ) as archive:
        for path, arcname in entries:
            archive.write(path, arcname)
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"bad ZIP member: {bad}")
    print(f"RETURN_ZIP={output}")
    print(f"RETURN_ZIP_SHA256={sha256_file(output)}")
    print(f"RETURN_ZIP_FILE_COUNT={len(entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
