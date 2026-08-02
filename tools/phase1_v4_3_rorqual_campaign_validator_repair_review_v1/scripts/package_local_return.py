#!/usr/bin/env python3
"""Package local reclassification and Rorqual campaign-build evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--return-dir", required=True)
    parser.add_argument("--audit-root", required=True)
    parser.add_argument("--build-root", required=True)
    parser.add_argument("--review-root", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--workflow-exit-code", required=True, type=int)
    parser.add_argument("--git-final-commit", required=True)
    parser.add_argument("--git-remote-final-commit", required=True)
    args = parser.parse_args()
    return_dir = Path(args.return_dir).resolve()
    return_dir.mkdir(parents=True, exist_ok=True)
    content = return_dir / "return_content"
    if content.exists():
        shutil.rmtree(content)
    content.mkdir()

    audit_root = Path(args.audit_root).resolve()
    build_root = Path(args.build_root).resolve()
    review_root = Path(args.review_root).resolve()
    files = [
        audit_root / "SMOKE_RECLASSIFICATION_VERDICT.json",
        audit_root / "GEOMETRIC_MEAN_DEFINITION_AUDIT.csv",
        audit_root / "EXCLUDED_SEED_PAIRED_EFFECT_SUMMARY.csv",
        audit_root / "CORRECTED_VALIDATOR_STRUCTURAL.log",
        audit_root / "CORRECTED_VALIDATOR_SCIENTIFIC.log",
        build_root / "BUILD_AUDIT.json",
        build_root / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip",
        build_root / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2.zip.sha256",
        review_root / "INDEPENDENT_REVIEW_VERDICT.json",
        review_root / "REVIEW_CHECK_SUMMARY.json",
        review_root / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_INDEPENDENT_REVIEW.zip",
        review_root / "FR3_PHASE1_RORQUAL_JOB_PACKAGE_V4_3_R2_INDEPENDENT_REVIEW.zip.sha256",
    ]
    for path in files:
        if path.is_file():
            shutil.copy2(path, content / path.name)
    log = Path(args.log).resolve()
    if log.is_file():
        normalized = "\n".join(
            line.rstrip() for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
        ) + "\n"
        (content / "LOCAL_WSL_ORCHESTRATOR.log").write_text(normalized, encoding="utf-8")

    status = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "workflow_exit_code": args.workflow_exit_code,
        "git_final_commit": args.git_final_commit,
        "git_remote_final_commit": args.git_remote_final_commit,
        "cluster_contacted": False,
        "campaign_execution_authorized": False,
        "next_gate": "SEPARATE_RORQUAL_30_SEED_CAMPAIGN_AUTHORIZATION_AND_EXECUTION",
    }
    write_json(content / "RETURN_STATUS.json", status)

    manifest_lines = []
    for path in sorted(content.iterdir()):
        if path.is_file():
            manifest_lines.append(f"{sha256_file(path)}  {path.name}")
    (content / "RETURN_MANIFEST.sha256").write_text(
        "\n".join(manifest_lines) + "\n", encoding="utf-8"
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive = return_dir / f"FR3_V4_3_RORQUAL_CAMPAIGN_REPAIR_REVIEW_{stamp}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(content.iterdir()):
            if path.is_file():
                zf.write(path, path.name)
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"return ZIP CRC failure: {bad}")
    digest = sha256_file(archive)
    sidecar = Path(str(archive) + ".sha256")
    sidecar.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    shutil.copy2(content / "LOCAL_WSL_ORCHESTRATOR.log", return_dir / "LOCAL_WSL_ORCHESTRATOR.log")
    print(f"LOCAL_RETURN_ZIP={archive}")
    print(f"LOCAL_RETURN_ZIP_SHA256={digest}")
    print(f"LOCAL_RETURN_SIDECAR={sidecar}")
    print("LOCAL_RETURN_ZIP_CRC=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
