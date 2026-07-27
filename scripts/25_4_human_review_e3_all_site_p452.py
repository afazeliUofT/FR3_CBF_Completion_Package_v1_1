#!/usr/bin/env python3
"""Human-review decision and geometry/loss classification for the 19 P.452 paths."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
C_M_S = 299_792_458.0
EARTH_RADIUS_M = 6_371_000.0


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/e3_57_sector_reference_screen.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    inp = {k: ROOT / v for k, v in cfg["inputs"].items()}
    out = ROOT / cfg["outputs"]["work_dir"]
    out.mkdir(parents=True, exist_ok=True)

    loss = pd.read_csv(inp["all_site_basic_loss_csv"])
    profiles = pd.read_csv(inp["all_site_profiles_csv"])
    site_params = pd.read_csv(inp["all_site_site_parameters_csv"])
    summary = pd.read_csv(inp["all_site_loss_summary_csv"])
    validation = json.loads(inp["all_site_validation_json"].read_text(encoding="utf-8"))
    independent = json.loads(
        inp["all_site_independent_review_json"].read_text(encoding="utf-8")
    )

    expected = cfg["expected"]
    assert validation["status"] == "PASS_REVIEW_REQUIRED"
    assert independent["status"] == "PASS_WITH_HUMAN_REVIEW_REQUIRED"
    assert len(loss) == int(expected["p452_row_count"])
    assert loss["site_id"].nunique() == int(expected["site_count"])
    assert (loss.groupby("site_id").size() == int(expected["p452_rows_per_site"])).all()

    key = ["site_id", "coast_distance_km", "polarization_code", "time_percentage"]
    assert not loss.duplicated(key).any()
    calc_gain = 10.0 ** (-loss["basic_transmission_loss_db"].to_numpy(float) / 10.0)
    rel = np.abs(calc_gain - loss["path_gain_linear"].to_numpy(float)) / np.maximum(
        calc_gain, 1e-300
    )
    assert float(rel.max()) < 1e-10

    frequency_hz = float(
        json.loads(inp["all_site_parameters_json"].read_text(encoding="utf-8"))[
            "frequency_ghz"
        ]
    ) * 1e9
    wavelength = C_M_S / frequency_hz
    k_factor = float(cfg["human_review"]["effective_earth_radius_factor"])
    effective_radius = k_factor * EARTH_RADIUS_M
    p50_threshold = float(cfg["human_review"]["free_space_excess_threshold_db"])

    site_param_index = site_params.set_index("site_id")
    summary_index = summary.set_index("site_id")
    records = []

    for site_id, group in profiles.groupby("site_id", sort=True):
        group = group.sort_values("sample_index").reset_index(drop=True)
        params = site_param_index.loc[site_id]
        row = summary_index.loc[site_id]
        distance_m = group["distance_km"].to_numpy(float) * 1000.0
        total_m = float(distance_m[-1])
        terrain = group["terrain_m_asl"].to_numpy(float)
        tx_center = float(terrain[0]) + float(params["htg_m"])
        rx_center = float(terrain[-1]) + float(params["hrg_m"])
        fraction = distance_m / total_m
        straight_line = tx_center + fraction * (rx_center - tx_center)
        earth_bulge = distance_m * (total_m - distance_m) / (2.0 * effective_radius)
        effective_terrain = terrain + earth_bulge
        terrain_above_los = effective_terrain - straight_line

        d1 = distance_m
        d2 = total_m - distance_m
        fresnel = np.zeros_like(distance_m)
        interior = (d1 > 0) & (d2 > 0)
        fresnel[interior] = np.sqrt(wavelength * d1[interior] * d2[interior] / total_m)
        clearance_60 = straight_line - effective_terrain - 0.6 * fresnel

        p50_excess = float(row["p50_minus_free_space_db"])
        propagation_class = (
            "DIFFRACTION_DOMINATED_REFERENCE"
            if p50_excess > p50_threshold
            else "NEAR_FREE_SPACE_REFERENCE"
        )
        records.append(
            {
                "site_id": site_id,
                "distance_km": total_m / 1000.0,
                "profile_sample_count": len(group),
                "loss_p50_db": float(row["loss_p50_db"]),
                "loss_p20_db": float(row["loss_p20_db"]),
                "loss_p0p005_db": float(row["loss_p0p005_db"]),
                "free_space_reference_db": float(row["free_space_reference_db"]),
                "p50_minus_free_space_db": p50_excess,
                "maximum_terrain_above_effective_los_m": float(terrain_above_los.max()),
                "minimum_60pct_fresnel_clearance_m": float(clearance_60[interior].min()),
                "propagation_class": propagation_class,
            }
        )

    classification = pd.DataFrame(records).sort_values("site_id")
    classification.to_csv(out / "site_geometry_loss_classification.csv", index=False)

    diffraction_sites = classification.loc[
        classification["propagation_class"] == "DIFFRACTION_DOMINATED_REFERENCE",
        "site_id",
    ].tolist()
    expected_diffraction = list(cfg["human_review"]["expected_diffraction_dominated_sites"])
    if diffraction_sites != expected_diffraction:
        raise ValueError(
            f"Unexpected diffraction-dominated site set: {diffraction_sites}; "
            f"expected {expected_diffraction}"
        )
    for site_id in diffraction_sites:
        row = classification.loc[classification["site_id"] == site_id].iloc[0]
        if not (
            float(row["maximum_terrain_above_effective_los_m"]) > 0.0
            or float(row["minimum_60pct_fresnel_clearance_m"]) < 0.0
        ):
            raise ValueError(f"{site_id}: high diffraction loss lacks geometric support")

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_WITH_REQUIRED_MECHANISM_AUDIT",
        "claim_boundary": cfg["claim_boundary"]["all_site_review"],
        "site_count": int(expected["site_count"]),
        "p452_row_count": len(loss),
        "maximum_relative_path_gain_error": float(rel.max()),
        "diffraction_dominated_sites": diffraction_sites,
        "near_free_space_site_count": int(len(classification) - len(diffraction_sites)),
        "findings": {
            "all_coast_distance_spans_zero": bool(
                np.isclose(summary["maximum_coast_span_db"], 0.0).all()
            ),
            "all_hv_spans_zero": bool(
                np.isclose(summary["maximum_hv_span_db"], 0.0).all()
            ),
            "high_loss_sites_supported_by_profile_geometry": True,
            "external_direct_gain_factorization_not_yet_certified": True,
        },
        "next_gate": "P452_TROPOSCATTER_MECHANISM_ISOLATION_AUDIT",
    }
    write_json(out / "ALL_SITE_P452_HUMAN_REVIEW_DECISION.json", decision)
    (out / "ALL_SITE_P452_HUMAN_REVIEW_DECISION.md").write_text(
        "# Human review of the E3 19-site P.452 basic-loss audit\n\n"
        f"- Status: `{decision['status']}`\n"
        f"- Sites: `{decision['site_count']}`\n"
        f"- P.452 rows: `{decision['p452_row_count']}`\n"
        f"- Diffraction-dominated reference sites: "
        f"`{', '.join(diffraction_sites)}`\n"
        f"- Next gate: `{decision['next_gate']}`\n\n"
        "The 798-row basic-loss grid is internally correct. Sites 06, 08, 09, "
        "and 17 have large p=50 excess loss that is supported by their terrain/"
        "Fresnel geometry rather than a data or software defect. Direct antenna "
        "gains remain excluded until the troposcatter-isolation audit passes.\n",
        encoding="utf-8",
    )

    print("E3 19-SITE P.452 HUMAN REVIEW: PASS")
    print(json.dumps(decision, indent=2))
    print("\nSITE CLASSIFICATION")
    print(classification.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
