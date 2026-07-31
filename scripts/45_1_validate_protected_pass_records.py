#!/usr/bin/env python3
"""Strict validation of all five protected-pass records."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(root: Path, manifest: Path) -> None:
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"manifest mismatch: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/protected_pass_records_phase1_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    records = ROOT / cfg["paths"]["pass_records_dir"]
    index = json.loads(
        (records / "PASS_RECORD_INDEX.json").read_text(encoding="utf-8")
    )
    assert index["status"] == (
        "PASS_FIVE_IMMUTABLE_PROTECTED_PASS_RECORDS_READY_FOR_REVIEW"
    )
    assert index["campaign_execution_authorized"] is False
    assert len(index["pass_slots"]) == 5
    assert [row["slot"] for row in index["pass_slots"]] == list(range(5))

    peak_dates = []
    for row in index["pass_slots"]:
        slot = int(row["slot"])
        directory = records / f"slot_{slot}"
        verify_manifest(directory, directory / "RECORD_MANIFEST.sha256")
        archive = records / row["record_zip"]
        assert archive.is_file()
        assert sha256_file(archive) == row["record_zip_sha256"]
        with zipfile.ZipFile(archive) as bundle:
            assert bundle.testzip() is None

        metadata = json.loads(
            (directory / "PASS_RECORD_METADATA.json").read_text(
                encoding="utf-8"
            )
        )
        assert metadata["slot"] == slot
        assert (
            metadata["tle"]["sha256"]
            == metadata["tle"]["recorded_sha256"]
        )
        assert (
            metadata["tle"]["age_days_at_peak"]
            <= metadata["tle"]["maximum_age_days"]
        )
        protected = pd.read_csv(directory / "protected_track_1s.csv")
        assert len(protected) == row["protected_sample_count"]
        assert len(protected) >= 300
        assert protected["elevation_deg"].min() >= (
            cfg["selection_policy"]["minimum_elevation_deg"] - 1e-12
        )
        peak_dates.append(row["selection"]["target_peak_date"])

        shapes = []
        for criterion in ["long", "short"]:
            for pattern in ["multiple", "single"]:
                value = np.load(
                    directory / f"kappa_{criterion}_{pattern}.npy",
                    allow_pickle=False,
                )
                assert value.shape == (len(protected), 57)
                assert np.all(np.isfinite(value))
                assert np.all(value > 0.0)
                shapes.append(value.shape)
            multiple = np.load(
                directory / f"kappa_{criterion}_multiple.npy",
                allow_pickle=False,
            )
            single = np.load(
                directory / f"kappa_{criterion}_single.npy",
                allow_pickle=False,
            )
            ratio_db = 10.0 * np.log10(single / multiple)
            assert np.allclose(ratio_db, 3.0, rtol=0.0, atol=1e-10)
        assert len(set(shapes)) == 1

    assert len(set(peak_dates)) == 5
    slot0 = json.loads(
        (
            records / "slot_0/PASS_RECORD_METADATA.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        slot0["slot0_historical_kappa_max_relative_error"]
        <= 2e-12
    )
    print("PROTECTED-PASS RECORD STRICT VALIDATION: PASS")
    print(
        json.dumps(
            {
                "status": index["status"],
                "slots": 5,
                "unique_peak_dates": peak_dates,
                "slot0_historical_kappa_max_relative_error": slot0[
                    "slot0_historical_kappa_max_relative_error"
                ],
                "campaign_execution_authorized": False,
                "next_gate": cfg["next_gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
