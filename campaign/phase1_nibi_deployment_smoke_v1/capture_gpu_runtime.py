#!/usr/bin/env python3
"""Capture exact GPU, driver, CUDA, Slurm, and package runtime information."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

import torch


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command(command: list[str]) -> str:
    return subprocess.check_output(
        command,
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--environment-lock", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is not visible in the smoke job")
    name = torch.cuda.get_device_name(0)
    props = torch.cuda.get_device_properties(0)
    if "H100" not in name or props.total_memory < 75 * 1024**3:
        raise RuntimeError(
            f"deployment smoke requires H100 80 GB-class GPU: "
            f"{name}, {props.total_memory / 1024**3:.2f} GiB"
        )

    query = command(
        [
            "nvidia-smi",
            "--query-gpu=name,uuid,driver_version,memory.total,"
            "compute_cap,pci.bus_id,serial",
            "--format=csv,noheader,nounits",
        ]
    )
    value = {
        "schema_version": 1,
        "status": "PASS_NIBI_H100_RUNTIME_PROBE",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "slurm": {
            key: os.environ.get(key)
            for key in [
                "SLURM_JOB_ID",
                "SLURM_JOB_NAME",
                "SLURM_JOB_NODELIST",
                "SLURM_CPUS_PER_TASK",
                "SLURM_GPUS",
                "SLURM_JOB_ACCOUNT",
                "CUDA_VISIBLE_DEVICES",
            ]
        },
        "nvidia_smi_query": query,
        "nvidia_smi_full": command(["nvidia-smi"]),
        "torch": {
            "version": torch.__version__,
            "cuda_build": torch.version.cuda,
            "cudnn_version": torch.backends.cudnn.version(),
            "device_name": name,
            "device_count": torch.cuda.device_count(),
            "device_total_memory_bytes": int(props.total_memory),
            "compute_capability": list(torch.cuda.get_device_capability(0)),
        },
        "environment_lock_sha256": sha256_file(
            Path(args.environment_lock).expanduser().resolve()
        ),
        "smoke_token_sha256": sha256_file(
            Path(args.token).expanduser().resolve()
        ),
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    Path(str(output) + ".sha256").write_text(
        f"{sha256_file(output)}  {output.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    print("NIBI H100 RUNTIME PROBE: PASS")
    print("GPU:", name)
    print("Driver/runtime record:", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
