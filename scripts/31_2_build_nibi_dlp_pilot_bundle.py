#!/usr/bin/env python3
"""Build the self-contained Nibi pilot ZIP from frozen local inputs."""
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
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/tr38901_nibi_dlp_pilot_prep.json"
    )
    args = parser.parse_args()
    cfg_path = ROOT / args.config
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    work = ROOT / cfg["outputs"]["work_dir"]
    upload = ROOT / cfg["outputs"]["upload_dir"]
    template = ROOT / "nibi/dlp_rzf_pilot_v1"
    upload.mkdir(parents=True, exist_ok=True)
    staging = work / "nibi_bundle_staging"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(template, staging)

    required_inputs = {
        "bs_sites.csv": ROOT / cfg["inputs"]["bs_sites"],
        "bs_sectors.csv": ROOT / cfg["inputs"]["bs_sectors"],
        "sector_static_reference_accounting.csv": ROOT / cfg["inputs"]["sector_static"],
        "earth_station_site_gain_timeseries.csv.gz": ROOT / cfg["inputs"]["earth_station_gain"],
        "TR38901_USED_SUBSET_MAPPING_DECISION.json": work / "TR38901_USED_SUBSET_MAPPING_DECISION.json",
        "TR38901_V19_4_USED_SUBSET_MAPPING.csv": work / "TR38901_V19_4_USED_SUBSET_MAPPING.csv",
        "SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json": work / "SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json",
        "SIONNA_8X8_DUAL_PORT_ORDER.csv": work / "SIONNA_8X8_DUAL_PORT_ORDER.csv",
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
        "status": "READY_FOR_NIBI_ONE_SEED_GPU_PILOT_REVIEW",
        "claim_boundary": cfg["claim_boundary"]["nibi_bundle"],
        "source_commit_required": cfg["expected"]["required_ancestor_commit"],
        "dimensions": {
            "sites": cfg["expected"]["site_count"],
            "sectors": cfg["expected"]["sector_count"],
            "users": cfg["expected"]["user_count"],
            "users_per_sector": cfg["expected"]["users_per_sector"],
            "ports_per_bs": cfg["expected"]["array_port_count"],
        },
        "input_sha256": hashes,
        "next_gate": cfg["next_gate"],
    }
    (staging / "BUNDLE_METADATA.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest_path = staging / "BUNDLE_MANIFEST.sha256"
    lines = []
    for path in sorted(staging.rglob("*")):
        if path.is_file() and path != manifest_path:
            lines.append(
                f"{sha256_file(path)}  {path.relative_to(staging).as_posix()}"
            )
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    output_zip = upload / "FR3_DLP_RZF_NIBI_ONE_SEED_GPU_PILOT_v1.zip"
    if output_zip.exists():
        output_zip.unlink()
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
        if bad is not None:
            raise RuntimeError(f"Corrupt ZIP member: {bad}")
    (work / "NIBI_BUNDLE_METADATA.json").write_text(
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
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest_path, work / "NIBI_BUNDLE_CONTENTS.sha256")
    print("NIBI DLP-RZF PILOT BUNDLE BUILD: PASS")
    print("ZIP:", output_zip)
    print("SHA-256:", sha256_file(output_zip))
    print("Members:", len(lines) + 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
