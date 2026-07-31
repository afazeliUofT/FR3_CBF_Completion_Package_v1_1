#!/usr/bin/env python3
"""Build a compact success or diagnostic return for the Nibi deployment smoke."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_if_file(source: Path, target: Path) -> bool:
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def copy_tree_files(source: Path, target: Path) -> int:
    if not source.is_dir():
        return 0
    count = 0
    for path in sorted(source.rglob("*")):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--job-package-root", required=True)
    parser.add_argument("--smoke-package-root", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--smoke-seed", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    run = Path(args.run_root).expanduser().resolve()
    job = Path(args.job_package_root).expanduser().resolve()
    smoke = Path(args.smoke_package_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    staging = run / "return_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    seed_root = run / f"results/noncampaign_smoke_seed_{args.smoke_seed}"
    result_root = seed_root / "result"
    channel_root = seed_root / "channel"

    copied = 0
    copied += copy_tree_files(result_root, staging / "result")
    for name in [
        "CHANNEL_RECORD.json",
        "SECTOR_TOPOLOGY.csv",
        "USER_TOPOLOGY.csv",
    ]:
        copied += int(
            copy_if_file(
                channel_root / name,
                staging / "channel" / name,
            )
        )

    copied += copy_tree_files(run / "provenance", staging / "provenance")
    copied += copy_tree_files(run / "logs", staging / "logs")

    for source, relative in [
        (job / "JOB_PACKAGE_CONTRACT.json", "package/JOB_PACKAGE_CONTRACT.json"),
        (job / "PACKAGE_ID.txt", "package/PACKAGE_ID.txt"),
        (job / "PACKAGE_MANIFEST.sha256", "package/PACKAGE_MANIFEST.sha256"),
        (
            job / "CANDIDATE_AND_REVIEW_BINDING.json",
            "package/CANDIDATE_AND_REVIEW_BINDING.json",
        ),
        (
            smoke / "SMOKE_PACKAGE_CONTRACT.json",
            "smoke/SMOKE_PACKAGE_CONTRACT.json",
        ),
        (
            smoke / "SMOKE_SOURCE_MANIFEST.sha256",
            "smoke/SMOKE_SOURCE_MANIFEST.sha256",
        ),
        (
            smoke / "SMOKE_INDEPENDENT_REVIEW.json",
            "smoke/SMOKE_INDEPENDENT_REVIEW.json",
        ),
    ]:
        copied += int(copy_if_file(source, staging / relative))

    smoke_result = result_root / "NONCAMPAIGN_SMOKE_RESULT.json"
    scientific_status = None
    if smoke_result.is_file():
        scientific_status = json.loads(
            smoke_result.read_text(encoding="utf-8")
        ).get("status")

    metadata = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_RETURN_READY"
            if str(args.state).startswith("COMPLETED")
            and scientific_status
            == (
                "PASS_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_"
                "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS"
            )
            else "DIAGNOSTIC_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_RETURN"
        ),
        "job_id": str(args.job_id),
        "slurm_state": str(args.state),
        "smoke_seed": int(args.smoke_seed),
        "confirmatory_analysis_included": False,
        "analysis_scope": "EXCLUDED_FROM_PHASE1_CONFIRMATORY_ANALYSIS",
        "full_campaign_execution_authorized": False,
        "merge_authorized": False,
        "scientific_smoke_status": scientific_status,
        "copied_file_count_before_metadata": copied,
        "raw_frequency_response_returned": False,
        "raw_channel_location_retained_on_nibi": str(channel_root),
    }
    (staging / "RETURN_METADATA.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    manifest = staging / "RETURN_MANIFEST.sha256"
    lines = []
    for path in sorted(staging.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(staging).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    checksum = Path(str(output) + ".sha256")
    if checksum.exists():
        checksum.unlink()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(
                    path,
                    path.relative_to(staging).as_posix(),
                )
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"corrupt return member: {bad}")
    checksum.write_text(
        f"{sha256_file(output)}  {output.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    print("NONCAMPAIGN NIBI DEPLOYMENT SMOKE RETURN PACKAGE: PASS")
    print("Return ZIP:", output)
    print("Return SHA-256:", sha256_file(output))
    print("Slurm state:", args.state)
    print("Scientific smoke status:", scientific_status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
