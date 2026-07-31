#!/usr/bin/env python3
"""Freeze the exact resolved Nibi software environment before smoke execution."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def optional_hash(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def distribution_record(name: str) -> dict[str, object]:
    dist = importlib.metadata.distribution(name)
    root = Path(getattr(dist, "_path"))
    metadata = root / "METADATA"
    record = root / "RECORD"
    wheel = root / "WHEEL"
    return {
        "requested_name": name,
        "canonical_name": dist.metadata.get("Name", name),
        "version": dist.version,
        "dist_info_path": str(root),
        "metadata_sha256": optional_hash(metadata),
        "record_sha256": optional_hash(record),
        "wheel_sha256": optional_hash(wheel),
    }


def command_text(command: list[str]) -> str:
    return subprocess.check_output(
        command,
        text=True,
        stderr=subprocess.STDOUT,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--pip-freeze", required=True)
    parser.add_argument("--module-list", required=True)
    parser.add_argument("--setup-log", required=True)
    parser.add_argument("--job-package-zip", required=True)
    parser.add_argument("--smoke-package-zip", required=True)
    parser.add_argument("--job-package-id", required=True)
    parser.add_argument("--job-package-sha256", required=True)
    parser.add_argument("--smoke-package-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--smoke-seed", type=int, required=True)
    args = parser.parse_args()

    import numpy
    import pandas
    import scipy
    import torch

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    pip_freeze = Path(args.pip_freeze).expanduser().resolve()
    module_list = Path(args.module_list).expanduser().resolve()
    setup_log = Path(args.setup_log).expanduser().resolve()
    job_zip = Path(args.job_package_zip).expanduser().resolve()
    smoke_zip = Path(args.smoke_package_zip).expanduser().resolve()

    freeze_text = command_text(
        [sys.executable, "-m", "pip", "freeze", "--all"]
    )
    pip_freeze.write_text(freeze_text, encoding="utf-8", newline="\n")

    packages = [
        "torch",
        "sionna-no-rt",
        "numpy",
        "scipy",
        "pandas",
        "h5py",
        "matplotlib",
        "pyproj",
        "packaging",
        "setuptools",
        "pip",
        "wheel",
    ]
    distributions = {}
    for name in packages:
        try:
            distributions[name] = distribution_record(name)
        except importlib.metadata.PackageNotFoundError:
            distributions[name] = {"requested_name": name, "installed": False}

    actual_job_sha = sha256_file(job_zip)
    actual_smoke_sha = sha256_file(smoke_zip)
    if actual_job_sha != args.job_package_sha256:
        raise ValueError("job-package ZIP SHA-256 mismatch during environment freeze")
    if actual_smoke_sha != args.smoke_package_sha256:
        raise ValueError("smoke-package ZIP SHA-256 mismatch during environment freeze")

    value = {
        "schema_version": 1,
        "status": "PASS_EXACT_NIBI_SOFTWARE_ENVIRONMENT_LOCK_PRE_GPU",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": {
            "version": sys.version,
            "version_info": list(sys.version_info[:5]),
            "executable": sys.executable,
            "executable_sha256": sha256_file(Path(sys.executable)),
            "implementation": platform.python_implementation(),
        },
        "torch": {
            "version": torch.__version__,
            "cuda_build": torch.version.cuda,
            "cuda_available_on_login_node": bool(torch.cuda.is_available()),
        },
        "sionna_no_rt_version": importlib.metadata.version("sionna-no-rt"),
        "numpy_version": numpy.__version__,
        "scipy_version": scipy.__version__,
        "pandas_version": pandas.__version__,
        "distributions": distributions,
        "pip_freeze_path": str(pip_freeze),
        "pip_freeze_sha256": sha256_file(pip_freeze),
        "module_list_path": str(module_list),
        "module_list_sha256": sha256_file(module_list),
        "setup_log_path": str(setup_log),
        "setup_log_sha256": sha256_file(setup_log),
        "job_package": {
            "package_id": args.job_package_id,
            "zip_path": str(job_zip),
            "zip_sha256": actual_job_sha,
        },
        "smoke_package": {
            "zip_path": str(smoke_zip),
            "zip_sha256": actual_smoke_sha,
            "source_commit": args.source_commit,
            "smoke_seed": int(args.smoke_seed),
        },
        "environment_scope": "NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_ONLY",
        "full_campaign_execution_authorized": False,
        "merge_authorized": False,
    }
    output.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    checksum = Path(str(output) + ".sha256")
    checksum.write_text(
        f"{sha256_file(output)}  {output.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    print("EXACT NIBI SOFTWARE ENVIRONMENT LOCK: PASS")
    print("Environment lock:", output)
    print("Environment lock SHA-256:", sha256_file(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
