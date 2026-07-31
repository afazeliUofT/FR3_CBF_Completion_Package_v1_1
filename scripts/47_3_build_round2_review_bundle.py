#!/usr/bin/env python3
"""Build the external round-2 review evidence bundle."""
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
    evidence = ROOT / "evidence/phase1_candidate_v3_round2_review"
    output = (
        evidence
        / "FR3_PHASE1_CANDIDATE_V3_ROUND2_REVIEW_v1.zip"
    )
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(evidence.rglob("*")):
            if (
                path.is_file()
                and path != output
                and path != Path(str(output) + ".sha256")
            ):
                archive.write(
                    path,
                    path.relative_to(ROOT).as_posix(),
                )
        for path in [
            ROOT / "config/phase1_candidate_v3_round2_review_v1.json",
            ROOT / "docs/PHASE1_INDEPENDENT_REVIEW_ROUND2.md",
            ROOT / "scripts/47_0_verify_freeze_round2_review.py",
            ROOT / "scripts/47_1_validate_round2_review_freeze.py",
            ROOT / "PROJECT_STATUS.md",
            ROOT / "NEXT_IMMEDIATE_STEP.md",
        ]:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("round-2 review ZIP is corrupt")

    digest = sha256_file(output)
    Path(str(output) + ".sha256").write_text(
        f"{digest}  {output.name}\n",
        encoding="utf-8",
    )
    print("PHASE-1 ROUND-2 REVIEW BUNDLE: PASS")
    print("Review bundle:", output)
    print("Review bundle SHA-256:", digest)
    print("Campaign execution authorized: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
