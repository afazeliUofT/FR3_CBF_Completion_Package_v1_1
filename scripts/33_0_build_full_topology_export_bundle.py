#!/usr/bin/env python3
"""Build the reviewable Nibi full-topology export bundle from immutable evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

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
            raise ValueError(f"Manifest verification failed: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-zip", required=True)
    parser.add_argument("--config", default="config/full_topology_export_prep.json")
    args = parser.parse_args()

    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    review_zip = Path(args.review_zip).expanduser().resolve()
    if not review_zip.is_file():
        raise FileNotFoundError(review_zip)
    if sha256_file(review_zip) != expected["review_zip_sha256"]:
        raise ValueError("Review ZIP SHA-256 mismatch")

    work = ROOT / cfg["paths"]["work_dir"]
    upload = ROOT / cfg["paths"]["upload_dir"]
    template = ROOT / "nibi/controller_ready_full_topology_export_v1"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    upload.mkdir(parents=True, exist_ok=True)

    review_root = work / "review"
    with zipfile.ZipFile(review_zip) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"Corrupt review member: {bad}")
        archive.extractall(review_root)
    verify_manifest(review_root, review_root / "REVIEW_MANIFEST.sha256")

    input_zip = next((review_root / "input_bundle").glob("*.zip"))
    return_zip = next((review_root / "return_bundle").glob("FR3_DLP_RZF_NIBI_PILOT_RETURN_*.zip"))
    if sha256_file(input_zip) != expected["executed_input_bundle_sha256"]:
        raise ValueError("Executed input bundle hash mismatch")
    if sha256_file(return_zip) != expected["return_bundle_sha256"]:
        raise ValueError("Return bundle hash mismatch")

    input_root = work / "executed_input"
    with zipfile.ZipFile(input_zip) as archive:
        archive.extractall(input_root)
    verify_manifest(input_root, input_root / "BUNDLE_MANIFEST.sha256")

    staging = work / "bundle_staging"
    shutil.copytree(template, staging)
    staging_input = staging / "input"
    staging_input.mkdir(parents=True, exist_ok=True)

    required_inputs = [
        "SIONNA_8X8_DUAL_PORT_ORDER.csv",
        "SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json",
        "SIONNA_INCUMBENT_LOCAL_FRAME.csv",
        "SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT.json",
        "TR38901_USED_SUBSET_MAPPING_DECISION.json",
        "TR38901_V19_4_USED_SUBSET_MAPPING.csv",
        "bs_sectors.csv",
        "bs_sites.csv",
        "earth_station_site_gain_timeseries.csv.gz",
        "sector_static_reference_accounting.csv",
    ]
    input_hashes = {}
    for name in required_inputs:
        source = input_root / "input" / name
        if not source.is_file():
            raise FileNotFoundError(source)
        target = staging_input / name
        shutil.copy2(source, target)
        input_hashes[f"input/{name}"] = sha256_file(target)

    reference = staging_input / "reference_job_18658301"
    reference.mkdir()
    reference_source = review_root / "return_extracted" / "output"
    for name in [
        "NIBI_ONE_SEED_DLP_RZF_PILOT_AUDIT.json",
        "PILOT_NUMERICAL_EVIDENCE.npz",
        "PILOT_SECTOR_TIME_METRICS.csv.gz",
        "PILOT_TIME_SUMMARY.csv",
        "PILOT_USER_RATE_SUMMARY.csv",
    ]:
        source = reference_source / name
        if not source.is_file():
            raise FileNotFoundError(source)
        target = reference / name
        shutil.copy2(source, target)
        input_hashes[f"input/reference_job_18658301/{name}"] = sha256_file(target)

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "READY_FOR_INDEPENDENT_SOURCE_REVIEW",
        "claim_boundary": cfg["claim_boundary"],
        "source_commit_required": expected["required_ancestor_commit"],
        "review_zip_sha256": expected["review_zip_sha256"],
        "executed_input_bundle_sha256": expected["executed_input_bundle_sha256"],
        "return_bundle_sha256": expected["return_bundle_sha256"],
        "reference_job_id": expected["reference_job_id"],
        "target": {
            "cluster": "nibi",
            "gpu": "H100-80GB",
            "users_in_one_topology_call": 228,
        },
        "input_sha256": input_hashes,
        "next_gate": cfg["next_gate"],
    }
    (staging / "BUNDLE_METADATA.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest = staging / "BUNDLE_MANIFEST.sha256"
    lines = []
    for path in sorted(staging.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  {path.relative_to(staging).as_posix()}"
            )
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    output = upload / "FR3_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_NIBI_v1.zip"
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging).as_posix())
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"Corrupt output member: {bad}")

    checksum = Path(str(output) + ".sha256")
    checksum.write_text(
        f"{sha256_file(output)}  {output.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    result = {
        **metadata,
        "bundle_path": str(output.relative_to(ROOT)),
        "bundle_sha256": sha256_file(output),
        "bundle_bytes": output.stat().st_size,
        "manifest_entries": len(lines),
    }
    (work / "FULL_TOPOLOGY_EXPORT_PREP_METADATA.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest, work / "FULL_TOPOLOGY_EXPORT_BUNDLE_MANIFEST.sha256")
    print("FULL-TOPOLOGY EXPORT BUNDLE BUILD: PASS")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
