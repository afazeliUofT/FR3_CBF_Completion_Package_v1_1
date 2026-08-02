#!/usr/bin/env python3
"""Strict structural validation of a complete v4.3 merged campaign result."""
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
    parser.add_argument("--require-go-condition", action="store_true")
    args = parser.parse_args()
    root = Path(args.merged_dir).expanduser().resolve()
    audit = json.loads((root / "PHASE1_MERGED_AUDIT.json").read_text(encoding="utf-8"))
    cells = pd.read_csv(root / "PHASE1_ALL_CELL_SUMMARY.csv")
    paired = pd.read_csv(root / "PHASE1_PRIMARY_PAIRED_EFFECTS.csv")
    seeds = pd.read_csv(root / "PHASE1_SEED_CLUSTER_EFFECTS.csv")
    hashes = pd.read_csv(root / "PHASE1_SEED_RESULT_HASH_INDEX.csv")
    endpoints = pd.read_csv(root / "PHASE1_METHOD_ENDPOINT_SUMMARY.csv")
    if len(endpoints) != 9 or endpoints["method_id"].nunique() != 9:
        raise ValueError("method endpoint summary must contain nine methods")
    if (len(cells), len(paired), len(seeds), len(hashes)) != (1350, 150, 30, 30):
        raise ValueError("merged dimensions are not 1350/150/30/30")
    if cells["method_id"].nunique() != 9 or cells["pass_slot"].nunique() != 5:
        raise ValueError("merged method/pass design mismatch")
    required_hash_columns = {
        "campaign_seed",
        "seed_result_sha256",
        "result_manifest_sha256",
        "channel_record_file_sha256",
        "channel_record_canonical_json_sha256",
        "frequency_response_array_sha256",
        "authorization_token_sha256",
        "return_zip_sha256",
    }
    if not required_hash_columns.issubset(hashes.columns):
        raise ValueError("seed-result hash index schema is incomplete")
    for column in required_hash_columns - {"campaign_seed"}:
        if not hashes[column].astype(str).str.fullmatch(r"[0-9a-f]{64}").all():
            raise ValueError(f"invalid SHA-256 values in {column}")
    if "return_zip_present" not in hashes.columns or not hashes[
        "return_zip_present"
    ].astype(bool).all():
        raise ValueError("one or more seed return ZIPs are missing")
    from validator_contract import validate_cell_summary_numeric_domains
    domain_audit = validate_cell_summary_numeric_domains(cells)
    print("MERGED_CELL_SUMMARY_NUMERIC_DOMAIN_GATE=PASS")
    print(
        "MERGED_CELL_SUMMARY_INTENTIONAL_CANDIDATE_ONLY_NA_COUNT="
        + str(domain_audit["intentional_candidate_only_na_count"])
    )
    if audit["seed_count"] != 30 or audit["fixed_pass_count"] != 5:
        raise ValueError("merged audit seed/pass dimensions are wrong")
    if audit["method_count"] != 9 or audit["cell_count"] != 1350:
        raise ValueError("merged audit method/cell dimensions are wrong")
    if audit["primary_bootstrap"]["bootstrap_resamples"] != 10000:
        raise ValueError("bootstrap resample count is wrong")
    if args.require_go_condition and not audit["go_condition_met"]:
        raise ValueError("preregistered campaign go condition was not met")

    manifest = json.loads((root / "MERGED_FILE_MANIFEST.json").read_text(encoding="utf-8"))
    for name, record in manifest.items():
        path = root / name
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"merged manifest mismatch: {name}")
    review = root / "FR3_PHASE1_MERGED_REVIEW_RETURN.zip"
    sidecar = Path(str(review) + ".sha256")
    parts = sidecar.read_text(encoding="utf-8").split()
    if len(parts) != 2 or parts[1] != review.name or parts[0] != sha256_file(review):
        raise ValueError("merged review sidecar mismatch")
    with zipfile.ZipFile(review) as archive:
        if archive.testzip() is not None:
            raise ValueError("merged review ZIP CRC failure")

    print("PHASE1_V4_3_MERGED_RESULT_STRUCTURAL_VALIDATION=PASS")
    print(f"PHASE1_V4_3_MERGED_STATUS={audit['status']}")
    print(f"CANDIDATE_HARD_GATES={'PASS' if audit['all_hard_gates_pass'] else 'FAIL'}")
    print(f"GO_CONDITION_MET={'YES' if audit['go_condition_met'] else 'NO'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
