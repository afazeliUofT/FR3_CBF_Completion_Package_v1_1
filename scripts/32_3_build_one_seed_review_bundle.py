#!/usr/bin/env python3
"""Build a compact review bundle for the one-seed freeze and contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

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
        "--config", default="config/one_seed_18658301_freeze.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    output = ROOT / cfg["paths"]["review_bundle"]
    output.parent.mkdir(parents=True, exist_ok=True)

    selected_roots = [
        evidence,
    ]
    selected_files = [
        ROOT / "config/dynamic_safety_experiment_v1.yaml",
        ROOT / "config/controller_ready_full_topology_export_v1.yaml",
        ROOT / "config/current_audited_state.yaml",
        ROOT / "docs/DYNAMIC_SAFETY_EXPERIMENT_CONTRACT.md",
        ROOT / "docs/CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_SPEC.md",
        ROOT / "src/fr3_cbf/physical_accounting.py",
        ROOT / "PROJECT_STATUS.md",
        ROOT / "NEXT_IMMEDIATE_STEP.md",
        ROOT / "ROADMAP.md",
        ROOT / "COMPUTE_EXECUTION_STATUS.md",
    ]

    files: list[tuple[Path, str]] = []
    for root in selected_roots:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path != output and not path.name.endswith(
                ".zip.sha256"
            ):
                files.append((path, path.relative_to(ROOT).as_posix()))
    for path in selected_files:
        if not path.is_file():
            raise FileNotFoundError(path)
        files.append((path, path.relative_to(ROOT).as_posix()))

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "READY_FOR_INDEPENDENT_REVIEW",
        "job_id": "18658301",
        "claim_boundary": cfg["claim_boundary"],
        "file_count": len(files),
        "next_gate": cfg["next_gate"],
    }
    metadata_path = evidence / "REVIEW_BUNDLE_METADATA.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    files.append(
        (metadata_path, metadata_path.relative_to(ROOT).as_posix())
    )

    if output.exists():
        output.unlink()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for path, arcname in sorted(files, key=lambda item: item[1]):
            archive.write(path, arcname)
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"Corrupt review member: {bad}")

    checksum = Path(str(output) + ".sha256")
    checksum.write_text(
        f"{sha256_file(output)}  {output.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    print("ONE-SEED/DYNAMIC-CONTRACT REVIEW BUNDLE: PASS")
    print("Review bundle:", output)
    print("Review bundle SHA-256:", sha256_file(output))
    print("Files:", len(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
