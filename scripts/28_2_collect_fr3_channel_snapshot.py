#!/usr/bin/env python3
"""Collect a bounded, text-only snapshot of reusable FR3 channel code."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from _bootstrap import ROOT


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sanitize_notebook(text: str) -> str:
    obj = json.loads(text)
    for cell in obj.get("cells", []):
        if isinstance(cell, dict):
            cell["outputs"] = []
            cell["execution_count"] = None
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/distributed_channel_readiness.yaml"
    )
    parser.add_argument("--source-root")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    snap = cfg["source_snapshot"]
    source_root = Path(
        args.source_root
        or os.environ.get("FR3_CHANNEL_SOURCE_ROOT")
        or snap["default_root"]
    )
    fallback_parent = Path(snap["fallback_parent"])

    if not source_root.is_dir():
        print("ERROR: FR3 channel source root was not found:")
        print(" ", source_root)
        print("Candidate directories:")
        candidates = []
        if fallback_parent.is_dir():
            for path in fallback_parent.rglob("*"):
                if path.is_dir() and re.search(
                    r"(fr3|channel|sionna|beamform|precod)",
                    path.name,
                    flags=re.IGNORECASE,
                ):
                    candidates.append(path)
                    if len(candidates) >= 60:
                        break
        for path in candidates:
            print(" ", path)
        raise SystemExit(
            "Set FR3_CHANNEL_SOURCE_ROOT to the correct directory and rerun "
            "the same master drop-in."
        )

    excluded = {str(value).lower() for value in snap["excluded_directory_names"]}
    text_extensions = {str(value).lower() for value in snap["text_extensions"]}
    binary_extensions = {
        str(value).lower() for value in snap["binary_inventory_extensions"]
    }
    keywords = [str(value).lower() for value in snap["relevance_keywords"]]
    secret_names = [re.escape(str(value)) for value in snap["common_secret_names"]]
    secret_pattern = re.compile(
        rf"(?im)^\s*(?:{'|'.join(secret_names)})\s*[:=]\s*\S+"
    )

    output_root = ROOT / cfg["outputs"]["source_snapshot_dir"]
    source_output = output_root / "source"
    if output_root.exists():
        shutil.rmtree(output_root)
    source_output.mkdir(parents=True, exist_ok=True)

    max_file = int(snap["maximum_text_file_bytes"])
    max_total = int(snap["maximum_total_snapshot_bytes"])
    max_count = int(snap["maximum_selected_files"])

    candidates = []
    binary_rows = []
    rejected_rows = []

    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if any(part.lower() in excluded for part in relative.parts[:-1]):
            continue
        if ":Zone.Identifier" in path.name:
            continue
        suffix = path.suffix.lower()
        size = path.stat().st_size

        if suffix in binary_extensions:
            binary_rows.append(
                {
                    "relative_path": relative.as_posix(),
                    "bytes": size,
                    "sha256": sha256_file(path),
                    "extension": suffix,
                }
            )
            continue
        if suffix not in text_extensions:
            continue
        if size > max_file:
            rejected_rows.append(
                {
                    "relative_path": relative.as_posix(),
                    "bytes": size,
                    "reason": "text_file_exceeds_limit",
                }
            )
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="strict")
        except (UnicodeDecodeError, OSError):
            rejected_rows.append(
                {
                    "relative_path": relative.as_posix(),
                    "bytes": size,
                    "reason": "not_strict_utf8_text",
                }
            )
            continue

        if secret_pattern.search(text):
            raise SystemExit(
                "POTENTIAL SECRET DETECTED; SNAPSHOT ABORTED:\n"
                + relative.as_posix()
            )

        search_text = (relative.as_posix() + "\n" + text[:750_000]).lower()
        hits = sorted({keyword for keyword in keywords if keyword in search_text})
        root_priority = (
            len(relative.parts) == 1
            and re.search(
                r"(readme|requirement|environment|pyproject|setup|makefile|license)",
                relative.name,
                flags=re.IGNORECASE,
            )
        )
        score = len(hits) + (3 if root_priority else 0)
        candidates.append(
            {
                "path": path,
                "relative": relative,
                "bytes": size,
                "sha256": sha256_file(path),
                "text": text,
                "hits": hits,
                "score": score,
            }
        )

    relevant_dirs = {
        item["relative"].parent
        for item in candidates
        if int(item["score"]) >= 2
    }
    selected = [
        item
        for item in candidates
        if int(item["score"]) >= 2
        or item["relative"].parent in relevant_dirs
        or (len(item["relative"].parts) == 1 and int(item["score"]) >= 1)
    ]
    selected.sort(
        key=lambda item: (
            -int(item["score"]),
            len(item["relative"].parts),
            item["relative"].as_posix(),
        )
    )

    copied = []
    total = 0
    for item in selected:
        if len(copied) >= max_count:
            rejected_rows.append(
                {
                    "relative_path": item["relative"].as_posix(),
                    "bytes": item["bytes"],
                    "reason": "snapshot_file_count_limit",
                }
            )
            continue
        if total + int(item["bytes"]) > max_total:
            rejected_rows.append(
                {
                    "relative_path": item["relative"].as_posix(),
                    "bytes": item["bytes"],
                    "reason": "snapshot_total_size_limit",
                }
            )
            continue
        text = item["text"].replace("\r\n", "\n").replace("\r", "\n")
        if item["relative"].suffix.lower() == ".ipynb":
            try:
                text = sanitize_notebook(text)
            except Exception as exc:
                rejected_rows.append(
                    {
                        "relative_path": item["relative"].as_posix(),
                        "bytes": item["bytes"],
                        "reason": f"notebook_sanitization_failed:{type(exc).__name__}",
                    }
                )
                continue
        if text and not text.endswith("\n"):
            text += "\n"
        target = source_output / item["relative"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        copied.append(
            {
                "relative_path": item["relative"].as_posix(),
                "bytes_original": int(item["bytes"]),
                "bytes_snapshot": target.stat().st_size,
                "sha256_original": item["sha256"],
                "sha256_snapshot": sha256_file(target),
                "keyword_hits": "|".join(item["hits"]),
                "relevance_score": int(item["score"]),
            }
        )
        total += target.stat().st_size

    if not copied:
        raise SystemExit(
            "No relevant source/configuration files were selected. "
            "Check FR3_CHANNEL_SOURCE_ROOT."
        )

    output_root.mkdir(parents=True, exist_ok=True)

    def write_csv(name: str, rows: list[dict], fields: list[str]) -> None:
        with (output_root / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    write_csv(
        "SOURCE_INVENTORY.csv",
        copied,
        [
            "relative_path",
            "bytes_original",
            "bytes_snapshot",
            "sha256_original",
            "sha256_snapshot",
            "keyword_hits",
            "relevance_score",
        ],
    )
    write_csv(
        "BINARY_CANDIDATES.csv",
        binary_rows,
        ["relative_path", "bytes", "sha256", "extension"],
    )
    write_csv(
        "REJECTED_FILES.csv",
        rejected_rows,
        ["relative_path", "bytes", "reason"],
    )

    git_info = {}
    if (source_root / ".git").is_dir():
        for key, command in {
            "commit": ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            "branch": ["git", "-C", str(source_root), "branch", "--show-current"],
            "origin": ["git", "-C", str(source_root), "remote", "get-url", "origin"],
        }.items():
            try:
                git_info[key] = subprocess.check_output(
                    command, text=True, stderr=subprocess.DEVNULL
                ).strip()
            except Exception:
                git_info[key] = None

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"]["channel_snapshot"],
        "source_root": str(source_root),
        "selected_text_file_count": len(copied),
        "snapshot_bytes": total,
        "binary_candidate_count": len(binary_rows),
        "rejected_file_count": len(rejected_rows),
        "secret_screen": "PASS_COMMON_PATTERNS",
        "notebook_outputs_removed": True,
        "git": git_info,
        "purpose": (
            "Review reusable channel/topology/rate infrastructure. WMMSE is "
            "not adopted as the operational method."
        ),
        "next_gate": "CODE_LEVEL_REVIEW_OF_EXISTING_CHANNEL_BASELINE",
    }
    (output_root / "SNAPSHOT_METADATA.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    priority = sorted(
        copied,
        key=lambda row: (-int(row["relevance_score"]), row["relative_path"]),
    )[:120]
    with (output_root / "REVIEW_PRIORITY.md").open(
        "w", encoding="utf-8"
    ) as handle:
        handle.write("# FR3 channel-baseline review priority\n\n")
        handle.write(
            "Review channel generation, topology, array, power, noise, SINR, "
            "and rate code for reuse. WMMSE code may appear because it shares "
            "infrastructure, but WMMSE is not the proposed operational method.\n\n"
        )
        for row in priority:
            handle.write(
                f"- `{row['relative_path']}` — score "
                f"{row['relevance_score']}; hits: "
                f"{row['keyword_hits'] or 'none'}\n"
            )

    print("FR3 CHANNEL BASELINE SOURCE SNAPSHOT: PASS")
    print("Source root:", source_root)
    print("Selected text files:", len(copied))
    print("Snapshot bytes:", total)
    print("Binary candidates:", len(binary_rows))
    print("Rejected files:", len(rejected_rows))
    print("Output:", output_root)
    print("Priority files:")
    for row in priority[:40]:
        print(" ", row["relative_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
