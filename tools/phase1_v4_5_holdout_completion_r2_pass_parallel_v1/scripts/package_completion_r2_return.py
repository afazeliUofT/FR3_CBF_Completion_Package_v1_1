#!/usr/bin/env python3
"""Package compact success, scientific-nonzero, or partial evidence for R2."""
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
    p.add_argument("--package-root", required=True)
    p.add_argument("--completion-root", required=True)
    p.add_argument("--pass-array-job-id", required=True)
    p.add_argument("--assembly-job-id", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    run = Path(args.run_root).resolve()
    package = Path(args.package_root).resolve()
    completion = Path(args.completion_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"FR3_RORQUAL_V4_5_HOLDOUT_COMPLETION_R2_{args.pass_array_job_id}"
    archive = output_dir / f"{name}.zip"

    with tempfile.TemporaryDirectory(prefix="fr3-v45-r2-return-") as td:
        payload = Path(td) / name
        payload.mkdir()
        for rel in (
            "HOLDOUT_COMPLETION_AUDIT.json",
            "holdout_key_results.tex",
            "R1_TIMEOUT_AUDIT.json",
            "PASS_PARALLEL_EQUIVALENCE_AUDIT.json",
            "ACTIVE_COMPLETION_R2.env",
        ):
            copy_if(completion / rel, payload / rel)
        merged = completion / "merged"
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
            "PHASE1_MERGE_INCOMPLETE.json",
        ):
            copy_if(merged / rel, payload / "merged" / rel)
        seed_root = run / "results" / "seed_44052"
        for rel in (
            "FR3_PHASE1_SEED_44052_RETURN.zip",
            "FR3_PHASE1_SEED_44052_RETURN.zip.sha256",
            "result/SEED_RESULT.json",
            "result/RESULT_FILE_MANIFEST.json",
            "result/IMPLEMENTATION_CAPACITY_OVERLAY.json",
            "channel/CHANNEL_RECORD.json",
        ):
            copy_if(seed_root / rel, payload / "seed_44052" / rel)
        pass_root = completion / "pass_outputs"
        if pass_root.is_dir():
            for pass_dir in sorted(pass_root.glob("pass_*")):
                if not pass_dir.is_dir():
                    continue
                for source in sorted(pass_dir.iterdir()):
                    if source.is_file() and source.suffix not in {".npy", ".npz"}:
                        copy_if(source, payload / "pass_outputs" / pass_dir.name / source.name)
        slurm = completion / "slurm"
        if slurm.is_dir():
            for source in sorted(slurm.iterdir()):
                if source.is_file():
                    copy_if(source, payload / "slurm" / source.name)
        for rel in (
            "PACKAGE_VERSION.json",
            "config/HOLDOUT_COMPLETION_R2_CONTRACT.json",
            "scripts/audit_r1_timeout.py",
            "scripts/audit_pass_parallel_equivalence.py",
            "scripts/run_seed44052_pass.py",
            "scripts/assemble_seed44052.py",
            "scripts/validate_seed_result_repaired.py",
            "scripts/audit_completed_holdout.py",
        ):
            copy_if(package / rel, payload / "repair_source" / rel)
        metadata = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "pass_array_job_id": str(args.pass_array_job_id),
            "assembly_job_id": str(args.assembly_job_id),
            "existing_holdout_array_job_id": "18163102",
            "prior_completion_seed_job_id": "18207112",
            "seed_rerun_list": [44052],
            "pass_slots": [0, 1, 2, 3, 4],
            "channel_regenerated": False,
            "gpu_requested": False,
            "pass_parallelization_applied": True,
            "implementation_capacity_repair_applied": True,
            "validator_repair_applied": True,
            "scientific_source_files_modified": False,
            "action_library_definition_changed": False,
            "automatic_extra_seeds_authorized": False,
            "authorization_token_included": False,
        }
        write_json(payload / "RETURN_METADATA.json", metadata)
        lines = []
        for source in sorted(payload.rglob("*")):
            if source.is_file() and source.name != "RETURN_MANIFEST.sha256":
                lines.append(
                    f"{sha256_file(source)}  {source.relative_to(payload).as_posix()}\n"
                )
        (payload / "RETURN_MANIFEST.sha256").write_text("".join(lines), encoding="utf-8")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for source in sorted(payload.rglob("*")):
                if source.is_file():
                    zf.write(source, source.relative_to(Path(td)).as_posix())
    with zipfile.ZipFile(archive) as zf:
        if zf.testzip() is not None:
            raise RuntimeError("R2 return ZIP CRC failure")
    digest = sha256_file(archive)
    Path(str(archive) + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    print("HOLDOUT_COMPLETION_R2_RETURN_PACKAGING=PASS")
    print("HOLDOUT_COMPLETION_R2_RETURN_ZIP=" + str(archive))
    print("HOLDOUT_COMPLETION_R2_RETURN_ZIP_SHA256=" + digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
