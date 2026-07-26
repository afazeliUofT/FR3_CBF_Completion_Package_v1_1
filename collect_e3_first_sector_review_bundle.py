#!/usr/bin/env python3
"""Collect the exact local files needed to audit/build the first E3 sector P.452 stage.

Run from the FR3_CBF_Completion_Package_v1_1 repository root:

    python3 collect_e3_first_sector_review_bundle.py

The script is fail-closed: it refuses to create a partial bundle when any required
file is missing. It preserves repository-relative paths, writes an internal
SHA-256 manifest, and creates an external ZIP checksum file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REQUIRED_FILES = [
    # First-sector selection and reviewed terrain.
    "data/real/e3_first_sector_audit/selected_sector.json",
    "data/real/e3_first_sector_audit/sector_candidates.csv",
    "data/real/e3_first_sector_audit/first_sector_link_input.csv",
    "data/real/e3_first_sector_audit/first_sector_link_with_terrain.csv",
    "data/real/e3_first_sector_audit/FIRST_SECTOR_TERRAIN_DECISION.json",
    "data/real/e3_first_sector_audit/FIRST_SECTOR_TERRAIN_DECISION.md",
    "data/real/e3_first_sector_audit/FIRST_SECTOR_TERRAIN_EVIDENCE.sha256",
    "data/real/e3_first_sector_audit/terrain_review/terrain_profile_samples.csv.gz",
    "data/real/e3_first_sector_audit/terrain_review/terrain_summary.csv",
    "data/real/e3_first_sector_audit/terrain_review/TERRAIN_AUDIT.json",
    "data/real/e3_first_sector_audit/terrain_review/first_sector_profile_review.pdf",
    # Frozen E3 station, cellular layout, pattern, and pass.
    "data/real/earth_station.csv",
    "data/real/bs_sites.csv",
    "data/real/bs_sectors.csv",
    "data/real/E3_PATTERN_LAYOUT_DECISION.json",
    "data/real/e3_pattern_layout_review/earth_station_pattern_parameters.csv",
    "data/real/e3_pattern_layout_review/earth_station_pattern_samples.csv",
    "data/real/e3_pattern_layout_review/selected_pass_off_axis_summary.csv",
    "data/real/e3_reference_case/e3_track_selected_pass_1s.csv",
    "data/real/e3_reference_case/E3_PASS_SELECTION.json",
    # Orbit and provenance.
    "data/external/tle/active_case.tle",
    "data/external/tle/TLE_SOURCE_RECORD.json",
    "data/external/mrdem_e3_layout/MRDEM_SOURCE_RECORD.json",
    "data/external/itu/SA509_SOURCE_RECORD.json",
    # Validated P.452 implementation provenance (not the copyrighted/full source tree).
    "data/external/p452/reference_v18_commit.txt",
    "data/external/p452/p452_source_sha256.txt",
    "results/p452_reference_validation/P452_REFERENCE_PROVENANCE_R2026a.txt",
    # Active configurations and relevant runner/validator source.
    "config/e3_pattern_layout.yaml",
    "config/current_audited_state.yaml",
    "config/regulatory_constants.yaml",
    "scripts/20_validate_p452_export.py",
    "matlab/run_p452_pilot.m",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root (default: current directory)",
    )
    parser.add_argument(
        "--output",
        default="E3_FIRST_SECTOR_REVIEW_BUNDLE_2026-07-26.zip",
        help="Output ZIP path, relative to repository root unless absolute",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not (root / "PROJECT_STATUS.md").is_file():
        raise SystemExit(
            f"ERROR: {root} does not look like the repository root "
            "(PROJECT_STATUS.md is missing)."
        )

    missing = [rel for rel in REQUIRED_FILES if not (root / rel).is_file()]
    if missing:
        print("BUNDLE CREATION REFUSED: required files are missing:")
        for rel in missing:
            print(f"  MISSING  {rel}")
        return 2

    # Sanity-check the current scientific gate before packaging.
    terrain_decision_path = root / "data/real/e3_first_sector_audit/FIRST_SECTOR_TERRAIN_DECISION.json"
    terrain_decision = json.loads(terrain_decision_path.read_text(encoding="utf-8"))
    if terrain_decision.get("status") != "ACCEPTED_FOR_FIRST_SECTOR_P452_PIPELINE_AUDIT":
        raise SystemExit("ERROR: first-sector terrain decision is not in the accepted audit state.")
    if terrain_decision.get("next_gate") != "FIRST_SECTOR_P452_BASIC_LOSS_AND_GAIN_ACCOUNTING":
        raise SystemExit("ERROR: unexpected next gate in the terrain decision.")

    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    manifest_lines: list[str] = []
    file_records: list[dict[str, object]] = []

    for rel in REQUIRED_FILES:
        path = root / rel
        digest = sha256_file(path)
        size = path.stat().st_size
        manifest_lines.append(f"{digest}  {rel}")
        file_records.append({"path": rel, "sha256": digest, "size_bytes": size})

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Inputs required to review and build the first cellular-sector-to-"
            "EESS-earth-station P.452 basic-loss and gain-accounting stage."
        ),
        "claim_boundary": "Input/review bundle only; contains no paper result.",
        "sector_id": terrain_decision.get("sector_id"),
        "site_id": terrain_decision.get("site_id"),
        "next_gate": terrain_decision.get("next_gate"),
        "file_count": len(file_records),
        "files": file_records,
    }

    with ZipFile(output, "w", compression=ZIP_DEFLATED, allowZip64=True) as archive:
        for rel in REQUIRED_FILES:
            archive.write(root / rel, arcname=rel)
        archive.writestr(
            "BUNDLE_MANIFEST.sha256",
            "\n".join(manifest_lines) + "\n",
        )
        archive.writestr(
            "BUNDLE_METADATA.json",
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        )

    zip_digest = sha256_file(output)
    checksum_path = Path(str(output) + ".sha256")
    checksum_path.write_text(
        f"{zip_digest}  {output.name}\n",
        encoding="utf-8",
        newline="\n",
    )

    # Verify that every intended member and the two internal records are present.
    expected_members = set(REQUIRED_FILES) | {
        "BUNDLE_MANIFEST.sha256",
        "BUNDLE_METADATA.json",
    }
    with ZipFile(output) as archive:
        actual_members = set(archive.namelist())
        bad = archive.testzip()
    if bad is not None:
        raise SystemExit(f"ERROR: ZIP CRC check failed at member: {bad}")
    if actual_members != expected_members:
        missing_members = sorted(expected_members - actual_members)
        extra_members = sorted(actual_members - expected_members)
        raise SystemExit(
            "ERROR: ZIP membership mismatch: "
            f"missing={missing_members}, extra={extra_members}"
        )

    print("E3 FIRST-SECTOR REVIEW BUNDLE: PASS")
    print(f"Files: {len(REQUIRED_FILES)}")
    print(f"Sector: {terrain_decision.get('sector_id')}")
    print(f"Output: {output}")
    print(f"ZIP SHA-256: {zip_digest}")
    print(f"Checksum file: {checksum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
