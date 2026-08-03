#!/usr/bin/env python3
"""Package compact success or failure evidence for holdout completion R1."""
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


def copy_if(source: Path, target: Path) -> None:
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-root", required=True)
    p.add_argument("--repair-package-root", required=True)
    p.add_argument("--merged-root", required=True)
    p.add_argument("--completion-audit", required=True)
    p.add_argument("--completion-tex", required=True)
    p.add_argument("--seed-job-id", required=True)
    p.add_argument("--merge-job-id", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    run = Path(args.run_root).resolve()
    repair = Path(args.repair_package_root).resolve()
    merged = Path(args.merged_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R1_{args.seed_job_id}"
    archive_path = output_dir / f"{name}.zip"

    with tempfile.TemporaryDirectory(prefix="fr3-v45-completion-return-") as td:
        payload = Path(td) / name
        payload.mkdir()
        copy_if(Path(args.completion_audit), payload / "HOLDOUT_COMPLETION_AUDIT.json")
        copy_if(Path(args.completion_tex), payload / "paper" / "holdout_key_results.tex")
        for rel in (
            "PHASE1_MERGED_AUDIT.json",
            "PHASE1_BOOTSTRAP_SUMMARY.json",
            "PHASE1_SEED_CLUSTER_EFFECTS.csv",
            "PHASE1_METHOD_ENDPOINT_SUMMARY.csv",
            "PHASE1_PASS_SPECIFIC_EFFECTS.csv",
            "PHASE1_LEAVE_ONE_PASS_OUT.csv",
            "PHASE1_ACTION_AND_RUNTIME_SUMMARY.json",
            "PHASE1_SEED_RESULT_HASH_INDEX.csv",
            "FR3_PHASE1_MERGED_REVIEW_RETURN.zip",
            "FR3_PHASE1_MERGED_REVIEW_RETURN.zip.sha256",
        ):
            copy_if(merged / rel, payload / "merged" / rel)
        seed_root = run / "results" / "seed_44052"
        for rel in (
            "FR3_PHASE1_SEED_44052_RETURN.zip",
            "FR3_PHASE1_SEED_44052_RETURN.zip.sha256",
            "worker_stdout.log",
            "worker_stderr.log",
        ):
            copy_if(seed_root / rel, payload / "seed_44052" / rel)
        for rel in (
            "result/SEED_RESULT.json",
            "result/RESULT_FILE_MANIFEST.json",
            "result/IMPLEMENTATION_CAPACITY_OVERLAY.json",
            "channel/CHANNEL_RECORD.json",
        ):
            copy_if(seed_root / rel, payload / "seed_44052" / rel)
        for rel in (
            "config/HOLDOUT_COMPLETION_REPAIR_CONTRACT.json",
            "scripts/validate_seed_result_repaired.py",
            "scripts/run_seed44052_capacity_completion.py",
            "scripts/audit_completed_holdout.py",
        ):
            copy_if(repair / rel, payload / "repair_source" / rel)
        slurm = run / "holdout_completion_r1" / "slurm"
        if slurm.is_dir():
            for source in sorted(slurm.iterdir()):
                if source.is_file():
                    copy_if(source, payload / "slurm" / source.name)
        metadata = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "seed_job_id": str(args.seed_job_id),
            "merge_job_id": str(args.merge_job_id),
            "existing_holdout_array_job_id": "18163102",
            "seed_rerun_list": [44052],
            "channel_regenerated": False,
            "gpu_requested": False,
            "validator_repair_applied": True,
            "implementation_capacity_repair_applied": True,
            "scientific_source_files_modified": False,
            "automatic_extra_seeds_authorized": False,
            "authorization_token_included": False,
        }
        write_json(payload / "RETURN_METADATA.json", metadata)
        manifest_lines = []
        for source in sorted(payload.rglob("*")):
            if source.is_file() and source.name != "RETURN_MANIFEST.sha256":
                manifest_lines.append(
                    f"{sha256_file(source)}  {source.relative_to(payload).as_posix()}\n"
                )
        (payload / "RETURN_MANIFEST.sha256").write_text(
            "".join(manifest_lines), encoding="utf-8"
        )
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for source in sorted(payload.rglob("*")):
                if source.is_file():
                    zf.write(source, source.relative_to(Path(td)).as_posix())
    with zipfile.ZipFile(archive_path) as zf:
        if zf.testzip() is not None:
            raise RuntimeError("completion return ZIP CRC failure")
    digest = sha256_file(archive_path)
    sidecar = Path(str(archive_path) + ".sha256")
    sidecar.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    print("HOLDOUT_COMPLETION_RETURN_PACKAGING=PASS")
    print("HOLDOUT_COMPLETION_RETURN_ZIP=" + str(archive_path))
    print("HOLDOUT_COMPLETION_RETURN_ZIP_SHA256=" + digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
