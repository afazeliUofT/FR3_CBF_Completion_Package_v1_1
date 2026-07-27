#!/usr/bin/env python3
"""Validate the 19-site terrain profiles and classify QC flags."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/e3_all_site_terrain_review.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    out_cfg = cfg["outputs"]
    root = ROOT / out_cfg["all_site_root"]
    summary_path = ROOT / out_cfg["all_site_terrain_dir"] / "terrain_summary.csv"
    profiles_path = ROOT / out_cfg["all_site_terrain_dir"] / "terrain_profile_samples.csv.gz"
    audit_path = ROOT / out_cfg["all_site_terrain_dir"] / "TERRAIN_AUDIT.json"
    links_path = ROOT / out_cfg["all_site_links_with_terrain_csv"]
    pdf_path = ROOT / out_cfg["all_site_review_pdf"]

    for path in [summary_path, profiles_path, audit_path, links_path, pdf_path]:
        if not path.is_file():
            raise FileNotFoundError(path)

    summary = pd.read_csv(summary_path)
    profiles = pd.read_csv(profiles_path)
    links = pd.read_csv(links_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    expected = int(cfg["expected"]["site_count"])
    assert len(summary) == expected
    assert len(links) == expected
    assert summary["link_id"].astype(str).nunique() == expected
    assert links["link_id"].astype(str).nunique() == expected
    assert set(summary["link_id"].astype(str)) == set(links["link_id"].astype(str))
    assert set(profiles["link_id"].astype(str)) == set(summary["link_id"].astype(str))
    assert int(audit["link_count"]) == expected

    blocking = []
    nonblocking = []
    allowed = set(cfg["terrain"]["allowed_nonblocking_flags"])
    for _, row in summary.iterrows():
        if float(row["tx_implied_antenna_height_agl_m"]) <= 0:
            blocking.append((row["link_id"], "tx_antenna_not_above_ground"))
        if float(row["rx_implied_antenna_height_agl_m"]) <= 0:
            blocking.append((row["link_id"], "rx_antenna_not_above_ground"))
        raw = row.get("qc_flags", "")
        flags = [] if pd.isna(raw) or not str(raw).strip() else [
            item.strip() for item in str(raw).split("|") if item.strip()
        ]
        for flag in flags:
            if flag in allowed:
                nonblocking.append((str(row["link_id"]), flag))
            else:
                blocking.append((str(row["link_id"]), flag))

    profiles = profiles.sort_values(["link_id", "distance_from_tx_m"]).reset_index(drop=True)
    profiles.to_csv(root / "terrain_profile_samples_review.csv", index=False)

    qc_rows = []
    for link_id, group in profiles.groupby("link_id", sort=True):
        group = group.sort_values("distance_from_tx_m")
        dx = group["distance_from_tx_m"].astype(float).diff().dropna()
        dz = group["elevation_m_asl"].astype(float).diff().dropna()
        slopes = (dz / dx).replace([float("inf"), float("-inf")], float("nan")).dropna()
        qc_rows.append(
            {
                "link_id": str(link_id),
                "sample_count": int(len(group)),
                "distance_km": float(group["distance_from_tx_m"].iloc[-1]) / 1000.0,
                "minimum_elevation_m_asl": float(group["elevation_m_asl"].min()),
                "maximum_elevation_m_asl": float(group["elevation_m_asl"].max()),
                "maximum_absolute_adjacent_step_m": float(dz.abs().max()) if len(dz) else 0.0,
                "maximum_absolute_segment_slope": float(slopes.abs().max()) if len(slopes) else 0.0,
                "start_elevation_m_asl": float(group["elevation_m_asl"].iloc[0]),
                "end_elevation_m_asl": float(group["elevation_m_asl"].iloc[-1]),
            }
        )
    qc_metrics = pd.DataFrame(qc_rows)
    qc_metrics.to_csv(root / "all_site_profile_qc_metrics.csv", index=False)

    counts = profiles.groupby("link_id").size()
    stored_counts = summary.set_index("link_id")["total_sample_count"].astype(int)
    for link_id, count in counts.items():
        if int(count) != int(stored_counts.loc[link_id]):
            blocking.append((str(link_id), "profile_sample_count_mismatch"))

    if blocking:
        status = "BLOCKING_REVIEW_REQUIRED"
    else:
        status = "REVIEW_REQUIRED"

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "claim_boundary": cfg["claim_boundary"]["all_site_terrain"],
        "site_count": expected,
        "total_profile_samples": int(len(profiles)),
        "distance_km_min": float(summary["distance_km_wgs84"].min()),
        "distance_km_max": float(summary["distance_km_wgs84"].max()),
        "terrain_min_m_asl": float(summary["min_profile_terrain_m_asl"].min()),
        "terrain_max_m_asl": float(summary["max_profile_terrain_m_asl"].max()),
        "blocking_flags": [{"site_id": s, "flag": f} for s, f in blocking],
        "nonblocking_flags": [{"site_id": s, "flag": f} for s, f in nonblocking],
        "review_pdf": str(pdf_path.relative_to(ROOT)),
        "uncompressed_profile_review_csv": str(
            (root / "terrain_profile_samples_review.csv").relative_to(ROOT)
        ),
        "profile_qc_metrics_csv": str(
            (root / "all_site_profile_qc_metrics.csv").relative_to(ROOT)
        ),
        "maximum_absolute_adjacent_step_m": float(
            qc_metrics["maximum_absolute_adjacent_step_m"].max()
        ),
        "maximum_absolute_segment_slope": float(
            qc_metrics["maximum_absolute_segment_slope"].max()
        ),
        "next_gate": (
            "MANUAL_REVIEW_OF_ALL_19_SITE_TERRAIN_PROFILES"
            if not blocking
            else "RESOLVE_BLOCKING_ALL_SITE_TERRAIN_FLAGS"
        ),
    }
    write_json(root / "ALL_SITE_TERRAIN_REVIEW_AUDIT.json", decision)
    (root / "ALL_SITE_TERRAIN_REVIEW_AUDIT.md").write_text(
        "# E3 all-site terrain review\n\n"
        f"- Status: `{status}`\n"
        f"- Unique site paths: `{expected}`\n"
        f"- Total profile samples: `{len(profiles)}`\n"
        f"- Distance range: `{decision['distance_km_min']:.6f}` to `{decision['distance_km_max']:.6f}` km\n"
        f"- Blocking flags: `{len(blocking)}`\n"
        f"- Nonblocking flags: `{len(nonblocking)}`\n"
        f"- Next gate: `{decision['next_gate']}`\n\n"
        "These are terrain/profile inputs only. No all-site P.452 or paper result "
        "has been produced.\n",
        encoding="utf-8",
    )

    print("E3 ALL-SITE TERRAIN VALIDATION:", "PASS" if not blocking else "FAIL")
    print(json.dumps(decision, indent=2))
    return 0 if not blocking else 2


if __name__ == "__main__":
    raise SystemExit(main())
