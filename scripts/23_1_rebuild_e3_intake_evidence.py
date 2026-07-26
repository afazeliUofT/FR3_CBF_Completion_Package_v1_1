#!/usr/bin/env python3
"""Rebuild E3 reference-intake evidence with strict GNU sha256sum formatting."""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

LINE_RE = re.compile(r"^[0-9a-f]{64}  .+$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def admissible(path: Path, output: Path) -> bool:
    if path == output:
        return False
    if any(part == "__pycache__" for part in path.parts):
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    if path.name.endswith(":Zone.Identifier"):
        return False
    if "\n" in str(path) or "\r" in str(path):
        raise ValueError(f"Path contains a newline: {path!s}")
    return path.is_file()


def build_manifest(root: Path, output: Path) -> list[str]:
    explicit = [
        root / "E3_REFERENCE_INTAKE_MANIFEST.sha256",
        root / "config/e3_reference_intake.yaml",
        root / "scripts/22_0_rebuild_p452_pilot_evidence.py",
        root / "scripts/22_1_prepare_e3_station.py",
        root / "scripts/22_2_fetch_validate_e3_tle.py",
        root / "scripts/22_3_generate_select_e3_pass.py",
        root / "RUN_E3_REFERENCE_INTAKE.sh",
        root / "logs/22_0_rebuild_p452_pilot_evidence.log",
        root / "logs/22_1_prepare_e3_station.log",
        root / "logs/22_2_fetch_validate_e3_tle.log",
        root / "logs/22_3_generate_select_e3_pass.log",
    ]
    trees = [
        root / "data/real/e3_reference_case",
        root / "data/external/tle",
        root / "data/external/mrdem_e3_reference",
    ]
    files: set[Path] = set()
    for path in explicit:
        if not path.is_file():
            raise FileNotFoundError(path)
        files.add(path)
    for tree in trees:
        if not tree.is_dir():
            raise FileNotFoundError(tree)
        for path in tree.rglob("*"):
            if admissible(path, output):
                files.add(path)
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in sorted(files)]
    if not lines or not all(LINE_RE.fullmatch(line) for line in lines):
        raise RuntimeError("Internal checksum-line validation failed")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/real/E3_REFERENCE_INTAKE_EVIDENCE.sha256")
    parser.add_argument("--root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    output = root / args.output
    lines = build_manifest(root, output)
    print("E3 REFERENCE-INTAKE EVIDENCE REBUILD: PASS")
    print(f"Entries: {len(lines)}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
