#!/usr/bin/env python3
"""Build the online-PF load-transition milestone review bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
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
        "--config",
        default="config/online_pf_load_transition_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    results = ROOT / cfg["paths"]["results_dir"]
    output = ROOT / cfg["paths"]["review_bundle"]
    output.parent.mkdir(parents=True, exist_ok=True)

    files = [
        path
        for path in sorted(evidence.rglob("*"))
        if path.is_file()
        and path != output
        and not path.name.endswith(".zip.sha256")
    ]
    action_record = results / "ONLINE_PF_ACTIONS_AND_AVERAGES.npz"
    if not action_record.is_file():
        raise FileNotFoundError(action_record)
    files.append(action_record)
    for path in [
        ROOT / "config/online_pf_load_transition_v1.json",
        ROOT / "config/multi_seed_campaign_spec_v1.json",
        ROOT / "config/online_pf_load_transition_validated_state_v1.json",
        ROOT / "src/fr3_cbf/online_pf_load_transition.py",
        ROOT / "scripts/39_0_run_online_pf_load_transition.py",
        ROOT / "scripts/39_1_validate_online_pf_load_transition.py",
        ROOT / "docs/DELAYED_REACHABILITY_SAFETY_THEOREM.md",
        ROOT / "PROJECT_STATUS.md",
        ROOT / "NEXT_IMMEDIATE_STEP.md",
    ]:
        if not path.is_file():
            raise FileNotFoundError(path)
        files.append(path)

    if output.exists():
        output.unlink()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(set(files)):
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"Corrupt review member: {bad}")

    checksum = Path(str(output) + ".sha256")
    checksum.write_text(
        f"{sha256_file(output)}  {output.name}\n",
        encoding="utf-8",
    )
    print("ONLINE PF LOAD-TRANSITION REVIEW BUNDLE: PASS")
    print("Review bundle:", output)
    print("Review bundle SHA-256:", sha256_file(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
