#!/usr/bin/env python3
"""Audit fairness and freeze a constrained-PF policy before controller work."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    extras = sorted(
        {
            key
            for row in rows
            for key in row
            if key not in fieldnames
        }
    )
    fieldnames.extend(extras)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rate_metrics(rate: np.ndarray, epsilon: float) -> dict[str, float]:
    x = np.asarray(rate, dtype=float)
    if x.ndim != 1 or np.any(~np.isfinite(x)) or np.any(x < 0):
        raise ValueError("rate vector is invalid")
    denominator = len(x) * float(np.sum(x * x))
    jain = float(np.sum(x) ** 2 / denominator) if denominator > 0 else 0.0
    log_value = np.log(x + epsilon)
    return {
        "sum_rate_bps_hz": float(np.sum(x)),
        "proportional_fair_utility": float(np.sum(log_value)),
        "mean_log_utility_per_user": float(np.mean(log_value)),
        "geometric_mean_rate_bps_hz": float(
            np.exp(np.mean(log_value)) - epsilon
        ),
        "jain_fairness_index": jain,
        "minimum_rate_bps_hz": float(np.min(x)),
        "p01_rate_bps_hz": float(np.quantile(x, 0.01)),
        "p05_rate_bps_hz": float(np.quantile(x, 0.05)),
        "p10_rate_bps_hz": float(np.quantile(x, 0.10)),
        "median_rate_bps_hz": float(np.quantile(x, 0.50)),
        "maximum_rate_bps_hz": float(np.max(x)),
    }


def group_metrics(
    users: pd.DataFrame,
    rate: np.ndarray,
    epsilon: float,
) -> list[dict[str, object]]:
    rows = []
    indoor = users["indoor"].astype(bool).to_numpy()
    for group, mask in [
        ("all", np.ones(len(users), dtype=bool)),
        ("indoor", indoor),
        ("outdoor", ~indoor),
    ]:
        metrics = rate_metrics(np.asarray(rate)[mask], epsilon)
        rows.append(
            {
                "group": group,
                "user_count": int(mask.sum()),
                **metrics,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/fairness_policy_audit_v1.json",
    )
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()

    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    data = (
        Path(args.data_root).expanduser().resolve()
        if args.data_root
        else (ROOT / cfg["data_root"]).resolve()
    )
    results = ROOT / cfg["paths"]["results_dir"]
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    for path in [results, evidence]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    required = [
        "USER_TOPOLOGY.csv",
        "nominal_total_weighted_rate_per_user.npy",
        "nominal_protected_rate_per_user.npy",
        "common_scale_user_rate.npy",
        "frequency_weights.npy",
        "other_frequency_weighted_rate_per_user.npy",
        "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json",
    ]
    for name in required:
        if not (data / name).is_file():
            raise FileNotFoundError(data / name)

    validation = json.loads(
        (data / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json").read_text(
            encoding="utf-8"
        )
    )
    if validation["status"] != (
        "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
    ):
        raise ValueError("full-topology data are not V4 validated")

    users = pd.read_csv(data / "USER_TOPOLOGY.csv")
    nominal_total = np.load(
        data / "nominal_total_weighted_rate_per_user.npy"
    ).astype(float)
    nominal_protected = np.load(
        data / "nominal_protected_rate_per_user.npy"
    ).astype(float)
    common_total = np.load(
        data / "common_scale_user_rate.npy"
    ).astype(float)
    weights = np.load(data / "frequency_weights.npy").astype(float)
    other = np.load(
        data / "other_frequency_weighted_rate_per_user.npy"
    ).astype(float)

    if len(users) != 228 or common_total.shape != (587, 228):
        raise ValueError("unexpected user or common-rate dimensions")
    if not np.isclose(weights.sum(), 1.0, rtol=0.0, atol=1e-14):
        raise ValueError("frequency weights do not sum to one")

    protected_weight = float(weights[4])
    common_protected = (
        common_total - other[None, :]
    ) / protected_weight
    common_total_worst = common_total.min(axis=0)
    common_protected_worst = common_protected.min(axis=0)
    epsilon = float(cfg["pf_epsilon_bps_hz"])
    indoor_mask = users["indoor"].astype(bool).to_numpy()

    group_rows = []
    for scenario, rate in [
        ("nominal_total_band", nominal_total),
        ("common_scale_worst_total_band", common_total_worst),
        ("nominal_protected_band", nominal_protected),
        ("common_scale_worst_protected_band", common_protected_worst),
    ]:
        for row in group_metrics(users, rate, epsilon):
            group_rows.append({"scenario": scenario, **row})
    write_csv(results / "FAIRNESS_GROUP_METRICS.csv", group_rows)

    threshold_rows = []
    for threshold in cfg["serviceability_thresholds_bps_hz"]:
        threshold = float(threshold)
        eligible = nominal_total >= threshold
        for relative_floor in cfg["relative_floor_fractions"]:
            relative_floor = float(relative_floor)
            floor = np.maximum(
                threshold,
                relative_floor * nominal_total,
            )
            violation = eligible & (common_total_worst < floor)
            shortfall = np.maximum(
                0.0,
                floor - common_total_worst,
            )
            normalized_shortfall = np.zeros_like(shortfall)
            normalized_shortfall[eligible] = (
                shortfall[eligible] / floor[eligible]
            )
            threshold_rows.append(
                {
                    "serviceability_threshold_bps_hz": threshold,
                    "relative_floor_fraction": relative_floor,
                    "eligible_user_count": int(eligible.sum()),
                    "coverage_limited_user_count": int((~eligible).sum()),
                    "coverage_limited_indoor_count": int(
                        ((~eligible) & indoor_mask).sum()
                    ),
                    "coverage_limited_outdoor_count": int(
                        ((~eligible) & (~indoor_mask)).sum()
                    ),
                    "common_scale_controller_induced_floor_violation_count": int(
                        violation.sum()
                    ),
                    "common_scale_indoor_floor_violation_count": int(
                        (violation & indoor_mask).sum()
                    ),
                    "common_scale_outdoor_floor_violation_count": int(
                        (violation & (~indoor_mask)).sum()
                    ),
                    "total_normalized_floor_shortfall": float(
                        normalized_shortfall.sum()
                    ),
                    "maximum_normalized_floor_shortfall": float(
                        normalized_shortfall.max()
                    ),
                }
            )
    write_csv(results / "FAIRNESS_FLOOR_SENSITIVITY.csv", threshold_rows)

    absolute_threshold_rows = []
    for threshold in [0.01, 0.05, 0.1, 0.25, 0.5, 1.0]:
        for scenario, rate in [
            ("nominal_total_band", nominal_total),
            ("common_scale_worst_total_band", common_total_worst),
            ("nominal_protected_band", nominal_protected),
            ("common_scale_worst_protected_band", common_protected_worst),
        ]:
            below = np.asarray(rate) < threshold
            absolute_threshold_rows.append(
                {
                    "scenario": scenario,
                    "absolute_rate_threshold_bps_hz": threshold,
                    "below_threshold_count": int(below.sum()),
                    "below_threshold_indoor_count": int(
                        (below & indoor_mask).sum()
                    ),
                    "below_threshold_outdoor_count": int(
                        (below & (~indoor_mask)).sum()
                    ),
                }
            )
    write_csv(
        results / "ABSOLUTE_RATE_OUTAGE_COUNTS.csv",
        absolute_threshold_rows,
    )

    nominal_indoor_median = float(
        np.median(nominal_total[indoor_mask])
    )
    nominal_outdoor_median = float(
        np.median(nominal_total[~indoor_mask])
    )
    ordering_flag = nominal_indoor_median > nominal_outdoor_median

    primary = cfg["primary_policy"]
    primary_threshold = float(
        primary["serviceability_threshold_bps_hz"]
    )
    primary_relative = float(
        primary["relative_total_band_floor_fraction"]
    )
    primary_row = next(
        row
        for row in threshold_rows
        if math.isclose(
            row["serviceability_threshold_bps_hz"],
            primary_threshold,
        )
        and math.isclose(
            row["relative_floor_fraction"],
            primary_relative,
        )
    )

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_FAIRNESS_POLICY_AUDIT_REVIEW_REQUIRED",
        "claim_boundary": cfg["claim_boundary"],
        "data_validation_status": validation["status"],
        "user_counts": {
            "total": 228,
            "indoor": int(indoor_mask.sum()),
            "outdoor": int((~indoor_mask).sum()),
        },
        "nominal_total_band": rate_metrics(
            nominal_total,
            epsilon,
        ),
        "common_scale_worst_total_band": rate_metrics(
            common_total_worst,
            epsilon,
        ),
        "nominal_protected_band": rate_metrics(
            nominal_protected,
            epsilon,
        ),
        "common_scale_worst_protected_band": rate_metrics(
            common_protected_worst,
            epsilon,
        ),
        "indoor_outdoor_audit": {
            "sionna_boolean_interpretation_used": (
                "True=indoor, False=outdoor"
            ),
            "nominal_indoor_median_bps_hz": nominal_indoor_median,
            "nominal_outdoor_median_bps_hz": nominal_outdoor_median,
            "indoor_median_exceeds_outdoor_median": ordering_flag,
            "interpretation": (
                "Do not assign an indoor-specific optimization bonus from "
                "this one seed. Report groups separately and perform a "
                "multi-seed O2I/association audit before class weighting."
            ),
        },
        "primary_policy": primary,
        "primary_policy_common_scale_check": primary_row,
        "conclusions": [
            "The controller objective must not be network sum rate.",
            "Proportional fairness is appropriate as a utility objective but does not guarantee a nonzero rate.",
            "Coverage-limited users must be separated from controller-induced outages.",
            "Eligible users require an explicit total-band service floor in addition to PF utility.",
            "Protected-band rate and total-band rate must be reported separately.",
            "Indoor and outdoor metrics must be stratified; no indoor class weight is frozen from one seed."
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(results / "FAIRNESS_POLICY_AUDIT.json", audit)

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_CONSTRAINED_PF_POLICY_FROZEN_FOR_ONE_SEED_CONTROLLER_MILESTONE",
        "paper_result": False,
        "sum_rate_primary_objective": False,
        "primary_utility": "proportional_fair_sum_log",
        "explicit_service_floor": True,
        "coverage_limited_users_reported_separately": True,
        "indoor_outdoor_metrics_required": True,
        "indoor_class_weight_frozen": False,
        "primary_serviceability_threshold_bps_hz": primary_threshold,
        "primary_relative_floor_fraction": primary_relative,
        "primary_absolute_floor_bps_hz": float(
            primary["absolute_total_band_floor_bps_hz"]
        ),
        "next_gate": cfg["next_gate"],
    }
    write_json(evidence / "FAIRNESS_POLICY_DECISION.json", decision)
    write_json(evidence / "FAIRNESS_POLICY_AUDIT.json", audit)
    for name in [
        "FAIRNESS_GROUP_METRICS.csv",
        "FAIRNESS_FLOOR_SENSITIVITY.csv",
        "ABSOLUTE_RATE_OUTAGE_COUNTS.csv",
    ]:
        shutil.copy2(results / name, evidence / name)

    (evidence / "README.md").write_text(
        "# Fairness policy audit\n\n"
        "The primary controller objective is constrained proportional "
        "fairness, not network sum rate. Users below the declared nominal "
        "serviceability threshold are reported as coverage-limited; they "
        "are not hidden inside the controller objective. For eligible users, "
        "the controller must first avoid service-floor violations and "
        "shortfall, then maximize PF utility. Indoor and outdoor users are "
        "reported separately, but no indoor-specific weight is assigned from "
        "this one seed.\n",
        encoding="utf-8",
    )

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(
                f"{sha256_file(path)}  {path.as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("FR3 FAIRNESS POLICY AUDIT: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
