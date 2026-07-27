from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from _bootstrap import ROOT
from fr3_cbf.io import load_yaml, sha256_file

REQUIRED = [
    "README_FIRST.md",
    "NEXT_IMMEDIATE_STEP.md",
    "COMPLETION_ROADMAP.md",
    "PROJECT_STATUS.md",
    "config/regulatory_constants.yaml",
    "config/project.yaml",
    "config/s1_adequacy.yaml",
    "docs/FR3_CBF_System_Model.pdf",
    "docs/FR3_CBF_Tutorial.pdf",
    "source_documents/R-REC-P.530-19-202509.zip",
    "src/fr3_cbf/p530.py",
    "scripts/04_run_s1_adequacy.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail if any YAML item is OPEN")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    for rel in REQUIRED:
        path = ROOT / rel
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"Missing/empty: {rel}")

    reg = load_yaml(ROOT / "config/regulatory_constants.yaml")
    allowed = set(reg["metadata"]["allowed_status_values"])

    def walk(value, path="root"):
        if isinstance(value, dict):
            if "status" in value and value["status"] not in allowed:
                errors.append(f"Invalid status at {path}: {value['status']}")
            if value.get("status") == "OPEN":
                warnings.append(f"OPEN item: {path}")
            for k, v in value.items():
                walk(v, f"{path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{path}[{i}]")

    walk(reg)

    archive = ROOT / "source_documents/R-REC-P.530-19-202509.zip"
    expected_hash = reg["source_documents"]["user_supplied_p530_archive"]["sha256"]
    if archive.exists():
        actual = sha256_file(archive)
        if actual != expected_hash:
            errors.append(f"P.530 archive hash mismatch: {actual}")
        try:
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
                if not any(name.lower().endswith(".pdf") for name in names):
                    errors.append("P.530 archive does not contain a PDF")
        except zipfile.BadZipFile:
            errors.append("P.530 archive is not a valid ZIP")

    if args.strict and warnings:
        errors.extend(warnings)

    print("FR3 CBF package validation")
    for item in warnings:
        print("WARNING:", item)
    if errors:
        for item in errors:
            print("ERROR:", item)
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
