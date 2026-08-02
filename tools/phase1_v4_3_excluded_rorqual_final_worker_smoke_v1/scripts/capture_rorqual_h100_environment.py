#!/usr/bin/env python3
"""Capture and validate the final-worker Rorqual H100 runtime environment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import socket
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    import torch

    hostname = socket.getfqdn()
    if "rorqual" not in hostname.lower():
        raise RuntimeError(f"runtime host is not Rorqual: {hostname}")

    exact_versions = {
        "torch": "2.9.1",
        "sionna-no-rt": "2.0.1",
        "numpy": "2.4.2",
        "scipy": "1.17.0",
        "pandas": "2.3.3",
    }
    actual_versions = {
        name: importlib.metadata.version(name).split("+", 1)[0]
        for name in exact_versions
    }
    mismatches = {
        name: {"expected": expected, "actual": actual_versions[name]}
        for name, expected in exact_versions.items()
        if actual_versions[name] != expected
    }
    if mismatches:
        raise RuntimeError(f"Rorqual environment version mismatch: {mismatches}")
    if platform.python_version() != "3.12.4":
        raise RuntimeError(
            "Rorqual Python mismatch: "
            f"{platform.python_version()} != 3.12.4"
        )
    if str(torch.version.cuda) != "12.6":
        raise RuntimeError(
            f"Rorqual CUDA build mismatch: {torch.version.cuda} != 12.6"
        )

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not visible in the Rorqual H100 smoke allocation")
    count = int(torch.cuda.device_count())
    if count != 1:
        raise RuntimeError(f"expected exactly one visible GPU, found {count}")
    name = torch.cuda.get_device_name(0)
    memory = int(torch.cuda.get_device_properties(0).total_memory)
    if "H100" not in name:
        raise RuntimeError(f"allocated GPU is not an H100: {name}")
    if memory < 75 * 1024**3:
        raise RuntimeError(f"H100 memory is unexpectedly small: {memory}")

    generator = torch.Generator(device="cpu").manual_seed(20260802)
    a = torch.randn((64, 64), dtype=torch.float64, generator=generator)
    b = torch.randn((64, 64), dtype=torch.float64, generator=generator)
    cpu = a @ b
    gpu = (a.cuda() @ b.cuda()).cpu()
    max_abs = float(torch.max(torch.abs(cpu - gpu)))
    denom = float(torch.max(torch.abs(cpu)))
    rel = max_abs / max(denom, 1e-300)
    if rel > 1e-12:
        raise RuntimeError(f"float64 CPU/GPU probe relative error is too large: {rel}")

    try:
        nvidia_smi = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,uuid,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception as exc:  # pragma: no cover - only on cluster
        nvidia_smi = f"UNAVAILABLE: {exc}"

    value = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_RORQUAL_H100_FINAL_WORKER_ENVIRONMENT",
        "exact_reference_environment_gate": "PASS",
        "expected_versions": exact_versions,
        "actual_versions": actual_versions,
        "hostname": hostname,
        "cluster": "rorqual",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "sionna_no_rt": importlib.metadata.version("sionna-no-rt"),
        "numpy": importlib.metadata.version("numpy"),
        "scipy": importlib.metadata.version("scipy"),
        "pandas": importlib.metadata.version("pandas"),
        "cuda_device_count": count,
        "gpu_name": name,
        "gpu_total_memory_bytes": memory,
        "gpu_total_memory_gib": memory / 1024**3,
        "nvidia_smi": nvidia_smi,
        "float64_matmul_max_abs_error": max_abs,
        "float64_matmul_relative_error": rel,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_account": os.environ.get("SLURM_JOB_ACCOUNT"),
        "slurm_node": os.environ.get("SLURMD_NODENAME"),
        "slurm_cpus_per_task": os.environ.get("SLURM_CPUS_PER_TASK"),
        "execution_scope": "EXCLUDED_FINAL_WORKER_SMOKE_SEED43999_ONLY",
        "channel_generation_required": True,
        "preserved_channel_reused": False,
        "full_campaign_execution_authorized": False,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RORQUAL_H100_FINAL_WORKER_ENVIRONMENT_GATE=PASS")
    print("RORQUAL_EXACT_REFERENCE_ENVIRONMENT_GATE=PASS")
    print(f"RORQUAL_GPU_NAME={name}")
    print(f"RORQUAL_GPU_MEMORY_GIB={memory / 1024**3:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
