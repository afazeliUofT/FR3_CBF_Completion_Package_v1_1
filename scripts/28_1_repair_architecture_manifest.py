#!/usr/bin/env python3
"""Rebuild the architecture package manifest without caches or bytecode."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import ROOT


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", default="DISTRIBUTED_IA_RZF_ARCHITECTURE_MANIFEST.sha256"
    )
    args = parser.parse_args()

    manifest = ROOT / args.manifest
    source_files = [
        ROOT / "DISTRIBUTED_IA_RZF_ARCHITECTURE_TEST_REPORT.txt",
        ROOT / "README_DISTRIBUTED_IA_RZF_ARCHITECTURE.md",
        ROOT / "RUN_DISTRIBUTED_IA_RZF_ARCHITECTURE_DROPIN.sh",
        ROOT / "config/distributed_ia_rzf_architecture.yaml",
        ROOT / "scripts/27_0_freeze_distributed_ia_rzf_architecture.py",
        ROOT / "scripts/27_1_run_distributed_ia_rzf_prototype.py",
        ROOT / "scripts/27_2_validate_distributed_ia_rzf.py",
        ROOT / "src/fr3_cbf/distributed_precoding.py",
        ROOT / "tests/test_distributed_precoding.py",
        ROOT / "wrappers/distributed_ia_rzf/00_preflight.sh",
        ROOT / "wrappers/distributed_ia_rzf/10_architecture_freeze.sh",
        ROOT / "wrappers/distributed_ia_rzf/20_prototype_validate.sh",
        ROOT / "wrappers/distributed_ia_rzf/30_package_push.sh",
    ]
    missing = [str(path.relative_to(ROOT)) for path in source_files if not path.is_file()]
    if missing:
        raise SystemExit("MISSING MANIFEST SOURCE FILES:\n" + "\n".join(missing))

    old_lines = (
        manifest.read_text(encoding="utf-8").splitlines()
        if manifest.is_file()
        else []
    )
    prohibited_old = [
        line
        for line in old_lines
        if "__pycache__" in line
        or ".pytest_cache" in line
        or line.rstrip().endswith((".pyc", ".pyo"))
    ]

    lines = [
        f"{digest(path)}  {path.relative_to(ROOT).as_posix()}"
        for path in source_files
    ]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    # Remove local cache artifacts, but never enter .venv.
    removed = []
    for root_name in ["src", "scripts", "tests", "wrappers"]:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file() and path.suffix in {".pyc", ".pyo"}:
                path.unlink()
                removed.append(path.relative_to(ROOT).as_posix())
            elif path.is_dir() and path.name in {"__pycache__", ".pytest_cache"}:
                import shutil

                shutil.rmtree(path)
                removed.append(path.relative_to(ROOT).as_posix() + "/")

    record = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "manifest": manifest.relative_to(ROOT).as_posix(),
        "manifest_entries": len(lines),
        "removed_prohibited_old_entries": prohibited_old,
        "removed_local_cache_artifacts": removed,
        "policy": "No bytecode or test cache belongs in source-package manifests.",
    }
    out = ROOT / "data/real/distributed_channel_readiness"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ARCHITECTURE_MANIFEST_REPAIR.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("ARCHITECTURE PACKAGE MANIFEST REPAIR: PASS")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
