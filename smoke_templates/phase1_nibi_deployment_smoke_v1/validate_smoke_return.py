#!/usr/bin/env python3
"""Validate the compact return or diagnostic bundle on local WSL."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(root: Path, manifest: Path) -> int:
    count = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split("  ", 1)
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != expected:
            raise ValueError(f"return manifest mismatch: {relative}")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--return-zip", required=True)
    parser.add_argument("--smoke-tools-root", required=True)
    args = parser.parse_args()
    return_zip = Path(args.return_zip).expanduser().resolve()
    tools = Path(args.smoke_tools_root).expanduser().resolve()
    checksum = Path(str(return_zip) + ".sha256")
    if not checksum.is_file():
        raise FileNotFoundError(checksum)
    expected = checksum.read_text(encoding="utf-8").split()[0]
    if sha256_file(return_zip) != expected:
        raise ValueError("local smoke return ZIP checksum mismatch")
    with zipfile.ZipFile(return_zip) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"corrupt return member: {bad}")

    with tempfile.TemporaryDirectory(prefix="fr3_nibi_smoke_return_") as temp:
        root = Path(temp)
        with zipfile.ZipFile(return_zip) as archive:
            archive.extractall(root)
        metadata = json.loads(
            (root / "RETURN_METADATA.json").read_text(encoding="utf-8")
        )
        manifest_count = verify_manifest(
            root, root / "RETURN_MANIFEST.sha256"
        )
        if metadata["confirmatory_analysis_included"] is not False:
            raise ValueError("returned smoke entered confirmatory analysis")
        if metadata["full_campaign_execution_authorized"] is not False:
            raise ValueError("returned smoke authorizes full campaign")
        if metadata["raw_frequency_response_returned"] is not False:
            raise ValueError("compact return unexpectedly contains raw channel")

        if metadata["status"] == (
            "PASS_NONCAMPAIGN_NIBI_DEPLOYMENT_SMOKE_RETURN_READY"
        ):
            required = [
                root / "result/NONCAMPAIGN_SMOKE_RESULT.json",
                root / "provenance/ENVIRONMENT_LOCK.json",
                root / "provenance/SMOKE_AUTHORIZATION_TOKEN.json",
                root / "provenance/GPU_RUNTIME.json",
                root / "logs",
            ]
            for path in required:
                if not path.exists():
                    raise FileNotFoundError(path)
            subprocess.run(
                [
                    "python3",
                    str(tools / "validate_noncampaign_smoke.py"),
                    "--result-dir",
                    str(root / "result"),
                    "--smoke-contract",
                    str(root / "smoke/SMOKE_PACKAGE_CONTRACT.json"),
                    "--environment-lock",
                    str(root / "provenance/ENVIRONMENT_LOCK.json"),
                    "--token",
                    str(root / "provenance/SMOKE_AUTHORIZATION_TOKEN.json"),
                ],
                check=True,
            )
            gpu = json.loads(
                (root / "provenance/GPU_RUNTIME.json").read_text(
                    encoding="utf-8"
                )
            )
            if gpu["status"] != "PASS_NIBI_H100_RUNTIME_PROBE":
                raise ValueError("GPU runtime probe did not pass")
            result = json.loads(
                (root / "result/NONCAMPAIGN_SMOKE_RESULT.json")
                .read_text(encoding="utf-8")
            )
            print("LOCAL NONCAMPAIGN NIBI SMOKE RETURN VALIDATION: PASS")
            print(json.dumps(
                {
                    "job_id": metadata["job_id"],
                    "slurm_state": metadata["slurm_state"],
                    "smoke_seed": metadata["smoke_seed"],
                    "return_manifest_entries": manifest_count,
                    "scientific_status": result["status"],
                    "primary_mean_effect": result[
                        "primary_paired_effects"
                    ]["mean_over_five_passes"],
                    "confirmatory_analysis_included": False,
                },
                indent=2,
            ))
            return 0

        print("LOCAL NIBI SMOKE DIAGNOSTIC RETURN: VALID ARCHIVE")
        print(json.dumps(metadata, indent=2))
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
