#!/usr/bin/env python3
"""Strict validation of the merged phase-1 result."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-dir", required=True)
    args = parser.parse_args()
    root = Path(args.merged_dir).expanduser().resolve()
    audit = json.loads(
        (root / "PHASE1_MERGED_AUDIT.json").read_text(encoding="utf-8")
    )
    cells = pd.read_csv(root / "PHASE1_ALL_CELL_SUMMARY.csv")
    primary = pd.read_csv(root / "PHASE1_PRIMARY_PAIRED_EFFECTS.csv")
    seeds = pd.read_csv(root / "PHASE1_SEED_CLUSTER_EFFECTS.csv")
    if len(cells) != 1200 or len(primary) != 150 or len(seeds) != 30:
        raise ValueError("merged result dimensions are wrong")
    if not np.isfinite(cells.select_dtypes(include=[np.number])).all().all():
        raise ValueError("merged cells contain non-finite values")
    if audit["seed_count"] != 30 or audit["fixed_pass_count"] != 5:
        raise ValueError("merged audit design dimensions are wrong")
    if audit["cell_count"] != 1200:
        raise ValueError("merged audit cell count is wrong")
    if audit["bootstrap"]["bootstrap_resamples"] != 10000:
        raise ValueError("bootstrap resample count is wrong")
    if not audit["all_hard_gates_pass"]:
        raise ValueError("merged predictive hard gates failed")

    manifest = json.loads(
        (root / "MERGED_FILE_MANIFEST.json").read_text(encoding="utf-8")
    )
    for name, record in manifest.items():
        path = root / name
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"merged file manifest mismatch: {name}")

    review = root / "FR3_PHASE1_MERGED_REVIEW_RETURN.zip"
    checksum = Path(str(review) + ".sha256")
    if checksum.read_text(encoding="utf-8").split()[0] != sha256_file(review):
        raise ValueError("merged review ZIP checksum mismatch")
    with zipfile.ZipFile(review) as archive:
        if archive.testzip() is not None:
            raise ValueError("merged review ZIP is corrupt")

    print("PHASE-1 MERGED RESULT STRICT VALIDATION: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
