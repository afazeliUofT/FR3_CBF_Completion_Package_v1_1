#!/usr/bin/env python3
"""Package a compact, manifest-bound v4.4 scheduling development return."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

FAILED_SEEDS = [44001, 44007, 44008, 44013, 44017, 44018, 44024, 44025, 44026, 44027, 44028]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def copy_if(source: Path, target: Path) -> None:
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-root", type=Path, required=True)
    p.add_argument("--package-root", type=Path, required=True)
    p.add_argument("--array-job-id", required=True)
    p.add_argument("--merge-job-id", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    a = p.parse_args()
    run_root = a.run_root.resolve()
    package_root = a.package_root.resolve()
    output_dir = a.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"FR3_RORQUAL_V4_4_PROTECTED_SUBBAND_SCHEDULING_DEVELOPMENT_{a.array_job_id}"
    staging = output_dir / name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    for source, relative in [
        (package_root / "PACKAGE_VERSION.json", "bindings/PACKAGE_VERSION.json"),
        (package_root / "SOURCE_PAYLOAD_MANIFEST.sha256", "bindings/SOURCE_PAYLOAD_MANIFEST.sha256"),
        (package_root / "config/V44_SCHEDULING_DEVELOPMENT_CONTRACT.json", "bindings/V44_SCHEDULING_DEVELOPMENT_CONTRACT.json"),
        (package_root / "src/fr3_cbf/protected_subband_scheduler.py", "candidate_source/protected_subband_scheduler.py"),
        (package_root / "src/fr3_cbf/candidate_v4_4_scheduling_campaign.py", "candidate_source/candidate_v4_4_scheduling_campaign.py"),
        (package_root / "scripts/replay_v44_scheduling_seed.py", "candidate_source/replay_v44_scheduling_seed.py"),
        (package_root / "scripts/merge_v44_scheduling_development.py", "candidate_source/merge_v44_scheduling_development.py"),
        (run_root / "local_audit/IMMUTABLE_FAILED_SEED_DIAGNOSIS_AUDIT.json", "audits/IMMUTABLE_FAILED_SEED_DIAGNOSIS_AUDIT.json"),
        (run_root / "local_audit/SCHEDULING_NECESSITY_AND_PLAUSIBILITY_AUDIT.json", "audits/SCHEDULING_NECESSITY_AND_PLAUSIBILITY_AUDIT.json"),
        (run_root / "slurm/sacct_v44_scheduling.txt", "slurm/sacct_v44_scheduling.txt"),
        (run_root / "V44_OVERLAY_MANIFEST.sha256", "bindings/V44_OVERLAY_MANIFEST.sha256"),
    ]:
        copy_if(source, staging / relative)

    if (run_root / "merged").is_dir():
        shutil.copytree(run_root / "merged", staging / "merged", dirs_exist_ok=True)
    if (run_root / "logs").is_dir():
        shutil.copytree(run_root / "logs", staging / "logs", dirs_exist_ok=True)

    returned = 0
    for seed in FAILED_SEEDS:
        task = run_root / "tasks" / f"seed_{seed}"
        result = task / "result"
        target = staging / "seed_results" / f"seed_{seed}"
        if result.is_dir():
            shutil.copytree(result, target / "result", dirs_exist_ok=True)
            returned += 1
        for filename in ("stdout.log", "stderr.log", "process_exit_code.txt", "TASK_STATUS.json"):
            copy_if(task / filename, target / filename)

    summary_path = run_root / "merged/V44_SCHEDULING_DEVELOPMENT_SUMMARY.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    else:
        summary = {
            "status": "FAIL_INFRASTRUCTURE_NO_V44_SCHEDULING_SUMMARY",
            "next_gate": "DIAGNOSE_V44_SCHEDULING_INFRASTRUCTURE",
        }
    metadata = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": summary.get("status", "UNKNOWN"),
        "next_gate": summary.get("next_gate", "REVIEW_REQUIRED"),
        "array_job_id": str(a.array_job_id),
        "merge_job_id": str(a.merge_job_id),
        "failed_seed_return_count": returned,
        "expected_failed_seed_return_count": len(FAILED_SEEDS),
        "channel_regenerated": False,
        "gpu_requested": False,
        "raw_channels_included": False,
        "fresh_confirmation": False,
        "campaign_rerun_authorized": False,
    }
    (staging / "RETURN_METADATA.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest = []
    for path in sorted(staging.rglob("*")):
        if path.is_file() and path.name != "RETURN_MANIFEST.sha256":
            manifest.append(f"{sha256_file(path)}  {path.relative_to(staging).as_posix()}")
    (staging / "RETURN_MANIFEST.sha256").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    zip_path = output_dir / f"{name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=f"{name}/{path.relative_to(staging).as_posix()}")
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"return ZIP CRC failure: {bad}")
    digest = sha256_file(zip_path)
    sidecar = Path(str(zip_path) + ".sha256")
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    shutil.rmtree(staging)

    print("V44_SCHEDULING_RETURN_PACKAGING=PASS")
    print(f"REMOTE_RETURN_ZIP={zip_path}")
    print(f"REMOTE_RETURN_ZIP_SHA256={digest}")
    print(f"DIAGNOSTIC_SEED_RETURN_COUNT={returned}")
    print(f"V44_SCHEDULING_DEVELOPMENT_STATUS={summary.get('status', 'UNKNOWN')}")
    print(f"NEXT_GATE={summary.get('next_gate', 'REVIEW_REQUIRED')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
