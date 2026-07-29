#!/usr/bin/env python3
"""Static fail-closed validation of the prepared full-topology export bundle."""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/full_topology_export_prep.json")
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    upload = ROOT / cfg["paths"]["upload_dir"]
    bundle = upload / "FR3_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_NIBI_v1.zip"
    if not bundle.is_file():
        raise FileNotFoundError(bundle)

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        with zipfile.ZipFile(bundle) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise RuntimeError(f"Corrupt bundle member: {bad}")
            archive.extractall(root)
        required = [
            "BUNDLE_METADATA.json",
            "BUNDLE_MANIFEST.sha256",
            "export_config.json",
            "run_full_topology_export.py",
            "validate_full_topology_export.py",
            "setup_environment.sh",
            "export_worker.sh",
            "RUN_NIBI_FULL_TOPOLOGY_EXPORT.sh",
            "input/reference_job_18658301/PILOT_TIME_SUMMARY.csv",
        ]
        for relative in required:
            if not (root / relative).is_file():
                raise FileNotFoundError(relative)

        for path in root.rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in root.rglob("*.sh"):
            result = subprocess.run(
                ["bash", "-n", str(path)],
                capture_output=True,
                text=True,
            )
            if result.returncode:
                raise RuntimeError(f"Bash syntax failed: {path}\n{result.stderr}")

        source = (root / "run_full_topology_export.py").read_text(encoding="utf-8")
        required_tokens = [
            "one_topology_call_all_228_users",
            "model.set_topology(*topology_tensors)",
            "frequency_response.npy",
            "protected_amp_perpendicular.npy",
            "protected_steering_pol1.npy",
            "FULL_VS_CHUNKED_COMPARISON.json",
            "legacy_numeric_reproduction",
            "Differences combine topology-generation mode",
        ]
        for token in required_tokens:
            if token not in source:
                raise RuntimeError(f"Required source token is missing: {token}")
        forbidden_tokens = [
            "for start_user in range(0, cfg[\"user_count\"]",
            "hidden_fallback_to_sector_chunks",
        ]
        for token in forbidden_tokens:
            if token in source:
                raise RuntimeError(f"Forbidden full-topology source token: {token}")

        metadata = json.loads((root / "BUNDLE_METADATA.json").read_text(encoding="utf-8"))
        if metadata["target"]["users_in_one_topology_call"] != 228:
            raise RuntimeError("Bundle metadata does not require all 228 users")

    print("FULL-TOPOLOGY EXPORT BUNDLE STATIC VALIDATION: PASS")
    print("Bundle:", bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
