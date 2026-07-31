#!/usr/bin/env python3
"""Build the independent job-package review-freeze bundle."""
from __future__ import annotations

import hashlib
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
    evidence = ROOT / "evidence/phase1_nibi_job_package_independent_review_v1"
    output = (
        evidence
        / "FR3_PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_v1.zip"
    )
    if output.exists():
        output.unlink()
    checksum = Path(str(output) + ".sha256")
    if checksum.exists():
        checksum.unlink()

    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(evidence.rglob("*")):
            if path.is_file() and path != output and path != checksum:
                archive.write(
                    path,
                    path.relative_to(ROOT).as_posix(),
                )
        for path in [
            ROOT
            / "config/phase1_nibi_job_package_independent_review_v1.json",
            ROOT
            / "docs/PHASE1_NIBI_JOB_PACKAGE_INDEPENDENT_REVIEW_V1.md",
            ROOT
            / "scripts/49_0_verify_freeze_phase1_job_package_review.py",
            ROOT
            / "scripts/49_1_validate_phase1_job_package_independent_review.py",
            ROOT / "PROJECT_STATUS.md",
            ROOT / "NEXT_IMMEDIATE_STEP.md",
        ]:
            archive.write(path, path.relative_to(ROOT).as_posix())

    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"corrupt review-freeze member: {bad}")
    digest = sha256_file(output)
    checksum.write_text(
        f"{digest}  {output.name}\n",
        encoding="utf-8",
    )
    print("PHASE-1 JOB-PACKAGE INDEPENDENT REVIEW BUNDLE: PASS")
    print("Review bundle:", output)
    print("Review bundle SHA-256:", digest)
    print("Full campaign execution authorized: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
