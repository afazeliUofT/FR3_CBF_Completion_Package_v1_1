#!/usr/bin/env python3
"""Rebuild the successful P.452 pilot evidence manifest without malformed lines."""
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    parser.add_argument(
        "--output",
        default="data/real/P452_PILOT_COORDINATE_FIXED_EVIDENCE.sha256",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    explicit = [
        "P452_PILOT_COORDINATE_HOTFIX_MANIFEST.sha256",
        "config/p452_pilot.yaml",
        "scripts/21_0_prepare_p452_pilot.py",
        "scripts/21_1_validate_p452_pilot.py",
        "scripts/21_2_preflight_p452_pilot_inputs.py",
        "scripts/20_validate_p452_export.py",
        "matlab/run_p452_pilot.m",
        "logs/21_0_p452_pilot_prepare_coordinate_fix.log",
        "logs/21_0_p452_pilot_freeze_coordinate_fix.log",
        "logs/21_2_p452_pilot_input_preflight.log",
        "logs/p452_pilot_matlab_R2026a_coordinate_fixed.log",
        "logs/p452_pilot_matlab_R2026a_coordinate_fixed.exitcode",
    ]
    paths = [root / item for item in explicit]
    pilot_dir = root / "data/real/p452_pilot"
    if not pilot_dir.is_dir():
        raise FileNotFoundError(pilot_dir)
    paths.extend(sorted(path for path in pilot_dir.iterdir() if path.is_file()))
    output = root / args.output
    paths = [path for path in paths if path.resolve() != output.resolve()]
    missing = [str(path.relative_to(root)) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing pilot evidence files: {missing}")
    unique: dict[str, Path] = {}
    for path in paths:
        rel = path.relative_to(root).as_posix()
        unique[rel] = path
    lines = [f"{sha256_file(path)}  {rel}" for rel, path in sorted(unique.items())]
    if not lines or any(LINE_RE.fullmatch(line) is None for line in lines):
        raise RuntimeError("Generated evidence manifest contains malformed lines")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    for line in output.read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        actual = sha256_file(root / rel)
        if actual != digest:
            raise RuntimeError(f"Post-write hash mismatch: {rel}")
    print("P.452 PILOT EVIDENCE MANIFEST REBUILD: PASS")
    print(f"Entries: {len(lines)}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
