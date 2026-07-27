#!/usr/bin/env python3
"""Freeze the 19 reviewed terrain profiles after explicit human confirmation."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def split_flags(value: object) -> list[str]:
    if pd.isna(value) or not str(value).strip():
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_all_site_p452.yaml")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()

    cfg_path = ROOT / args.config
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    inp = {key: ROOT / value for key, value in cfg["inputs"].items()}
    expected = cfg["expected"]

    expected_phrase = str(expected["manual_confirmation_phrase"])
    if args.confirmation != expected_phrase:
        raise SystemExit(
            "FAIL: confirmation phrase does not match. Expected exactly: "
            f"{expected_phrase}"
        )
    reviewer = args.reviewer.strip()
    if len(reviewer) < 2:
        raise SystemExit("FAIL: reviewer name is empty")

    required = [
        inp["terrain_summary_csv"],
        inp["terrain_profiles_csv_gz"],
        inp["terrain_audit_json"],
        inp["terrain_review_audit_json"],
        inp["terrain_review_pdf"],
        inp["site_links_with_terrain_csv"],
        inp["earth_station_csv"],
        inp["bs_sites_csv"],
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    summary = pd.read_csv(inp["terrain_summary_csv"])
    profiles = pd.read_csv(inp["terrain_profiles_csv_gz"])
    links = pd.read_csv(inp["site_links_with_terrain_csv"])
    sites = pd.read_csv(inp["bs_sites_csv"])
    station = pd.read_csv(inp["earth_station_csv"])
    terrain_audit = json.loads(inp["terrain_audit_json"].read_text(encoding="utf-8"))
    review_audit = json.loads(
        inp["terrain_review_audit_json"].read_text(encoding="utf-8")
    )

    site_count = int(expected["site_count"])
    if len(summary) != site_count or len(links) != site_count or len(sites) != site_count:
        raise ValueError("Expected exactly 19 terrain/link/site rows")
    if len(station) != 1:
        raise ValueError("Expected exactly one earth-station row")
    if len(profiles) != int(expected["terrain_profile_sample_count"]):
        raise ValueError(
            f"Expected {expected['terrain_profile_sample_count']} profile samples; "
            f"found {len(profiles)}"
        )
    if review_audit.get("blocking_flags"):
        raise ValueError(f"Blocking terrain flags remain: {review_audit['blocking_flags']}")
    if review_audit.get("status") != "REVIEW_REQUIRED":
        raise ValueError("Unexpected pre-freeze terrain-review status")

    identifiers = set(summary["link_id"].astype(str))
    if identifiers != set(links["link_id"].astype(str)):
        raise ValueError("Summary/link site identifiers differ")
    if identifiers != set(sites["site_id"].astype(str)):
        raise ValueError("Summary/site identifiers differ")
    if identifiers != set(profiles["link_id"].astype(str)):
        raise ValueError("Profile/site identifiers differ")

    allowed = set(cfg["terrain"]["allowed_nonblocking_flags"])
    blocking: list[dict[str, str]] = []
    retained: list[dict[str, str]] = []
    site_records: list[dict[str, object]] = []

    profile_counts = profiles.groupby("link_id").size()
    for _, row in summary.sort_values("link_id").iterrows():
        site_id = str(row["link_id"])
        flags = split_flags(row.get("qc_flags", ""))
        for flag in flags:
            if flag in allowed:
                retained.append({"site_id": site_id, "flag": flag})
            else:
                blocking.append({"site_id": site_id, "flag": flag})
        tx_agl = float(row["tx_implied_antenna_height_agl_m"])
        rx_agl = float(row["rx_implied_antenna_height_agl_m"])
        if tx_agl <= 0:
            blocking.append({"site_id": site_id, "flag": "tx_not_above_ground"})
        if rx_agl <= 0:
            blocking.append({"site_id": site_id, "flag": "rx_not_above_ground"})
        if int(profile_counts.loc[site_id]) != int(row["total_sample_count"]):
            blocking.append({"site_id": site_id, "flag": "profile_count_mismatch"})
        site_records.append(
            {
                "site_id": site_id,
                "distance_km": float(row["distance_km_wgs84"]),
                "profile_sample_count": int(row["total_sample_count"]),
                "tx_height_agl_m": tx_agl,
                "rx_height_agl_m": rx_agl,
                "minimum_terrain_m_asl": float(row["min_profile_terrain_m_asl"]),
                "maximum_terrain_m_asl": float(row["max_profile_terrain_m_asl"]),
                "inclusive_minus_interior_m": float(
                    row["inclusive_minus_interior_m"]
                ),
                "retained_flags": flags,
            }
        )

    if blocking:
        raise ValueError(f"Blocking terrain problems remain: {blocking}")

    distances = summary["distance_km_wgs84"].to_numpy(float)
    if not np.all(
        (distances >= float(expected["distance_km_min"]))
        & (distances <= float(expected["distance_km_max"]))
    ):
        raise ValueError("A site distance is outside the frozen layout range")
    if not np.allclose(
        summary["tx_implied_antenna_height_agl_m"].to_numpy(float),
        float(expected["tx_height_agl_m"]),
        atol=1e-8,
        rtol=0,
    ):
        raise ValueError("Not all site TX heights are 25 m AGL")
    if not np.allclose(
        summary["rx_implied_antenna_height_agl_m"].to_numpy(float),
        float(expected["rx_height_agl_m"]),
        atol=1e-8,
        rtol=0,
    ):
        raise ValueError("Not all station RX heights are 20 m AGL")

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN_FOR_19_SITE_P452_BASIC_LOSS_AUDIT",
        "claim_boundary": cfg["claim_boundary"]["terrain"],
        "reviewer": reviewer,
        "manual_confirmation": args.confirmation,
        "visual_review_statement": (
            "Reviewer explicitly confirmed review of every page in the 19-page "
            "terrain-profile PDF."
        ),
        "site_count": site_count,
        "total_profile_samples": int(len(profiles)),
        "retained_nonblocking_flags": retained,
        "blocking_flags": [],
        "site_records": site_records,
        "profile_rule": (
            "P.452 uses each complete sampled terrain profile. The inclusive "
            "and interior scalar terrain means are retained only as audit data."
        ),
        "input_sha256": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in required
        },
        "next_gate": "ALL_SITE_P452_BASIC_LOSS_AUDIT",
    }
    out_root = ROOT / cfg["outputs"]["work_dir"]
    out_root.mkdir(parents=True, exist_ok=True)
    write_json(out_root / "ALL_SITE_TERRAIN_DECISION.json", decision)
    (out_root / "ALL_SITE_TERRAIN_DECISION.md").write_text(
        "# E3 all-site terrain decision\n\n"
        f"- Status: `{decision['status']}`\n"
        f"- Reviewer: `{reviewer}`\n"
        f"- Unique paths: `{site_count}`\n"
        f"- Profile samples: `{len(profiles)}`\n"
        f"- Retained nonblocking flags: `{len(retained)}`\n"
        f"- Next gate: `{decision['next_gate']}`\n\n"
        "All 19 terrain profiles were explicitly reviewed. The only retained "
        "flags are documented inclusive-versus-interior arithmetic-mean "
        "differences. The complete profiles, not those scalar means, are used "
        "by P.452.\n",
        encoding="utf-8",
    )

    print("E3 ALL-SITE TERRAIN FREEZE: PASS")
    print("Reviewer:", reviewer)
    print("Sites:", site_count)
    print("Total profile samples:", len(profiles))
    print("Retained nonblocking flags:", len(retained))
    print("Output:", out_root / "ALL_SITE_TERRAIN_DECISION.json")
    print("Next gate:", decision["next_gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
