#!/usr/bin/env python3
"""Build a compact independent-review bundle for passes and candidate v2."""
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
        default="config/protected_pass_records_phase1_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    records = ROOT / cfg["paths"]["pass_records_dir"]
    candidate = ROOT / cfg["paths"]["phase1_candidate_v2_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True)

    for name in ["PASS_RECORD_INDEX.json", "PASS_RECORD_CATALOG.csv"]:
        shutil.copy2(records / name, evidence / name)
    for slot in range(5):
        slot_dir = evidence / f"slot_{slot}"
        slot_dir.mkdir()
        for name in [
            "PASS_RECORD_METADATA.json",
            "RECORD_MANIFEST.sha256",
        ]:
            shutil.copy2(
                records / f"slot_{slot}" / name,
                slot_dir / name,
            )
        archive = records / f"FR3_PROTECTED_PASS_SLOT_{slot}.zip"
        shutil.copy2(archive, evidence / archive.name)
        shutil.copy2(
            Path(str(archive) + ".sha256"),
            evidence / f"{archive.name}.sha256",
        )

    candidate_zip = (
        candidate / "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v2.zip"
    )
    shutil.copy2(candidate_zip, evidence / candidate_zip.name)
    shutil.copy2(
        Path(str(candidate_zip) + ".sha256"),
        evidence / f"{candidate_zip.name}.sha256",
    )
    shutil.copy2(
        candidate / "CAMPAIGN_METADATA.json",
        evidence / "CAMPAIGN_METADATA_V2.json",
    )
    shutil.copy2(
        candidate / "INDEPENDENT_REVIEW_STATUS.json",
        evidence / "INDEPENDENT_REVIEW_STATUS.json",
    )
    (evidence / "INDEPENDENT_REVIEW_REQUEST.md").write_text(
        "# Independent review request\n\n"
        "Review the generic 64T64R mapping and complete five-pass phase-1 "
        "candidate. Verify all items in the included review protocol. "
        "Return either PASS or a precise blocking defect. Campaign execution "
        "must remain unauthorized during review.\n",
        encoding="utf-8",
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
    )

    review = ROOT / cfg["paths"]["review_bundle"]
    if review.exists():
        review.unlink()
    with zipfile.ZipFile(
        review,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(evidence.rglob("*")):
            if path.is_file() and path != review:
                archive.write(
                    path,
                    path.relative_to(ROOT).as_posix(),
                )
        for path in [
            ROOT / "config/protected_pass_records_phase1_v1.json",
            ROOT / "src/fr3_cbf/protected_pass_records.py",
            ROOT / "scripts/45_0_generate_protected_pass_records.py",
            ROOT / "scripts/45_1_validate_protected_pass_records.py",
            ROOT / "scripts/45_2_build_complete_phase1_candidate.py",
            ROOT / "docs/PROTECTED_PASS_RECORD_POLICY.md",
            ROOT / "PROJECT_STATUS.md",
            ROOT / "NEXT_IMMEDIATE_STEP.md",
        ]:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(review) as archive:
        assert archive.testzip() is None
    digest = sha256_file(review)
    Path(str(review) + ".sha256").write_text(
        f"{digest}  {review.name}\n",
        encoding="utf-8",
    )
    print("PROTECTED-PASS/PHASE1 REVIEW BUNDLE: PASS")
    print("Review bundle:", review)
    print("Review bundle SHA-256:", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
