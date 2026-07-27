#!/usr/bin/env python3
"""Validate and summarize the 19-site P.452 basic-loss audit."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def free_space_loss_db(frequency_ghz: float, distance_km: np.ndarray) -> np.ndarray:
    return 92.45 + 20.0 * np.log10(frequency_ghz) + 20.0 * np.log10(distance_km)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/e3_all_site_p452.yaml")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["outputs"]["work_dir"]
    review = ROOT / cfg["outputs"]["review_dir"]
    review.mkdir(parents=True, exist_ok=True)

    loss = pd.read_csv(work / "p452_all_site_basic_loss.csv")
    coupling = pd.read_csv(work / "p452_all_site_coupling_export.csv")
    site_params = pd.read_csv(work / "p452_all_site_site_parameters.csv")
    params = json.loads(
        (work / "p452_all_site_parameters.json").read_text(encoding="utf-8")
    )
    matlab_audit = json.loads(
        (work / "P452_ALL_SITE_MATLAB_AUDIT.json").read_text(encoding="utf-8")
    )

    expected_rows = int(params["expected_output_row_count"])
    expected_sites = int(cfg["expected"]["site_count"])
    if matlab_audit.get("status") != "PASS":
        raise ValueError("MATLAB audit did not pass")
    if matlab_audit["matlab_release"] != str(cfg["expected"]["matlab_release"]):
        raise ValueError("Unexpected MATLAB release")
    if matlab_audit["p452_reference_commit"] != str(
        cfg["expected"]["p452_reference_commit"]
    ):
        raise ValueError("Unexpected P.452 commit")
    if len(loss) != expected_rows or len(coupling) != expected_rows:
        raise ValueError("Unexpected all-site P.452 row count")
    if loss["site_id"].nunique() != expected_sites:
        raise ValueError("Expected 19 unique sites")
    if not (loss.groupby("site_id").size() == 42).all():
        raise ValueError("Every site must contain exactly 42 sensitivity rows")

    key = [
        "site_id",
        "coast_distance_km",
        "polarization_code",
        "time_percentage",
    ]
    if loss.duplicated(key).any():
        raise ValueError("Duplicate P.452 sensitivity row")

    calculated_gain = 10.0 ** (
        -loss["basic_transmission_loss_db"].to_numpy(float) / 10.0
    )
    stored_gain = loss["path_gain_linear"].to_numpy(float)
    relative_error = np.abs(calculated_gain - stored_gain) / np.maximum(
        calculated_gain, 1e-300
    )
    if float(relative_error.max()) >= 1e-10:
        raise ValueError("Path-gain conversion failed")

    if not np.isfinite(loss["basic_transmission_loss_db"]).all():
        raise ValueError("Non-finite basic loss")
    if (loss["basic_transmission_loss_db"] <= 0).any():
        raise ValueError("Nonpositive basic loss")

    nominal_coast = float(cfg["propagation"]["nominal_coast_distance_km"])
    nominal = loss.loc[
        np.isclose(loss["coast_distance_km"], nominal_coast)
        & (loss["polarization_label"] == "H")
    ].copy()

    pivot = nominal.pivot(
        index="site_id",
        columns="time_percentage",
        values="basic_transmission_loss_db",
    )
    required_p = [50.0, 20.0, 0.005]
    for value in required_p:
        if value not in pivot.columns:
            raise ValueError(f"Missing p={value}")

    site_summary = site_params[
        ["site_id", "distance_km", "profile_sample_count"]
    ].copy()
    site_summary = site_summary.merge(
        pivot[required_p].rename(
            columns={
                50.0: "loss_p50_db",
                20.0: "loss_p20_db",
                0.005: "loss_p0p005_db",
            }
        ),
        on="site_id",
        how="left",
        validate="one_to_one",
    )

    fspl = free_space_loss_db(
        float(cfg["propagation"]["frequency_ghz"]),
        site_summary["distance_km"].to_numpy(float),
    )
    site_summary["free_space_reference_db"] = fspl
    site_summary["p50_minus_free_space_db"] = (
        site_summary["loss_p50_db"] - site_summary["free_space_reference_db"]
    )

    coast_span = (
        loss.groupby(["site_id", "polarization_label", "time_percentage"])[
            "basic_transmission_loss_db"
        ]
        .agg(lambda values: float(values.max() - values.min()))
        .groupby("site_id")
        .max()
    )
    hv_span = (
        loss.groupby(["site_id", "coast_distance_km", "time_percentage"])[
            "basic_transmission_loss_db"
        ]
        .agg(lambda values: float(values.max() - values.min()))
        .groupby("site_id")
        .max()
    )
    site_summary["maximum_coast_span_db"] = site_summary["site_id"].map(coast_span)
    site_summary["maximum_hv_span_db"] = site_summary["site_id"].map(hv_span)

    if (site_summary["p50_minus_free_space_db"] < -0.5).any():
        bad = site_summary.loc[
            site_summary["p50_minus_free_space_db"] < -0.5,
            ["site_id", "p50_minus_free_space_db"],
        ]
        raise ValueError(f"Implausible p50/free-space result:\n{bad}")

    site_summary_path = work / "all_site_loss_summary.csv"
    site_summary.to_csv(site_summary_path, index=False)

    # Review plots.
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(
        site_summary["distance_km"],
        site_summary["loss_p50_db"],
        label="P.452 p=50%",
    )
    ax.scatter(
        site_summary["distance_km"],
        site_summary["loss_p20_db"],
        label="P.452 p=20%",
    )
    ax.plot(
        site_summary["distance_km"],
        site_summary["free_space_reference_db"],
        linestyle="--",
        label="free-space reference",
    )
    for _, row in site_summary.iterrows():
        ax.annotate(
            row["site_id"].replace("E3_SITE_", ""),
            (row["distance_km"], row["loss_p20_db"]),
            fontsize=7,
        )
    ax.set_xlabel("Site-to-station distance (km)")
    ax.set_ylabel("Basic transmission loss (dB)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_title("E3 19-site P.452 basic-loss audit")
    fig.tight_layout()
    fig.savefig(review / "all_site_loss_vs_distance.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ordered = site_summary.sort_values("site_id")
    x = np.arange(len(ordered))
    ax.plot(x, ordered["loss_p50_db"], marker="o", label="p=50%")
    ax.plot(x, ordered["loss_p20_db"], marker="o", label="p=20%")
    ax.plot(x, ordered["loss_p0p005_db"], marker="o", label="p=0.005%")
    ax.set_xticks(x)
    ax.set_xticklabels(ordered["site_id"], rotation=60, ha="right", fontsize=7)
    ax.set_ylabel("Basic transmission loss (dB)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_title("P.452 time-percentage sensitivity by modelled site")
    fig.tight_layout()
    fig.savefig(review / "all_site_loss_by_site.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(
        ordered["site_id"],
        ordered["maximum_coast_span_db"],
        label="coast-distance span",
    )
    ax.bar(
        ordered["site_id"],
        ordered["maximum_hv_span_db"],
        alpha=0.6,
        label="H/V span",
    )
    ax.tick_params(axis="x", rotation=60, labelsize=7)
    ax.set_ylabel("Maximum loss span (dB)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    ax.set_title("All-site P.452 model-sensitivity spans")
    fig.tight_layout()
    fig.savefig(review / "all_site_p452_sensitivity_spans.png", dpi=180)
    plt.close(fig)

    validation = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"]["p452"],
        "site_count": expected_sites,
        "p452_row_count": len(loss),
        "coupling_export_row_count": len(coupling),
        "maximum_relative_path_gain_error": float(relative_error.max()),
        "basic_loss_min_db": float(loss["basic_transmission_loss_db"].min()),
        "basic_loss_max_db": float(loss["basic_transmission_loss_db"].max()),
        "p50_minus_free_space_min_db": float(
            site_summary["p50_minus_free_space_db"].min()
        ),
        "p50_minus_free_space_max_db": float(
            site_summary["p50_minus_free_space_db"].max()
        ),
        "maximum_coast_span_db": float(
            site_summary["maximum_coast_span_db"].max()
        ),
        "maximum_hv_span_db": float(site_summary["maximum_hv_span_db"].max()),
        "zero_terminal_horizon_gains_inside_p452_verified": True,
        "no_separate_p2108_baseline_verified": True,
        "direct_antenna_gains_not_included": True,
        "review_required": True,
        "next_gate": cfg["review"]["next_gate"],
    }
    write_json(work / "ALL_SITE_P452_VALIDATION.json", validation)
    (work / "ALL_SITE_P452_VALIDATION.md").write_text(
        "# E3 all-site P.452 basic-loss validation\n\n"
        f"- Status: `{validation['status']}`\n"
        f"- Unique sites: `{expected_sites}`\n"
        f"- P.452 rows: `{len(loss)}`\n"
        f"- Basic-loss range: `{validation['basic_loss_min_db']:.6f}` to "
        f"`{validation['basic_loss_max_db']:.6f}` dB\n"
        f"- Maximum coast-distance span: "
        f"`{validation['maximum_coast_span_db']:.6e}` dB\n"
        f"- Maximum H/V span: `{validation['maximum_hv_span_db']:.6e}` dB\n"
        f"- Next gate: `{validation['next_gate']}`\n\n"
        "This is a 19-site basic-loss audit. No sector beam gain, earth-station "
        "tracking gain, aggregate network interference, controller action, or "
        "paper/compliance claim has been produced.\n",
        encoding="utf-8",
    )

    print("E3 ALL-SITE P.452 BASIC-LOSS VALIDATION: PASS")
    print(json.dumps(validation, indent=2))
    print("\nSITE SUMMARY")
    print(site_summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
