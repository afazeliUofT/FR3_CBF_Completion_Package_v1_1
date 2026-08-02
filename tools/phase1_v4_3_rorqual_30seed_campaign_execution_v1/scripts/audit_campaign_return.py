#!/usr/bin/env python3
"""Verify a returned full-campaign ZIP and print its scientific gates."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_sidecar(archive: Path) -> None:
    sidecar = Path(str(archive) + ".sha256")
    parts = sidecar.read_text(encoding="utf-8").split()
    if len(parts) != 2 or parts[1] != archive.name:
        raise ValueError("campaign return sidecar is not basename-only")
    if parts[0] != sha256_file(archive):
        raise ValueError("campaign return sidecar hash mismatch")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--return-zip", required=True)
    args = p.parse_args()
    archive = Path(args.return_zip).expanduser().resolve()
    verify_sidecar(archive)
    with zipfile.ZipFile(archive) as z:
        bad = z.testzip()
        if bad is not None:
            raise ValueError(f"campaign return ZIP CRC failure: {bad}")
        roots = {Path(name).parts[0] for name in z.namelist() if name and not name.endswith("/")}
        if len(roots) != 1:
            raise ValueError("campaign return must have one root directory")
        root_name = next(iter(roots))
        with tempfile.TemporaryDirectory(prefix="fr3-campaign-audit-") as temp_name:
            z.extractall(temp_name)
            root = Path(temp_name) / root_name
            manifest = root / "RETURN_MANIFEST.sha256"
            for raw in manifest.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                digest, rel = raw.split(maxsplit=1)
                rel = rel.lstrip(" *")
                path = root / rel
                if not path.is_file() or sha256_file(path) != digest:
                    raise ValueError(f"return manifest mismatch: {rel}")
            metadata = json.loads((root / "CAMPAIGN_RETURN_METADATA.json").read_text(encoding="utf-8"))
            seed_index = json.loads((root / "SEED_COMPLETION_INDEX.json").read_text(encoding="utf-8"))
            if len(seed_index) != 30:
                raise ValueError("seed completion index does not contain 30 seeds")
            nested = sorted((root / "seed_returns").glob("FR3_PHASE1_SEED_*_RETURN.zip"))
            for seed_zip in nested:
                verify_sidecar(seed_zip)
                with zipfile.ZipFile(seed_zip) as seed_archive:
                    bad_seed = seed_archive.testzip()
                    if bad_seed is not None:
                        raise ValueError(f"seed return CRC failure: {seed_zip.name}: {bad_seed}")
            merged_review = root / "merged" / "FR3_PHASE1_MERGED_REVIEW_RETURN.zip"
            if merged_review.is_file():
                verify_sidecar(merged_review)
                with zipfile.ZipFile(merged_review) as merged_archive:
                    if merged_archive.testzip() is not None:
                        raise ValueError("merged review ZIP CRC failure")

    print("CAMPAIGN_RETURN_SHA256_GATE=PASS")
    print("CAMPAIGN_RETURN_ZIP_CRC=PASS")
    print("CAMPAIGN_RETURN_MANIFEST=PASS")
    print(f"CAMPAIGN_RETURN_STATUS={metadata['status']}")
    print(f"CAMPAIGN_SCIENTIFIC_EXIT_CODE={metadata['scientific_exit_code']}")
    print(f"SEED_RETURN_COUNT={metadata['seed_return_count']}")
    print(f"SEED_HARD_GATE_PASS_COUNT={metadata['seed_hard_gate_pass_count']}")
    print(f"MERGED_ALL_HARD_GATES_PASS={metadata['merged_all_hard_gates_pass']}")
    print(f"GO_CONDITION_MET={metadata['go_condition_met']}")
    print(f"PRIMARY_POINT_ESTIMATE={metadata['primary_point_estimate']}")
    print(f"PRIMARY_LOWER_95={metadata['primary_lower_95']}")
    print(f"PRIMARY_UPPER_95={metadata['primary_upper_95']}")
    print("INFORMATION_EXCHANGE_LOCALITY_CERTIFIED=NO")
    print("NEXT_GATE=" + metadata["next_gate"])
    return int(metadata["scientific_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
