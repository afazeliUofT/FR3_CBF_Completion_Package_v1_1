#!/usr/bin/env python3
"""Independent all-row review of the 19-site P.452 basic-loss audit."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, obj: object) -> None:
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_all_site_p452.yaml")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["outputs"]["work_dir"]
    all_site = pd.read_csv(work / "p452_all_site_basic_loss.csv")
    coupling = pd.read_csv(work / "p452_all_site_coupling_export.csv")
    validation = json.loads(
        (work / "ALL_SITE_P452_VALIDATION.json").read_text(encoding="utf-8")
    )
    prior = pd.read_csv(
        ROOT / "data/real/e3_first_sector_p452/p452_basic_loss.csv"
    )

    expected_sites = int(cfg["expected"]["site_count"])
    expected_rows = expected_sites * 7 * 2 * 3

    assert validation["status"] == "PASS_REVIEW_REQUIRED"
    assert len(all_site) == expected_rows == 798
    assert len(coupling) == expected_rows
    assert all_site["site_id"].nunique() == expected_sites
    assert (all_site.groupby("site_id").size() == 42).all()

    key = [
        "site_id",
        "coast_distance_km",
        "polarization_code",
        "time_percentage",
    ]
    assert not all_site.duplicated(key).any()

    recomputed = 10.0 ** (
        -all_site["basic_transmission_loss_db"].to_numpy(float) / 10.0
    )
    stored = all_site["path_gain_linear"].to_numpy(float)
    relative_error = np.abs(recomputed - stored) / np.maximum(
        recomputed, 1e-300
    )
    assert float(relative_error.max()) < 1e-10

    # Loss must be nondecreasing with p within each site/coast/polarization.
    monotonic_failures = []
    for group_key, group in all_site.groupby(
        ["site_id", "coast_distance_km", "polarization_code"]
    ):
        ordered = group.sort_values("time_percentage")
        loss = ordered["basic_transmission_loss_db"].to_numpy(float)
        if np.any(np.diff(loss) < -1e-9):
            monotonic_failures.append(group_key)
    assert not monotonic_failures, monotonic_failures

    # Regression: Site 18 must exactly reproduce the accepted one-sector grid.
    site18 = all_site.loc[all_site["site_id"] == "E3_SITE_18"].copy()
    compare_cols = [
        "coast_distance_km",
        "polarization_code",
        "polarization_label",
        "time_percentage",
        "basic_transmission_loss_db",
        "path_gain_linear",
    ]
    site18 = site18[compare_cols].sort_values(compare_cols[:4]).reset_index(
        drop=True
    )
    prior = prior[compare_cols].sort_values(compare_cols[:4]).reset_index(
        drop=True
    )
    assert len(site18) == len(prior) == 42
    assert (
        site18[compare_cols[:4]].astype(str).to_numpy()
        == prior[compare_cols[:4]].astype(str).to_numpy()
    ).all()
    loss_error = float(
        np.max(
            np.abs(
                site18["basic_transmission_loss_db"].to_numpy(float)
                - prior["basic_transmission_loss_db"].to_numpy(float)
            )
        )
    )
    gain_error = float(
        np.max(
            np.abs(
                site18["path_gain_linear"].to_numpy(float)
                - prior["path_gain_linear"].to_numpy(float)
            )
        )
    )
    assert loss_error < 1e-10
    assert gain_error < 1e-20

    # Coupling export must retain zero external gain accounting.
    assert set(
        coupling["element_gain_accounted"].astype(str).str.lower()
    ) <= {"false", "0"}
    assert np.allclose(
        coupling["receiver_gain_linear"].to_numpy(float), 1.0
    )
    assert coupling["provenance_note"].str.contains(
        "ALL_SITE_BASIC_LOSS_AUDIT_NOT_PAPER_RESULT",
        regex=False,
    ).all()

    review = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_WITH_HUMAN_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"]["p452"],
        "site_count": expected_sites,
        "p452_row_count": len(all_site),
        "coupling_row_count": len(coupling),
        "maximum_relative_path_gain_error": float(relative_error.max()),
        "monotonic_time_percentage_check": True,
        "site18_regression_loss_error_db": loss_error,
        "site18_regression_gain_error": gain_error,
        "zero_external_gain_inside_export_verified": True,
        "review_required": True,
        "next_gate": cfg["review"]["next_gate"],
    }
    write_json(work / "ALL_SITE_P452_INDEPENDENT_REVIEW.json", review)
    (work / "ALL_SITE_P452_INDEPENDENT_REVIEW.md").write_text(
        "# Independent E3 19-site P.452 review\n\n"
        f"- Status: `{review['status']}`\n"
        f"- Sites: `{expected_sites}`\n"
        f"- Rows: `{len(all_site)}`\n"
        f"- Maximum path-gain relative error: "
        f"`{review['maximum_relative_path_gain_error']:.3e}`\n"
        f"- Site-18 regression loss error: `{loss_error:.3e}` dB\n"
        f"- Site-18 regression gain error: `{gain_error:.3e}`\n"
        f"- Next gate: `{review['next_gate']}`\n\n"
        "This remains a site-level basic-loss audit. It does not include final "
        "sector beam gains, tracking earth-station gain expansion, aggregate "
        "interference, controller action, paper result, or compliance claim.\n",
        encoding="utf-8",
    )

    print("E3 ALL-SITE P.452 INDEPENDENT REVIEW: PASS")
    print(json.dumps(review, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
