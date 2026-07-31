#!/usr/bin/env python3
"""Build the local independent-review bundle for the Nibi smoke orchestrator."""
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
        default="config/phase1_nibi_deployment_smoke_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    smoke_root = ROOT / cfg["paths"]["smoke_package_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True)

    for name in [
        "SMOKE_PACKAGE_CONTRACT.json",
        "SMOKE_INDEPENDENT_REVIEW.json",
        "SMOKE_SOURCE_MANIFEST.sha256",
        "SMOKE_ZIP_BINDING.json",
        "FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1.zip",
        "FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_v1.zip.sha256",
    ]:
        source = smoke_root / name
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, evidence / name)

    shutil.copy2(
        ROOT / "docs/PHASE1_NIBI_DEPLOYMENT_SMOKE_INDEPENDENT_REVIEW.md",
        evidence / "PHASE1_NIBI_DEPLOYMENT_SMOKE_INDEPENDENT_REVIEW.md",
    )
    (evidence / "REVIEW_REQUEST.md").write_text(
        "# Nibi deployment-smoke return review request\n\n"
        "After the one-job smoke completes, review the exact environment lock, "
        "GPU/driver record, token scope, Slurm accounting, channel fingerprints, "
        "five-pass/eight-method result, and exclusion markers. Return PASS or a "
        "precise blocker. Do not authorize the 30-seed campaign from this "
        "preparation bundle.\n",
        encoding="utf-8",
        newline="\n",
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(evidence).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    review = (
        evidence
        / "FR3_PHASE1_NIBI_DEPLOYMENT_SMOKE_PREP_REVIEW_v1.zip"
    )
    checksum = Path(str(review) + ".sha256")
    with zipfile.ZipFile(
        review,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(evidence.rglob("*")):
            if (
                path.is_file()
                and path != review
                and path != checksum
            ):
                archive.write(
                    path,
                    path.relative_to(ROOT).as_posix(),
                )
        for path in [
            ROOT / "config/phase1_nibi_deployment_smoke_v1.json",
            ROOT / "scripts/50_0_build_phase1_nibi_deployment_smoke.py",
            ROOT / "scripts/50_1_validate_phase1_nibi_deployment_smoke.py",
            ROOT / "PROJECT_STATUS.md",
            ROOT / "NEXT_IMMEDIATE_STEP.md",
        ]:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(review) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"corrupt smoke-prep review member: {bad}")
    checksum.write_text(
        f"{sha256_file(review)}  {review.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    print("NONCAMPAIGN NIBI DEPLOYMENT SMOKE PREP REVIEW BUNDLE: PASS")
    print("Review bundle:", review)
    print("Review bundle SHA-256:", sha256_file(review))
    print("Full campaign execution authorized: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
