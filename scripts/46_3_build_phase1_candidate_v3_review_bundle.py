#!/usr/bin/env python3
"""Build the candidate-v3 independent-review preparation bundle."""
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
        "--contract",
        default="config/phase1_campaign_contract_v3.json",
    )
    args = parser.parse_args()
    contract = json.loads(
        (ROOT / args.contract).read_text(encoding="utf-8")
    )
    candidate = ROOT / "campaign/phase1_candidate_v3"
    evidence = ROOT / "evidence/phase1_candidate_v3_review"
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True)

    for name in [
        "CAMPAIGN_METADATA.json",
        "PHASE1_CAMPAIGN_CONTRACT_V3.json",
        "CANDIDATE_PROVENANCE.json",
        "SOURCE_SNAPSHOT_RECORD.json",
        "INDEPENDENT_REVIEW_STATUS.json",
        "PHASE1_INDEPENDENT_REVIEW_ROUND1.md",
        "PHASE1_STATISTICAL_ANALYSIS_PLAN_V3.md",
        "PHASE1_METHOD_INFORMATION_CONTRACT_V3.md",
        "BUNDLE_MANIFEST.sha256",
        "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip",
        "FR3_PHASE1_CAMPAIGN_REVIEW_CANDIDATE_v3.zip.sha256",
    ]:
        source = candidate / name
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, evidence / name)

    (evidence / "ROUND2_INDEPENDENT_REVIEW_REQUEST.md").write_text(
        "# Round-2 independent review request\n\n"
        "Verify that candidate v3 resolves every blocker in "
        "`PHASE1_INDEPENDENT_REVIEW_ROUND1.md`, that all five pass records "
        "remain immutable, that method information sets and timing are fair, "
        "that the seed-cluster statistical plan is coherent, and that campaign "
        "execution remains locked. Return PASS or a precise remaining defect.\n",
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

    review = (
        evidence
        / "FR3_PHASE1_CANDIDATE_V3_REVIEW_PREP_v1.zip"
    )
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
            ROOT / "config/phase1_campaign_contract_v3.json",
            ROOT / "docs/PHASE1_INDEPENDENT_REVIEW_ROUND1.md",
            ROOT / "docs/PHASE1_STATISTICAL_ANALYSIS_PLAN_V3.md",
            ROOT / "docs/PHASE1_METHOD_INFORMATION_CONTRACT_V3.md",
            ROOT / "scripts/46_0_build_phase1_candidate_v3.py",
            ROOT / "scripts/46_1_validate_phase1_candidate_v3.py",
            ROOT / "PROJECT_STATUS.md",
            ROOT / "NEXT_IMMEDIATE_STEP.md",
        ]:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(review) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"corrupt review member: {bad}")

    digest = sha256_file(review)
    Path(str(review) + ".sha256").write_text(
        f"{digest}  {review.name}\n",
        encoding="utf-8",
    )
    print("PHASE-1 CANDIDATE V3 REVIEW-PREP BUNDLE: PASS")
    print("Review bundle:", review)
    print("Review bundle SHA-256:", digest)
    print("Execution authorized: NO")
    print("Next gate:", contract["next_gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
