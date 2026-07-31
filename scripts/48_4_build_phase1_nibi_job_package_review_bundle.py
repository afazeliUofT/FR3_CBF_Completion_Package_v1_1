#!/usr/bin/env python3
"""Build the independent-review bundle for the immutable Nibi job package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
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
        default="config/phase1_nibi_job_package_builder_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    package = ROOT / cfg["paths"]["job_package_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    evidence.mkdir(parents=True, exist_ok=True)

    package_zip = package / "FR3_PHASE1_NIBI_JOB_PACKAGE_v1.zip"
    for source, target_name in [
        (package_zip, package_zip.name),
        (Path(str(package_zip) + ".sha256"), package_zip.name + ".sha256"),
        (package / "JOB_PACKAGE_CONTRACT.json", "JOB_PACKAGE_CONTRACT.json"),
        (package / "PACKAGE_ID.txt", "PACKAGE_ID.txt"),
        (
            package / "CANDIDATE_AND_REVIEW_BINDING.json",
            "CANDIDATE_AND_REVIEW_BINDING.json",
        ),
        (
            package / "NEW_JOB_SOURCE_RECORD.json",
            "NEW_JOB_SOURCE_RECORD.json",
        ),
        (package / "RESULT_SCHEMA.json", "RESULT_SCHEMA.json"),
    ]:
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, evidence / target_name)

    (evidence / "INDEPENDENT_JOB_PACKAGE_REVIEW_REQUEST.md").write_text(
        "# Independent phase-1 Nibi job-package review request\n\n"
        "Review the immutable non-executable package. Verify candidate/review "
        "bindings, the reactive-myopic same-fallback implementation, one-channel-"
        "per-seed reuse, all eight method definitions, the primary final moving-PF "
        "endpoint, result schemas, 30-seed merge/bootstrap logic, source hashes, "
        "H100/scratch resource templates, and all execution locks. Return PASS or "
        "a precise blocker. Do not authorize or submit Nibi jobs.\n",
        encoding="utf-8",
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    review_name = Path(cfg["paths"]["review_bundle"]).name
    for path in sorted(evidence.rglob("*")):
        if (
            path.is_file()
            and path != manifest
            and path.name not in {review_name, review_name + ".sha256"}
        ):
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(evidence).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    review = ROOT / cfg["paths"]["review_bundle"]
    if review.exists():
        review.unlink()
    with zipfile.ZipFile(
        review, "w", zipfile.ZIP_DEFLATED, allowZip64=True
    ) as archive:
        for path in sorted(evidence.rglob("*")):
            if path.is_file() and path != review:
                archive.write(path, path.relative_to(ROOT).as_posix())
        for path in [
            ROOT / "config/phase1_nibi_job_package_builder_v1.json",
            ROOT / "docs/PHASE1_NIBI_JOB_PACKAGE_DESIGN.md",
            ROOT / "scripts/48_0_build_phase1_nibi_job_package.py",
            ROOT / "scripts/48_1_validate_phase1_nibi_job_package.py",
            ROOT / "scripts/48_2_run_phase1_exact_local_smoke.py",
            ROOT / "src/fr3_cbf/phase1_job_runtime.py",
            ROOT / "PROJECT_STATUS.md",
            ROOT / "NEXT_IMMEDIATE_STEP.md",
        ]:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(review) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("job-package review ZIP is corrupt")
    digest = sha256_file(review)
    Path(str(review) + ".sha256").write_text(
        f"{digest}  {review.name}\n", encoding="utf-8"
    )

    print("PHASE-1 NIBI JOB-PACKAGE REVIEW BUNDLE: PASS")
    print("Review bundle:", review)
    print("Review bundle SHA-256:", digest)
    print("Campaign execution authorized: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
