#!/usr/bin/env python3
"""Fail-closed static validation of the generated Narval pilot package."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/tr38901_narval_dlp_pilot_prep.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    upload = ROOT / cfg["outputs"]["upload_dir"]
    bundle = upload / "FR3_DLP_RZF_NARVAL_ONE_SEED_GPU_PILOT_v1.zip"
    if not bundle.is_file():
        raise FileNotFoundError(bundle)

    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Corrupt bundle member: {bad}")
        required = {
            "RUN_NARVAL_ONE_SEED_DLP_RZF_PILOT.sh",
            "setup_environment.sh",
            "pilot_worker.sh",
            "run_gpu_pilot.py",
            "validate_gpu_pilot.py",
            "BUNDLE_METADATA.json",
            "BUNDLE_MANIFEST.sha256",
            "input/SIONNA_INCUMBENT_LOCAL_FRAME.csv",
            "input/SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT.json",
        }
        missing = sorted(required - set(names))
        if missing:
            raise RuntimeError(f"Missing Narval bundle members: {missing}")

        all_text = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in names
            if name.endswith((".py", ".sh", ".json", ".md", ".txt"))
        )
        checks = {
            "--gpus-per-node=a100:1": "--gpus-per-node=a100:1" in all_text,
            "--cpus-per-task=12": "--cpus-per-task=12" in all_text,
            "--mem=124G": "--mem=124G" in all_text,
            "narval-only venv": "fr3-sionna2-2.0.1-narval-cu128" in all_text,
            "A100 validation": '"A100"' in all_text or "'A100'" in all_text,
            "chunked channel": "channel_user_chunk_size" in all_text,
            "negative steering phase": "torch.exp(-1j * phase)" in all_text,
            "frozen local frame": "SIONNA_INCUMBENT_LOCAL_FRAME.csv" in all_text,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise RuntimeError(f"Narval source checks failed: {failed}")
        if "h100:1" in all_text.lower() or "--gpus=h100" in all_text.lower():
            raise RuntimeError("H100/Nibi GPU request remains in Narval bundle")
        metadata = json.loads(archive.read("BUNDLE_METADATA.json"))
        if metadata["cluster"] != "narval" or metadata["gpu"] != "A100-40GB":
            raise RuntimeError("Narval metadata is inconsistent")

    print("NARVAL PILOT BUNDLE SOURCE VALIDATION: PASS")
    print("Bundle:", bundle)
    print("Members:", len(names))
    for name in checks:
        print("  PASS:", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
