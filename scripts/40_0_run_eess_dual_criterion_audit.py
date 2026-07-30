#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def qstats(x: np.ndarray) -> dict[str, float]:
    return {
        k: float(v)
        for k, v in zip(
            ["minimum", "p05", "median", "p95", "maximum"],
            np.quantile(np.asarray(x, dtype=float), [0, 0.05, 0.5, 0.95, 1]),
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/eess_dual_criterion_audit_v1.json")
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))

    inputs = cfg["input_paths"]
    static_path = ROOT / inputs["static_accounting"]
    full = ROOT / inputs["full_output"]
    pattern_params_path = ROOT / inputs["pattern_parameters"]
    pattern_samples_path = ROOT / inputs["pattern_samples"]
    pattern_summary_path = ROOT / inputs["protected_pattern_summary"]
    export_cfg_path = ROOT / inputs["export_config"]
    regulatory_path = ROOT / inputs["regulatory_constants"]

    for p in [
        static_path,
        full / "kappa_time_sector.npy",
        full / "nominal_mode_leakage_w.npy",
        full / "nominal_aggregate_interference_w.npy",
        full / "aggregate_allowance_w.npy",
        full / "common_scale_reference.npy",
        full / "protected_time_s.npy",
        full / "SECTOR_TOPOLOGY.csv",
        pattern_params_path,
        pattern_samples_path,
        pattern_summary_path,
        export_cfg_path,
        regulatory_path,
    ]:
        if not p.is_file():
            raise FileNotFoundError(p)

    export_cfg = json.loads(export_cfg_path.read_text(encoding="utf-8"))
    if export_cfg["p452_time_percentage"] != 20.0:
        raise ValueError("The historical export did not use p=20%")
    if export_cfg["short_threshold_dbw_per_10mhz"] != -133.0:
        raise ValueError("The historical export threshold was not -133 dBW/10 MHz")
    if export_cfg["earth_station_pattern_type"] != "multiple_entry_section_1_2":
        raise ValueError("The historical export pattern was not SA.509 multiple-entry")

    regulatory_text = regulatory_path.read_text(encoding="utf-8")
    for token in [
        "threshold_dbw_per_10mhz: -150.0",
        "time_percentage_exceeded: 20.0",
        "threshold_dbw_per_10mhz: -133.0",
        "time_percentage_exceeded: 0.005",
    ]:
        if token not in regulatory_text:
            raise ValueError(f"Regulatory source-of-truth token missing: {token}")

    static = pd.read_csv(static_path)
    selected = static.loc[
        (static["polarization_label"] == "H")
        & (static["bs_gain_case"] == "ELEMENT_PATTERN_REFERENCE")
    ].copy()
    pivot = selected.pivot(
        index="sector_id",
        columns="p452_time_percentage",
        values="basic_transmission_loss_db",
    ).sort_index()
    for p in [20.0, 0.005]:
        if p not in pivot.columns:
            raise ValueError(f"Static accounting lacks p={p}")

    sector_table = pd.read_csv(full / "SECTOR_TOPOLOGY.csv").sort_values("bs_index")
    if len(sector_table) != 57:
        raise ValueError("Expected 57 sectors")
    sector_ids = sector_table["sector_id"].astype(str).tolist()
    if set(sector_ids) != set(pivot.index.astype(str)):
        raise ValueError("Static accounting and full-topology sector IDs differ")

    loss20 = np.asarray([pivot.loc[s, 20.0] for s in sector_ids], dtype=float)
    loss0005 = np.asarray([pivot.loc[s, 0.005] for s in sector_ids], dtype=float)
    rare_gain_db = loss20 - loss0005
    if np.any(rare_gain_db <= 0):
        raise ValueError("p=0.005 must have lower basic loss than p=20")

    kappa20_multiple = np.load(full / "kappa_time_sector.npy")
    leakage = np.load(full / "nominal_mode_leakage_w.npy")
    nominal20_multiple = np.load(full / "nominal_aggregate_interference_w.npy")
    historical_allowance = np.load(full / "aggregate_allowance_w.npy")
    historical_scale = np.load(full / "common_scale_reference.npy")
    time_s = np.load(full / "protected_time_s.npy")
    if kappa20_multiple.shape != (587, 57) or leakage.shape != (57, 2):
        raise ValueError("Unexpected coupling/leakage dimensions")
    reconstructed = kappa20_multiple @ leakage.sum(axis=1)
    if not np.allclose(reconstructed, nominal20_multiple, rtol=1e-12, atol=1e-24):
        raise ValueError("Historical nominal aggregate does not reconstruct")

    # SA.509 sensitivity. All protected off-axis angles are far beyond phi2,
    # where the single-entry and multiple-entry envelopes differ by exactly 3 dB.
    params = pd.read_csv(pattern_params_path)
    summary = pd.read_csv(pattern_summary_path)
    min_off_axis = float(summary["minimum_off_axis_deg_during_protected_window"].min())
    max_phi2 = float(params["phi2_deg"].max())
    if not min_off_axis > max_phi2:
        raise ValueError("Protected window enters a non-constant SA.509 difference region")
    samples = pd.read_csv(pattern_samples_path)
    # Verify the +3 dB relation over every tabulated off-axis point >= min protected angle.
    single = samples.loc[
        (samples["pattern_type"] == "single_entry_section_1_1")
        & np.isclose(samples["aperture_efficiency"], 0.65)
    ].sort_values("off_axis_deg")
    multiple = samples.loc[
        (samples["pattern_type"] == "multiple_entry_section_1_2")
        & np.isclose(samples["aperture_efficiency"], 0.65)
    ].sort_values("off_axis_deg")
    merged = single.merge(multiple, on="off_axis_deg", suffixes=("_single", "_multiple"))
    protected_region = merged.loc[merged["off_axis_deg"] >= min_off_axis]
    pattern_delta = (
        protected_region["gain_dbi_single"] - protected_region["gain_dbi_multiple"]
    ).to_numpy()
    if not np.allclose(pattern_delta, 3.0, rtol=0.0, atol=1e-12):
        raise ValueError("SA.509 single/multiple difference is not exactly 3 dB in protected region")

    p_factor = np.power(10.0, rare_gain_db / 10.0)
    single_pattern_factor = np.power(10.0, 3.0 / 10.0)

    kappa_short_multiple = kappa20_multiple * p_factor[None, :]
    kappa_long_multiple = kappa20_multiple.copy()
    kappa_short_single = kappa_short_multiple * single_pattern_factor
    kappa_long_single = kappa_long_multiple * single_pattern_factor

    nominal = {
        "historical_p20_multiple": nominal20_multiple,
        "short_p0005_multiple": kappa_short_multiple @ leakage.sum(axis=1),
        "short_p0005_single": kappa_short_single @ leakage.sum(axis=1),
        "long_p20_multiple": kappa_long_multiple @ leakage.sum(axis=1),
        "long_p20_single": kappa_long_single @ leakage.sum(axis=1),
    }

    short_threshold = 10.0 ** (-133.0 / 10.0)
    long_threshold = 10.0 ** (-150.0 / 10.0)
    thresholds = {
        "historical_p20_multiple": float(historical_allowance[0]),
        "short_p0005_multiple": short_threshold,
        "short_p0005_single": short_threshold,
        "long_p20_multiple": long_threshold,
        "long_p20_single": long_threshold,
    }

    required_q = {
        name: np.maximum(0.0, 10.0 * np.log10(value / thresholds[name]))
        for name, value in nominal.items()
    }
    historical_safe = nominal20_multiple * historical_scale**2
    corrected_excess = {
        "short_p0005_multiple": nominal["short_p0005_multiple"] * historical_scale**2 / short_threshold,
        "short_p0005_single": nominal["short_p0005_single"] * historical_scale**2 / short_threshold,
        "long_p20_multiple": nominal["long_p20_multiple"] * historical_scale**2 / long_threshold,
        "long_p20_single": nominal["long_p20_single"] * historical_scale**2 / long_threshold,
    }

    local_arrays = ROOT / cfg["paths"]["local_arrays"]
    evidence = ROOT / cfg["paths"]["evidence"]
    for p in [local_arrays, evidence]:
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True)

    np.save(local_arrays / "kappa_short_p0005_multiple.npy", kappa_short_multiple)
    np.save(local_arrays / "kappa_short_p0005_single.npy", kappa_short_single)
    np.save(local_arrays / "kappa_long_p20_multiple.npy", kappa_long_multiple)
    np.save(local_arrays / "kappa_long_p20_single.npy", kappa_long_single)
    np.save(local_arrays / "allowance_short_exact_w.npy", np.full(587, short_threshold))
    np.save(local_arrays / "allowance_long_exact_w.npy", np.full(587, long_threshold))

    sector_rows = []
    for idx, sector_id in enumerate(sector_ids):
        sector_rows.append(
            {
                "bs_index": idx,
                "sector_id": sector_id,
                "loss_p20_db": float(loss20[idx]),
                "loss_p0005_db": float(loss0005[idx]),
                "p0005_minus_p20_coupling_db": float(rare_gain_db[idx]),
            }
        )
    write_csv(evidence / "P452_PERCENTILE_SECTOR_DELTAS.csv", sector_rows)

    time_rows = []
    for i, t in enumerate(time_s):
        row = {"time_s": float(t)}
        for name in required_q:
            row[f"{name}_required_attenuation_db"] = float(required_q[name][i])
        for name, ratio in corrected_excess.items():
            row[f"historical_policy_{name}_ratio"] = float(ratio[i])
        time_rows.append(row)
    write_csv(evidence / "EESS_DUAL_CRITERION_TIME_SERIES.csv", time_rows)

    case_results = {}
    for name, q in required_q.items():
        case_results[name] = {
            "required_attenuation_db": qstats(q),
            "samples_above_60db": int(np.sum(q > 60.0)),
            "samples_above_67db": int(np.sum(q > 67.0)),
            "nominal_interference_dbw": qstats(10.0 * np.log10(nominal[name])),
        }
    for name, ratio in corrected_excess.items():
        case_results[name]["historical_policy_exceedance_samples"] = int(np.sum(ratio > 1.0))
        case_results[name]["historical_policy_maximum_excess_db"] = float(
            10.0 * np.log10(np.max(ratio))
        )

    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_EESS_DUAL_CRITERION_DIAGNOSIS",
        "claim_boundary": cfg["claim_boundary"],
        "historical_configuration": {
            "p452_time_percentage": export_cfg["p452_time_percentage"],
            "threshold_dbw_per_10mhz": export_cfg["short_threshold_dbw_per_10mhz"],
            "pattern_type": export_cfg["earth_station_pattern_type"],
            "reserve_fraction": export_cfg["reserve_fraction"],
            "decision": "HYBRID_LONG_TERM_PROPAGATION_WITH_SHORT_TERM_THRESHOLD_NOT_VALID_AS_FINAL_REGULATORY_TEST",
        },
        "corrected_criteria": cfg["criteria"],
        "pattern_policy": {
            **cfg["pattern_policy"],
            "minimum_protected_off_axis_deg": min_off_axis,
            "maximum_phi2_deg": max_phi2,
            "verified_single_minus_multiple_db": 3.0,
        },
        "p452_p0005_minus_p20_coupling_db": qstats(rare_gain_db),
        "case_results": case_results,
        "key_diagnosis": {
            "historical_policy_short_multiple_all_samples_violate": (
                case_results["short_p0005_multiple"]["historical_policy_exceedance_samples"] == 587
            ),
            "historical_policy_long_multiple_all_samples_violate": (
                case_results["long_p20_multiple"]["historical_policy_exceedance_samples"] == 587
            ),
            "current_60db_grid_insufficient_for_long_multiple": (
                case_results["long_p20_multiple"]["samples_above_60db"] > 0
            ),
            "current_60db_grid_insufficient_for_long_single_sensitivity": (
                case_results["long_p20_single"]["samples_above_60db"] > 0
            ),
            "short_term_arrays_can_be_rebuilt_without_new_p452_run": True,
        },
        "uncertainty_evidence_status": {
            "p452_reference_implementation_numeric_error": "VALIDATED_BELOW_1E-6_DB_NOT_A_PHYSICAL_UNCERTAINTY",
            "p452_model_residual": "NOT_CALIBRATABLE_FROM_COLLECTED_PACKAGE",
            "terrain_vertical_error": "PROVENANCE_AVAILABLE_NO_HELD_OUT_ERROR_DISTRIBUTION",
            "earth_station_pattern": "REFERENCE_PATTERN_ONLY_NO_MEASURED_STATION_PATTERN",
            "ephemeris": "ONE_TLE_WITH_0.52_DAY_AGE_NO_INDEPENDENT_TRUTH",
            "array_csi": "NO_HELD_OUT_CALIBRATION_DATA",
            "traffic_message": "SYNTHETIC_STRESS_MODEL_AVAILABLE_NOT_PHYSICAL_CALIBRATION",
        },
        "next_gate": cfg["next_gate"],
    }
    write_json(evidence / "EESS_DUAL_CRITERION_AUDIT.json", audit)
    write_json(
        evidence / "EESS_DUAL_CRITERION_GATE_DECISION.json",
        {
            "created_utc": audit["created_utc"],
            "status": "PASS_REGULATORY_DIAGNOSIS_CONTROLLER_REEVALUATION_REQUIRED",
            "paper_result": False,
            "current_online_controller_results_remain_algorithmic_one_seed_evidence": True,
            "current_online_controller_results_are_regulatory_compliance_evidence": False,
            "new_p452_matlab_run_required": False,
            "new_nibi_channel_generation_required": False,
            "local_controller_rerun_required": True,
            "recommended_provisional_action_grid_max_db": 70,
            "hard_null_endpoint_required": True,
            "next_gate": cfg["next_gate"],
        },
    )

    source_hashes = {
        "static_accounting": sha256_file(static_path),
        "kappa_p20_multiple": sha256_file(full / "kappa_time_sector.npy"),
        "mode_leakage": sha256_file(full / "nominal_mode_leakage_w.npy"),
        "pattern_parameters": sha256_file(pattern_params_path),
        "pattern_samples": sha256_file(pattern_samples_path),
        "protected_pattern_summary": sha256_file(pattern_summary_path),
        "export_config": sha256_file(export_cfg_path),
        "regulatory_constants": sha256_file(regulatory_path),
    }
    write_json(evidence / "SOURCE_HASHES.json", source_hashes)

    readme = f"""# EESS dual-criterion correction audit

Status: `PASS_REGULATORY_DIAGNOSIS_CONTROLLER_REEVALUATION_REQUIRED`

The historical full-topology export combined P.452 p=20% with the -133 dBW/10 MHz
short-term threshold. That hybrid remains useful as algorithmic one-seed
evidence, but it is not the final SA.1027 regulatory test.

Corrected percentile-matched tests:

- long-term terrestrial single-entry criterion: p=20%, -150 dBW/10 MHz;
- short-term terrestrial single-entry criterion: p=0.005%, -133 dBW/10 MHz;
- both must be met.

The all-sector P.452 table already contains p=0.005%, so no new MATLAB/P.452
execution is needed. The next step is a local controller rerun using both
criteria, a provisional 0--70 dB action grid, and a hard-null endpoint. The
SA.509 multiple-entry pattern remains the aggregate-network primary model
decision; the single-entry pattern is a +3 dB protected-window sensitivity.
"""
    (evidence / "README.md").write_text(readme, encoding="utf-8")

    manifest = evidence / "EVIDENCE_MANIFEST.sha256"
    lines = []
    for p in sorted(evidence.rglob("*")):
        if p.is_file() and p != manifest:
            lines.append(f"{sha256_file(p)}  {p.as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("EESS DUAL-CRITERION CORRECTION AUDIT: PASS")
    print(json.dumps(audit, indent=2))
    print("Evidence files:", len(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
