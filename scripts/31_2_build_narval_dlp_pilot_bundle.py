#!/usr/bin/env python3
"""Build the self-contained Narval A100 pilot ZIP from frozen local inputs."""
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/tr38901_narval_dlp_pilot_prep.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["outputs"]["work_dir"]
    upload = ROOT / cfg["outputs"]["upload_dir"]
    template = ROOT / "narval/dlp_rzf_pilot_v1"
    upload.mkdir(parents=True, exist_ok=True)
    staging = work / "narval_bundle_staging"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(template, staging)

    old_work = ROOT / "data/real/tr38901_nibi_dlp_pilot_prep"
    required_inputs = {
        "bs_sites.csv": ROOT / cfg["inputs"]["bs_sites"],
        "bs_sectors.csv": ROOT / cfg["inputs"]["bs_sectors"],
        "sector_static_reference_accounting.csv": ROOT / cfg["inputs"]["sector_static"],
        "earth_station_site_gain_timeseries.csv.gz": ROOT / cfg["inputs"]["earth_station_gain"],
        "TR38901_USED_SUBSET_MAPPING_DECISION.json":
            old_work / "TR38901_USED_SUBSET_MAPPING_DECISION.json",
        "TR38901_V19_4_USED_SUBSET_MAPPING.csv":
            old_work / "TR38901_V19_4_USED_SUBSET_MAPPING.csv",
        "SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json":
            work / "SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json",
        "SIONNA_8X8_DUAL_PORT_ORDER.csv":
            work / "SIONNA_8X8_DUAL_PORT_ORDER.csv",
        "SIONNA_INCUMBENT_LOCAL_FRAME.csv":
            work / "SIONNA_INCUMBENT_LOCAL_FRAME.csv",
        "SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT.json":
            work / "SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT.json",
    }
    input_dir = staging / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, source in required_inputs.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        target = input_dir / name
        shutil.copy2(source, target)
        hashes[f"input/{name}"] = sha256_file(target)

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "READY_FOR_NARVAL_A100_ONE_SEED_GPU_PILOT",
        "claim_boundary": cfg["claim_boundary"]["narval_bundle"],
        "source_commit_required": cfg["expected"]["required_ancestor_commit"],
        "cluster": "narval",
        "gpu": "A100-40GB",
        "dimensions": {
            "sites": cfg["expected"]["site_count"],
            "sectors": cfg["expected"]["sector_count"],
            "users": cfg["expected"]["user_count"],
            "users_per_sector": cfg["expected"]["users_per_sector"],
            "ports_per_bs": cfg["expected"]["array_port_count"],
        },
        "channel_generation": {
            "user_chunk_size": cfg["pilot"]["channel_user_chunk_size"],
            "reason": "fit one Narval A100 40GB",
            "cross_chunk_spatial_consistency_claimed": False,
        },
        "input_sha256": hashes,
        "steering_frame_status":
            "PASS_EXACT_SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT",
        "superseded_nibi_bundle": cfg["superseded_nibi_bundle"],
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

    for path in upload.glob("FR3_DLP_RZF_NARVAL_ONE_SEED_GPU_PILOT_*.zip*"):
        path.unlink()
    output_zip = upload / "FR3_DLP_RZF_NARVAL_ONE_SEED_GPU_PILOT_v1.zip"
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging).as_posix())
    checksum = upload / f"{output_zip.name}.sha256"
    checksum.write_text(
        f"{sha256_file(output_zip)}  {output_zip.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    with zipfile.ZipFile(output_zip) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Corrupt ZIP member: {bad}")

    (work / "NARVAL_BUNDLE_METADATA.json").write_text(
        json.dumps(
            {
                **metadata,
                "zip_path": str(output_zip.relative_to(ROOT)),
                "zip_sha256": sha256_file(output_zip),
                "zip_bytes": output_zip.stat().st_size,
                "manifest_entries": len(lines),
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest, work / "NARVAL_BUNDLE_CONTENTS.sha256")
    print("NARVAL DLP-RZF PILOT BUNDLE BUILD: PASS")
    print("ZIP:", output_zip)
    print("SHA-256:", sha256_file(output_zip))
    print("Members:", len(lines) + 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
