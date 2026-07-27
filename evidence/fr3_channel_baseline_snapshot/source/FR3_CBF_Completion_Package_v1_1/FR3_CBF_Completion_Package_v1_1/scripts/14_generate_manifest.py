from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import ROOT
from fr3_cbf.io import sha256_file

EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "_components_extracted"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a SHA-256 manifest")
    parser.add_argument("--output", default="MANIFEST.sha256")
    parser.add_argument("--include-results", action="store_true")
    args = parser.parse_args()
    output = ROOT / args.output
    lines = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path == output:
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if not args.include_results and rel.parts and rel.parts[0] in {"results", "logs"}:
            continue
        lines.append(f"{sha256_file(path)}  {rel.as_posix()}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} hashes to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
