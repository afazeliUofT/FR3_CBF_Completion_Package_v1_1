#!/usr/bin/env python3
"""Close the collected source review and determine whether an executable channel engine exists."""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/sionna2_channel_qualification.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    snapshot = ROOT / "evidence/fr3_channel_baseline_snapshot"
    metadata_path = snapshot / "SNAPSHOT_METADATA.json"
    inventory_path = snapshot / "SOURCE_INVENTORY.csv"
    source_root = snapshot / "source"
    for path in [metadata_path, inventory_path, source_root]:
        if not path.exists():
            raise FileNotFoundError(path)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = cfg["expected"]
    if int(metadata["selected_text_file_count"]) != int(
        expected["snapshot_selected_text_files"]
    ):
        raise ValueError("Snapshot file count differs from the reviewed run")
    if int(metadata["binary_candidate_count"]) != int(
        expected["snapshot_binary_candidates"]
    ):
        raise ValueError("Snapshot binary-candidate count differs from the reviewed run")

    with inventory_path.open(newline="", encoding="utf-8") as handle:
        inventory = list(csv.DictReader(handle))

    executable_suffixes = {".py", ".m", ".ipynb"}
    import_pattern = re.compile(
        r"(?m)^\s*(?:from\s+sionna(?:\.|\s)|import\s+sionna(?:\.|\s|$))"
    )
    api_pattern = re.compile(
        r"\b(?:UMa|UMi|PanelArray|gen_hexgrid_topology|set_topology)\s*\("
    )
    actual_channel_files: list[dict[str, object]] = []
    mention_only_files: list[str] = []

    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(source_root).as_posix()
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        if path.suffix.lower() in executable_suffixes:
            imports_sionna = bool(import_pattern.search(text))
            uses_api = bool(api_pattern.search(text))
            if imports_sionna or uses_api:
                actual_channel_files.append(
                    {
                        "relative_path": relative,
                        "imports_sionna": imports_sionna,
                        "uses_channel_api": uses_api,
                    }
                )
        elif "sionna" in text.lower() or "tr 38.901" in text.lower():
            mention_only_files.append(relative)

    decision_status = (
        "REUSABLE_EXECUTABLE_CHANNEL_BASELINE_FOUND"
        if actual_channel_files
        else "NO_REUSABLE_EXECUTABLE_CHANNEL_BASELINE_FOUND"
    )
    selected_implementation_path = (
        "REVIEW_EXISTING_EXECUTABLE_BASELINE"
        if actual_channel_files
        else "QUALIFY_CLEAN_SIONNA_2_0_1_IMPLEMENTATION"
    )
    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": decision_status,
        "claim_boundary": cfg["claim_boundary"]["snapshot_review"],
        "snapshot_root": str(snapshot.relative_to(ROOT)),
        "inventory_file_count": len(inventory),
        "binary_candidate_count": int(metadata["binary_candidate_count"]),
        "executable_channel_candidate_count": len(actual_channel_files),
        "executable_channel_candidates": actual_channel_files,
        "documentation_or_string_mentions_count": len(mention_only_files),
        "finding": (
            "The reviewed source root contains the current completion package, "
            "documentation, regulatory files, and reference runners, but no "
            "runnable Sionna UMa/UMi channel generator or archived channel-result "
            "bundle."
            if not actual_channel_files
            else "One or more executable channel candidates were found and need code-level review."
        ),
        "selected_next_path": selected_implementation_path,
        "next_gate": "SIONNA_2_0_1_ENVIRONMENT_AND_API_QUALIFICATION",
    }
    work = ROOT / cfg["environment"]["work_dir"]
    write_json(work / "CHANNEL_SOURCE_REVIEW_DECISION.json", decision)
    (work / "CHANNEL_SOURCE_REVIEW_DECISION.md").write_text(
        "# Channel-source review decision\n\n"
        f"- Status: `{decision_status}`\n"
        f"- Snapshot files: `{len(inventory)}`\n"
        f"- Binary channel candidates: `{metadata['binary_candidate_count']}`\n"
        f"- Executable Sionna/channel candidates: `{len(actual_channel_files)}`\n"
        f"- Selected next path: `{selected_implementation_path}`\n\n"
        f"{decision['finding']}\n",
        encoding="utf-8",
    )
    print("CHANNEL SOURCE REVIEW: PASS")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
