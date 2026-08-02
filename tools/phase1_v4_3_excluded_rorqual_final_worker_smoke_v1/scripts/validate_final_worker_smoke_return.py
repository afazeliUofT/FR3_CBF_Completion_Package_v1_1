#!/usr/bin/env python3
"""Validate a compact excluded final-worker smoke return on WSL."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
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
    args = parser.parse_args()
    archive = Path(args.return_zip).expanduser().resolve()
    sidecar = Path(str(archive) + ".sha256")
    if not sidecar.is_file():
        raise FileNotFoundError(sidecar)
    parts = sidecar.read_text(encoding="utf-8").split()
    if len(parts) != 2 or parts[1] != archive.name:
        raise ValueError("return sidecar is not basename-only")
    if parts[0] != sha256_file(archive):
        raise ValueError("return ZIP SHA-256 mismatch")
    with zipfile.ZipFile(archive) as bundle:
        bad = bundle.testzip()
        if bad is not None:
            raise RuntimeError(f"return ZIP CRC failure: {bad}")
        roots = sorted({Path(name).parts[0] for name in bundle.namelist() if name})
        if len(roots) != 1:
            raise ValueError(f"return ZIP must have one root: {roots}")
        with tempfile.TemporaryDirectory(prefix="fr3-final-worker-return-") as temp_name:
            temp = Path(temp_name)
            bundle.extractall(temp)
            root = temp / roots[0]
            manifest_count = verify_manifest(root, root / "RETURN_MANIFEST.sha256")
            metadata = json.loads(
                (root / "RETURN_METADATA.json").read_text(encoding="utf-8")
            )
            if metadata["campaign_seed"] != 43999:
                raise ValueError("return seed is not 43999")
            if metadata["confirmatory_analysis_included"] is not False:
                raise ValueError("excluded smoke entered confirmatory analysis")
            if metadata["full_campaign_execution_authorized"] is not False:
                raise ValueError("return authorizes full campaign")
            if metadata["authorization_token_included"] is not False:
                raise ValueError("return contains authorization token")
            if metadata["raw_frequency_response_included"] is not False:
                raise ValueError("return contains raw channel")
            if any(
                path.name == "frequency_response.npy"
                or "AUTHORIZATION.json" in path.name
                or path.suffix in {".pyc", ".pyo"}
                or "__pycache__" in path.parts
                for path in root.rglob("*")
                if path.is_file()
            ):
                raise ValueError("return contains a forbidden file")

            audit_path = root / "provenance/FINAL_WORKER_SMOKE_AUDIT.json"
            audit = (
                json.loads(audit_path.read_text(encoding="utf-8"))
                if audit_path.is_file()
                else None
            )
            success = metadata["status"] == (
                "PASS_EXCLUDED_RORQUAL_FINAL_WORKER_SMOKE_RETURN_READY"
            )
            if success:
                if audit is None:
                    raise FileNotFoundError(audit_path)
                if audit["status"] != (
                    "PASS_EXCLUDED_RORQUAL_FINAL_CAMPAIGN_WORKER_SMOKE_SEED43999"
                ):
                    raise ValueError("pass return has a non-pass scientific audit")
                if metadata["slurm_state"] != "COMPLETED":
                    raise ValueError("pass return has non-completed Slurm state")
                for key in (
                    "worker_exit_code",
                    "structural_validator_exit_code",
                    "scientific_pass_validator_exit_code",
                    "independent_audit_exit_code",
                ):
                    if int(metadata[key]) != 0:
                        raise ValueError(f"pass return has nonzero {key}")

    print("LOCAL_FINAL_WORKER_SMOKE_RETURN_VALIDATION=PASS")
    print(f"RETURN_MANIFEST_ENTRIES={manifest_count}")
    print(f"RETURN_STATUS={metadata['status']}")
    print(f"SLURM_STATE={metadata['slurm_state']}")
    print(f"SCIENTIFIC_STATUS={metadata['scientific_smoke_status']}")
    print("FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO")
    return 0 if success else 20


if __name__ == "__main__":
    raise SystemExit(main())
