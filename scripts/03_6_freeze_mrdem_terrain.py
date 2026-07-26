#!/usr/bin/env python3
"""Freeze reviewed terrain evidence into the pre-allocation S1 link table.

This script never invents or fills an outage allocation. It only freezes the
terrain stage after file-integrity checks and an explicit human-review record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--links", required=True, help="paired_fs_links_with_terrain.csv")
    parser.add_argument("--summary", required=True, help="terrain_summary.csv")
    parser.add_argument("--profiles", required=True, help="terrain_profile_samples.csv.gz")
    parser.add_argument("--audit", required=True, help="TERRAIN_AUDIT.json")
    parser.add_argument("--review-pdf", required=True, help="Human-review multipage PDF")
    parser.add_argument("--output", default="data/real/paired_fs_links_before_allocation.csv")
    parser.add_argument("--decision-json", default="data/real/TERRAIN_DECISION.json")
    parser.add_argument("--decision-md", default="data/real/TERRAIN_DECISION.md")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--review-note", default="")
    parser.add_argument("--expected-links", type=int, default=70)
    parser.add_argument(
        "--accept-reviewed-flags",
        action="store_true",
        help="Allow nonzero QC flags only after every flagged profile has been reviewed",
    )
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    paths = {
        "links": Path(args.links).expanduser().resolve(),
        "summary": Path(args.summary).expanduser().resolve(),
        "profiles": Path(args.profiles).expanduser().resolve(),
        "audit": Path(args.audit).expanduser().resolve(),
        "review_pdf": Path(args.review_pdf).expanduser().resolve(),
    }
    for path in paths.values():
        require_file(path)
    if args.expected_links <= 0:
        raise ValueError("--expected-links must be positive")

    audit = json.loads(paths["audit"].read_text(encoding="utf-8"))
    required_audit_hashes = {
        "output_links_sha256": paths["links"],
        "summary_csv_sha256": paths["summary"],
        "profiles_csv_gz_sha256": paths["profiles"],
    }
    for key, path in required_audit_hashes.items():
        expected = str(audit.get(key, "")).strip().lower()
        actual = sha256_file(path)
        if not expected:
            raise ValueError(f"Audit record lacks {key}")
        if actual != expected:
            raise ValueError(f"Hash mismatch for {path}: audit={expected}, actual={actual}")

    links = pd.read_csv(paths["links"])
    summary = pd.read_csv(paths["summary"])
    profiles = pd.read_csv(paths["profiles"])
    if len(links) != args.expected_links:
        raise ValueError(f"Expected {args.expected_links} links; found {len(links)}")
    if len(summary) != args.expected_links:
        raise ValueError(f"Expected {args.expected_links} terrain summaries; found {len(summary)}")
    if links["link_id"].astype(str).duplicated().any():
        raise ValueError("Duplicate link_id values in links table")
    if summary["link_id"].astype(str).duplicated().any():
        raise ValueError("Duplicate link_id values in summary table")

    link_ids = set(links["link_id"].astype(str))
    summary_ids = set(summary["link_id"].astype(str))
    profile_ids = set(profiles["link_id"].astype(str))
    if link_ids != summary_ids or link_ids != profile_ids:
        raise ValueError("Link IDs differ among links, terrain summary, and profile samples")

    terrain = pd.to_numeric(links["mean_terrain_elevation_m_asl"], errors="coerce")
    if terrain.isna().any() or not all(math.isfinite(float(v)) for v in terrain):
        raise ValueError("Terrain field contains missing or non-finite values")

    if "allocated_incremental_outage_pct" not in links.columns:
        raise ValueError("Link table lacks allocated_incremental_outage_pct")
    if links["allocated_incremental_outage_pct"].notna().any():
        raise ValueError(
            "Outage allocation is already populated. Terrain freeze must precede and remain "
            "independent of the outage-allocation decision."
        )

    qc_count = int(pd.to_numeric(summary["qc_flag_count"], errors="raise").sum())
    flagged_links = int((pd.to_numeric(summary["qc_flag_count"], errors="raise") > 0).sum())
    if flagged_links and not args.accept_reviewed_flags:
        raise ValueError(
            f"{flagged_links} link(s) have terrain QC flags. Review every flagged profile, then "
            "rerun with --accept-reviewed-flags and a detailed --review-note, or correct the data."
        )
    if args.confirm and not args.review_note.strip():
        raise ValueError("--review-note is required with --confirm")

    stats = {
        "link_count": len(links),
        "profile_sample_count": len(profiles),
        "flagged_link_count": flagged_links,
        "total_qc_flag_count": qc_count,
        "mean_convention": str(summary["selected_mean_convention"].iloc[0]),
        "terrain_mean_min_m_asl": float(terrain.min()),
        "terrain_mean_median_m_asl": float(terrain.median()),
        "terrain_mean_max_m_asl": float(terrain.max()),
        "max_abs_inclusive_interior_difference_m": float(
            pd.to_numeric(summary["inclusive_minus_interior_m"], errors="raise").abs().max()
        ),
        "minimum_tx_implied_agl_m": float(
            pd.to_numeric(summary["tx_implied_antenna_height_agl_m"], errors="raise").min()
        ),
        "minimum_rx_implied_agl_m": float(
            pd.to_numeric(summary["rx_implied_antenna_height_agl_m"], errors="raise").min()
        ),
    }

    print("MRDEM TERRAIN FREEZE PREFLIGHT")
    print(json.dumps(stats, indent=2, sort_keys=True))
    print("TERRAIN FREEZE PREFLIGHT: PASS")
    if not args.confirm:
        print("No files were written because --confirm was not supplied.")
        return 0

    output_path = Path(args.output).expanduser().resolve()
    decision_json = Path(args.decision_json).expanduser().resolve()
    decision_md = Path(args.decision_md).expanduser().resolve()
    for path in (output_path, decision_json, decision_md):
        if path.exists() and not args.force:
            raise FileExistsError(f"{path} already exists; use --force to replace it")
        path.parent.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(paths["links"], output_path)
    decision = {
        "decision": "MRDEM_TERRAIN_FROZEN_PENDING_OUTAGE_ALLOCATION",
        "decided_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer": args.reviewer,
        "review_note": args.review_note.strip(),
        "accepted_reviewed_qc_flags": bool(args.accept_reviewed_flags),
        "stats": stats,
        "inputs": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in paths.items()
        },
        "output": {
            "path": str(output_path),
            "sha256": sha256_file(output_path),
        },
        "claim_boundary": (
            "This decision freezes the discretely sampled MRDEM DTM terrain means for the "
            "cited 70-link dataset. It does not establish an outage allocation, validate the "
            "final S1 cap, or assert that TAFL and MRDEM use identical vertical-datum realizations."
        ),
        "remaining_blocker": "explicit allocated_incremental_outage_pct decision",
    }
    decision_json.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = [
        "# MRDEM Terrain Decision",
        "",
        "- **Decision:** Terrain frozen; outage allocation remains open",
        f"- **Reviewer:** {args.reviewer}",
        f"- **UTC time:** {decision['decided_utc']}",
        f"- **Directed links:** {stats['link_count']}",
        f"- **Selected discrete mean convention:** {stats['mean_convention']}",
        f"- **Flagged links explicitly reviewed:** {stats['flagged_link_count']}",
        f"- **Review note:** {args.review_note.strip()}",
        "",
        "## Claim boundary",
        "",
        decision["claim_boundary"],
        "",
        "## Remaining blocker",
        "",
        "Declare and document the incremental worst-month outage allocation before creating "
        "`data/real/paired_fs_links.csv` and running real S1 validation.",
        "",
    ]
    decision_md.write_text("\n".join(md), encoding="utf-8")

    print(f"Wrote: {output_path}")
    print(f"Wrote: {decision_json}")
    print(f"Wrote: {decision_md}")
    print("MRDEM TERRAIN FREEZE: PASS")
    print("Do not run real S1 validation yet: the outage allocation remains blank.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
