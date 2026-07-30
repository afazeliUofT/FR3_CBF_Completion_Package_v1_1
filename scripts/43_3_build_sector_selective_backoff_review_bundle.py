#!/usr/bin/env python3
"""Build the declared-envelope sector-selective fallback review bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

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
        "--config",
        default="config/sector_selective_backoff_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    results = ROOT / cfg["paths"]["results_dir"]
    output = ROOT / cfg["paths"]["review_bundle"]
    output.parent.mkdir(parents=True, exist_ok=True)

    files = [
        path
        for base in [evidence, results]
        for path in sorted(base.rglob("*"))
        if path.is_file()
        and path != output
        and not path.name.endswith(".zip.sha256")
    ]
    for path in [
        ROOT / "config/sector_selective_backoff_v1.json",
        ROOT / "config/sector_selective_backoff_state_v1.json",
        ROOT / "config/phased_campaign_spec_v3.json",
        ROOT / "src/fr3_cbf/null_floor_aware_sector_backoff.py",
        ROOT / "scripts/43_0_run_sector_selective_backoff.py",
        ROOT / "scripts/43_1_validate_sector_selective_backoff.py",
        ROOT / "docs/SECTOR_SELECTIVE_BACKOFF_CERTIFICATE.md",
        ROOT / "docs/DECLARED_ARRAY_CSI_ENGINEERING_ENVELOPE_V1.md",
        ROOT / "PROJECT_STATUS.md",
        ROOT / "NEXT_IMMEDIATE_STEP.md",
    ]:
        if not path.is_file():
            raise FileNotFoundError(path)
        files.append(path)

    if output.exists():
        output.unlink()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(set(files)):
            archive.write(
                path,
                path.relative_to(ROOT).as_posix(),
            )
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"corrupt review member: {bad}")

    checksum = Path(str(output) + ".sha256")
    checksum.write_text(
        f"{sha256_file(output)}  {output.name}\n",
        encoding="utf-8",
    )
    print("SECTOR-SELECTIVE BACKOFF REVIEW BUNDLE: PASS")
    print("Review bundle:", output)
    print("Review bundle SHA-256:", sha256_file(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
