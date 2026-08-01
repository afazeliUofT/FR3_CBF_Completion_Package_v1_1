#!/usr/bin/env python3
"""Verify one H100 is visible and the preserved channel is usable on CUDA."""
from __future__ import annotations

import argparse
import json
import math
import platform
from pathlib import Path
import subprocess

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel-root", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    import torch

    channel_root = Path(args.channel_root).expanduser().resolve()
    output = Path(args.output_json).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    count = torch.cuda.device_count()
    if count != 1:
        raise RuntimeError(f"expected exactly one visible GPU, found {count}")
    device = torch.device("cuda:0")
    props = torch.cuda.get_device_properties(device)
    name = torch.cuda.get_device_name(device)
    memory = int(props.total_memory)
    if "H100" not in name or memory < 75 * 1024**3:
        raise RuntimeError(
            f"expected H100 80GB-class GPU, found {name} with {memory / 1024**3:.3f} GiB"
        )

    # Deterministic float64 arithmetic check.
    rng = np.random.default_rng(43999)
    a_np = rng.standard_normal((128, 64), dtype=np.float64)
    b_np = rng.standard_normal((64, 32), dtype=np.float64)
    cpu = a_np @ b_np
    a = torch.from_numpy(a_np).to(device)
    b = torch.from_numpy(b_np).to(device)
    gpu = (a @ b).cpu().numpy()
    float64_max_abs = float(np.max(np.abs(cpu - gpu)))
    float64_relative = float(
        np.linalg.norm(cpu - gpu) / max(np.linalg.norm(cpu), np.finfo(float).tiny)
    )

    # Read a bounded slice of the immutable complex64 channel through mmap,
    # move it to the H100, and compare an energy reduction.
    response = np.load(channel_root / "frequency_response.npy", mmap_mode="r")
    # Keep this bounded even if the export shape changes.
    slices = tuple(slice(0, min(int(dim), limit)) for dim, limit in zip(
        response.shape, (2, 8, 8, 16)
    ))
    sample = np.ascontiguousarray(response[slices])
    sample_gpu = torch.from_numpy(sample).to(device)
    cpu_energy = float(np.sum(np.abs(sample.astype(np.complex128)) ** 2))
    gpu_energy = float(
        torch.sum(torch.abs(sample_gpu.to(torch.complex128)) ** 2).cpu().item()
    )
    complex_energy_relative = abs(cpu_energy - gpu_energy) / max(
        abs(cpu_energy), np.finfo(float).tiny
    )
    if float64_relative > 5e-13:
        raise RuntimeError(f"H100 float64 relative error too large: {float64_relative}")
    if complex_energy_relative > 5e-13:
        raise RuntimeError(
            f"H100 preserved-channel energy error too large: {complex_energy_relative}"
        )

    try:
        nvidia_smi = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,uuid,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
    except Exception as exc:  # pragma: no cover - cluster diagnostic only
        nvidia_smi = f"UNAVAILABLE:{type(exc).__name__}:{exc}"

    record = {
        "schema_version": 1,
        "status": "PASS_H100_ENVIRONMENT_AND_PRESERVED_CHANNEL_ACCESS",
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "cuda_device_count": count,
        "gpu_name": name,
        "gpu_total_memory_bytes": memory,
        "gpu_total_memory_gib": memory / 1024**3,
        "nvidia_smi": nvidia_smi,
        "float64_matmul_max_abs_error": float64_max_abs,
        "float64_matmul_relative_error": float64_relative,
        "preserved_channel_shape": list(response.shape),
        "preserved_channel_dtype": str(response.dtype),
        "preserved_channel_sample_shape": list(sample.shape),
        "preserved_channel_sample_cpu_energy": cpu_energy,
        "preserved_channel_sample_gpu_energy": gpu_energy,
        "preserved_channel_sample_energy_relative_error": complex_energy_relative,
        "channel_regenerated": False,
        "controller_replay_execution": "CPU_NUMPY_SCIPY_HIGHS_ON_H100_NODE",
        "confirmatory_campaign_authorized": False,
    }
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print("H100_ENVIRONMENT_GATE=PASS")
    print(f"H100_GPU_NAME={name}")
    print(f"H100_GPU_TOTAL_MEMORY_GIB={memory / 1024**3:.6f}")
    print(f"H100_FLOAT64_RELATIVE_ERROR={float64_relative:.17g}")
    print(f"H100_CHANNEL_ENERGY_RELATIVE_ERROR={complex_energy_relative:.17g}")
    print("H100_CHANNEL_REGENERATION=NO")
    print("CONTROLLER_REPLAY_EXECUTION=CPU_NUMPY_SCIPY_HIGHS_ON_H100_NODE")
    print("CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
