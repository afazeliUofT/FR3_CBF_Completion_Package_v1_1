#!/usr/bin/env python3
"""Recover superseded E3 selection inputs after the v1 wrapper archived them.

This script is fail-closed. It accepts a historical selection only when every
recoverable copy agrees on the expected superseded site/sector, and it accepts
a historical off-axis summary only when it is a unique 57-sector table whose
global minimum agrees with that historical selection.
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
import yaml


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected: {path}")
    return data


def semantic_selection(record: dict) -> tuple[str, str, float, float]:
    return (
        str(record.get("sector_id")),
        str(record.get("site_id")),
        float(record.get("distance_m")),
        float(record.get("minimum_earth_station_off_axis_deg")),
    )


def validate_historical_summary(
    frame: pd.DataFrame,
    selection: dict,
    *,
    expected_sector_count: int,
) -> None:
    required = {
        "site_id",
        "sector_id",
        "station_to_site_distance_m",
        "minimum_off_axis_deg_during_selected_track",
        "median_off_axis_deg_during_selected_track",
        "maximum_reference_gain_dbi_during_selected_track",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Historical off-axis summary missing columns: {missing}")
    if len(frame) != expected_sector_count:
        raise ValueError(
            f"Historical summary has {len(frame)} rows; expected {expected_sector_count}"
        )
    if frame["sector_id"].astype(str).nunique() != expected_sector_count:
        raise ValueError("Historical summary sector IDs are not unique")
    if "selection_window" in frame.columns:
        values = set(frame["selection_window"].dropna().astype(str))
        if values and values != {"all_detailed_track_samples_historical"}:
            raise ValueError(
                "Historical summary candidate appears to contain a protected-window "
                f"selection label: {sorted(values)}"
            )

    numeric = frame[
        [
            "station_to_site_distance_m",
            "minimum_off_axis_deg_during_selected_track",
            "median_off_axis_deg_during_selected_track",
            "maximum_reference_gain_dbi_during_selected_track",
        ]
    ].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("Historical summary contains invalid numeric values")

    selected_site = str(selection["site_id"])
    site_rows = frame.loc[frame["site_id"].astype(str) == selected_site]
    if site_rows.empty:
        raise ValueError("Historical selected site is absent from historical summary")

    global_minimum = float(numeric["minimum_off_axis_deg_during_selected_track"].min())
    site_minimum = float(
        pd.to_numeric(
            site_rows["minimum_off_axis_deg_during_selected_track"],
            errors="raise",
        ).min()
    )
    selected_minimum = float(selection["minimum_earth_station_off_axis_deg"])
    if not math.isclose(global_minimum, selected_minimum, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(
            "Historical summary global minimum does not match historical selected record: "
            f"summary={global_minimum}, selected={selected_minimum}"
        )
    if not math.isclose(site_minimum, selected_minimum, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("Historical selected site is not the historical minimum site")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/e3_protected_window_correction.yaml",
    )
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    config_path = root / args.config
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    expected = cfg["expected"]

    expected_sector = str(expected["superseded_sector_id"])
    expected_site = str(expected["superseded_site_id"])
    expected_sector_count = int(expected["sector_count"])

    stable_selection = root / cfg["inputs"]["old_selected_sector_json"]
    stable_summary = root / cfg["inputs"]["old_off_axis_summary_csv"]
    active_selection = root / "data/real/e3_first_sector_audit/selected_sector.json"
    evidence_selection = root / "evidence/e3_first_sector/selected_sector.json"

    selection_candidates: list[Path] = []
    for path in [stable_selection, active_selection, evidence_selection]:
        if path.is_file():
            selection_candidates.append(path)
    selection_candidates.extend(
        sorted(
            root.glob(
                "data/real/e3_first_sector_audit_superseded_unprotected_window_*/"
                "selected_sector.json"
            )
        )
    )

    valid_selection: list[tuple[Path, dict, str]] = []
    rejected_selection: list[dict[str, str]] = []
    seen: set[Path] = set()
    for path in selection_candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            record = load_json(path)
            if str(record.get("sector_id")) != expected_sector:
                raise ValueError(f"sector_id={record.get('sector_id')!r}")
            if str(record.get("site_id")) != expected_site:
                raise ValueError(f"site_id={record.get('site_id')!r}")
            semantic_selection(record)
            valid_selection.append((path, record, sha256_file(path)))
        except Exception as exc:
            rejected_selection.append(
                {"path": str(path.relative_to(root)), "reason": str(exc)}
            )

    if not valid_selection:
        raise RuntimeError(
            "No recoverable superseded selected-sector record was found. "
            f"Rejected candidates: {rejected_selection}"
        )

    semantic_values = {semantic_selection(record) for _, record, _ in valid_selection}
    if len(semantic_values) != 1:
        raise RuntimeError(
            "Conflicting superseded selection records were found: "
            + repr(
                [
                    {
                        "path": str(path.relative_to(root)),
                        "semantic": semantic_selection(record),
                    }
                    for path, record, _ in valid_selection
                ]
            )
        )

    def selection_priority(item: tuple[Path, dict, str]) -> tuple[int, str]:
        path = item[0]
        rel = path.relative_to(root).as_posix()
        if path.resolve() == stable_selection.resolve():
            priority = 0
        elif "e3_first_sector_audit_superseded_unprotected_window_" in rel:
            priority = 1
        elif path.resolve() == active_selection.resolve():
            priority = 2
        else:
            priority = 3
        return priority, rel

    valid_selection.sort(key=selection_priority)
    selection_source, selection_record, _ = valid_selection[0]

    stable_selection.parent.mkdir(parents=True, exist_ok=True)
    if stable_selection.is_file():
        existing = load_json(stable_selection)
        if semantic_selection(existing) != semantic_selection(selection_record):
            raise RuntimeError("Stable historical selection conflicts with recovered source")
    else:
        shutil.copy2(selection_source, stable_selection)

    current_summary = root / "data/real/e3_pattern_layout_review/selected_pass_off_axis_summary.csv"
    summary_candidates = [path for path in [stable_summary, current_summary] if path.is_file()]

    valid_summary: list[tuple[Path, str]] = []
    rejected_summary: list[dict[str, str]] = []
    seen.clear()
    for path in summary_candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            frame = pd.read_csv(path)
            validate_historical_summary(
                frame,
                selection_record,
                expected_sector_count=expected_sector_count,
            )
            valid_summary.append((path, sha256_file(path)))
        except Exception as exc:
            rejected_summary.append(
                {"path": str(path.relative_to(root)), "reason": str(exc)}
            )

    if not valid_summary:
        raise RuntimeError(
            "No valid historical unprotected-window off-axis summary was found. "
            f"Rejected candidates: {rejected_summary}"
        )

    summary_hashes = {digest for _, digest in valid_summary}
    if len(summary_hashes) != 1:
        raise RuntimeError(
            "Multiple valid historical summaries differ byte-for-byte; manual review required: "
            + repr(
                [
                    {"path": str(path.relative_to(root)), "sha256": digest}
                    for path, digest in valid_summary
                ]
            )
        )

    valid_summary.sort(
        key=lambda item: (
            0 if item[0].resolve() == stable_summary.resolve() else 1,
            item[0].relative_to(root).as_posix(),
        )
    )
    summary_source, _ = valid_summary[0]
    stable_summary.parent.mkdir(parents=True, exist_ok=True)
    if stable_summary.is_file():
        if sha256_file(stable_summary) != sha256_file(summary_source):
            raise RuntimeError("Stable historical summary conflicts with recovered source")
    else:
        shutil.copy2(summary_source, stable_summary)

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "historical_sector_id": expected_sector,
        "historical_site_id": expected_site,
        "stable_selection_path": str(stable_selection.relative_to(root)),
        "stable_selection_sha256": sha256_file(stable_selection),
        "selection_recovery_source": str(selection_source.relative_to(root)),
        "stable_summary_path": str(stable_summary.relative_to(root)),
        "stable_summary_sha256": sha256_file(stable_summary),
        "summary_recovery_source": str(summary_source.relative_to(root)),
        "valid_selection_candidates": [
            {"path": str(path.relative_to(root)), "sha256": digest}
            for path, _, digest in valid_selection
        ],
        "rejected_selection_candidates": rejected_selection,
        "valid_summary_candidates": [
            {"path": str(path.relative_to(root)), "sha256": digest}
            for path, digest in valid_summary
        ],
        "rejected_summary_candidates": rejected_summary,
        "next_gate": "REBUILD_PROTECTED_WINDOW_OFF_AXIS_SUMMARY",
        "claim_boundary": (
            "This recovers superseded historical inputs after a wrapper sequencing "
            "defect. It does not change the corrected protected-window geometry."
        ),
    }
    audit_path = root / "data/real/E3_PROTECTED_WINDOW_HISTORY_RECOVERY.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("E3 PROTECTED-WINDOW HISTORY RECOVERY: PASS")
    print("Selection source:", audit["selection_recovery_source"])
    print("Stable selection:", audit["stable_selection_path"])
    print("Summary source:", audit["summary_recovery_source"])
    print("Stable summary:", audit["stable_summary_path"])
    print("Historical sector:", expected_sector)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
