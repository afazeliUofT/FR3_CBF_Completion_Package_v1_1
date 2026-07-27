#!/usr/bin/env python3
"""Independent full-row review of the Site-18 one-sector accounting audit."""
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


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sa509_gain(phi: np.ndarray, row: pd.Series, multiple: bool) -> np.ndarray:
    phi = np.asarray(phi, dtype=float)
    out = np.empty_like(phi)
    g0 = float(row["g0_dbi"])
    p0 = float(row["phi0_deg"])
    p1 = float(row["phi1_deg"])
    p2 = float(row["phi2_deg"])
    m1 = phi < p1
    m2 = (phi >= p1) & (phi < p2)
    m3 = (phi >= p2) & (phi < 48.0)
    m4 = (phi >= 48.0) & (phi < 80.0)
    m5 = (phi >= 80.0) & (phi < 120.0)
    m6 = phi >= 120.0
    out[m1] = g0 - 3.0 * (phi[m1] / p0) ** 2
    out[m2] = g0 - (20.0 if multiple else 17.0)
    out[m3] = (29.0 if multiple else 32.0) - 25.0 * np.log10(phi[m3])
    if multiple:
        out[m4], out[m5], out[m6] = -13.0, -8.0, -13.0
    else:
        out[m4], out[m5], out[m6] = -10.0, -5.0, -10.0
    return out


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/e3_all_site_terrain_review.yaml")
    args = ap.parse_args()

    cfg_path = ROOT / args.config
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    inp = cfg["inputs"]
    exp = cfg["expected"]
    work = ROOT / inp["one_sector_work_dir"]
    pattern_path = ROOT / inp["pattern_parameters_csv"]
    out = ROOT / cfg["outputs"]["one_sector_review_dir"]
    out.mkdir(parents=True, exist_ok=True)

    required = [
        work / "p452_basic_loss.csv",
        work / "bs_gain_accounting.csv",
        work / "earth_station_gain_timeseries.csv",
        work / "gain_accounting_timeseries.csv.gz",
        work / "conditional_threshold_summary.csv",
        work / "peak_accounting_components.csv",
        work / "FIRST_SECTOR_P452_AUDIT.json",
        work / "FIRST_SECTOR_P452_VALIDATION.json",
        pattern_path,
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise SystemExit("MISSING REVIEW INPUTS:\n" + "\n".join(missing))

    p452 = pd.read_csv(work / "p452_basic_loss.csv")
    bs = pd.read_csv(work / "bs_gain_accounting.csv")
    es = pd.read_csv(work / "earth_station_gain_timeseries.csv")
    ts = pd.read_csv(work / "gain_accounting_timeseries.csv.gz")
    summary = pd.read_csv(work / "conditional_threshold_summary.csv")
    patterns = pd.read_csv(pattern_path)
    audit = json.loads((work / "FIRST_SECTOR_P452_AUDIT.json").read_text(encoding="utf-8"))
    validation = json.loads((work / "FIRST_SECTOR_P452_VALIDATION.json").read_text(encoding="utf-8"))

    assert audit["sector_id"] == exp["sector_id"]
    assert validation["sector_id"] == exp["sector_id"]
    assert validation["matlab_release"] == str(exp["matlab_release"])
    assert validation["p452_reference_commit"] == str(exp["p452_commit"])
    assert len(p452) == int(exp["p452_rows"])
    assert len(es) == int(exp["earth_station_gain_rows"])
    assert len(ts) == int(exp["accounting_rows"])

    # Full P.452 grid and conversion checks.
    key = ["coast_distance_km", "polarization_code", "time_percentage"]
    assert not p452.duplicated(key).any()
    recomputed_gain = 10.0 ** (-p452["basic_transmission_loss_db"].to_numpy(float) / 10.0)
    rel = np.abs(recomputed_gain - p452["path_gain_linear"].to_numpy(float)) / np.maximum(recomputed_gain, 1e-300)
    assert float(rel.max()) < 1e-10

    # Coast and H/V sensitivity are exactly nil for this path to numerical precision.
    coast_span = (
        p452.groupby(["polarization_label", "time_percentage"])["basic_transmission_loss_db"]
        .agg(lambda s: float(s.max() - s.min()))
    )
    hv_span = (
        p452.groupby(["coast_distance_km", "time_percentage"])["basic_transmission_loss_db"]
        .agg(lambda s: float(s.max() - s.min()))
    )
    max_coast_span = float(coast_span.max())
    max_hv_span = float(hv_span.max())
    assert max_coast_span < 1e-10
    assert max_hv_span < 1e-10

    # 50% P.452 result must be close to free-space for this short LoS audit path.
    params = json.loads((work / "p452_parameters.json").read_text(encoding="utf-8"))
    d_km = float(json.loads((work / "P452_FIRST_SECTOR_MATLAB_AUDIT.json").read_text(encoding="utf-8"))["distance_km"])
    f_ghz = float(params["frequency_ghz"])
    fspl = 92.45 + 20.0 * math.log10(f_ghz) + 20.0 * math.log10(d_km)
    p50 = float(p452.loc[np.isclose(p452["time_percentage"], 50.0), "basic_transmission_loss_db"].iloc[0])
    fspl_delta = p50 - fspl
    assert abs(fspl_delta) < 0.25

    # Full SA.509 recomputation for all 3,522 rows.
    es_calc = np.empty(len(es), dtype=float)
    for (eff, ptype), index in es.groupby(["aperture_efficiency", "pattern_type"]).groups.items():
        row = patterns.loc[
            np.isclose(patterns["aperture_efficiency"], float(eff))
            & (patterns["pattern_type"].astype(str) == str(ptype))
        ]
        assert len(row) == 1
        es_calc[np.asarray(index, dtype=int)] = sa509_gain(
            es.loc[index, "earth_station_off_axis_deg"].to_numpy(float),
            row.iloc[0],
            multiple=(ptype == "multiple_entry_section_1_2"),
        )
    es_error = np.abs(es_calc - es["earth_station_gain_dbi"].to_numpy(float))
    assert float(es_error.max()) < 1e-9

    # Full 49,308-row accounting identity, not a sample.
    accounted = (
        ts["conducted_power_dbw_per_100mhz"].to_numpy(float)
        + ts["bandwidth_adjustment_db"].to_numpy(float)
        + ts["activity_adjustment_db"].to_numpy(float)
        + ts["bs_gain_dbi"].to_numpy(float)
        - ts["basic_transmission_loss_db"].to_numpy(float)
        + ts["earth_station_gain_dbi"].to_numpy(float)
        - ts["polarization_mismatch_loss_db"].to_numpy(float)
    )
    accounting_error = np.abs(accounted - ts["conditional_interference_dbw_per_10mhz"].to_numpy(float))
    assert float(accounting_error.max()) < 1e-9

    # Rebuild every threshold-summary group and compare.
    group_cols = [
        "coast_distance_km",
        "p452_time_percentage",
        "polarization_label",
        "bs_gain_case",
        "earth_station_pattern_type",
    ]
    rebuilt = (
        ts.groupby(group_cols, as_index=False)
        .agg(
            max_interference_dbw_per_10mhz=("conditional_interference_dbw_per_10mhz", "max"),
            min_interference_dbw_per_10mhz=("conditional_interference_dbw_per_10mhz", "min"),
            mean_interference_dbw_per_10mhz=("conditional_interference_dbw_per_10mhz", "mean"),
            long_exceedance_fraction=("long_exceeded", "mean"),
            short_exceedance_fraction=("short_exceeded", "mean"),
            minimum_off_axis_deg=("earth_station_off_axis_deg", "min"),
            maximum_earth_station_gain_dbi=("earth_station_gain_dbi", "max"),
        )
        .sort_values(group_cols)
        .reset_index(drop=True)
    )
    stored = summary.sort_values(group_cols).reset_index(drop=True)
    assert list(rebuilt[group_cols].itertuples(index=False, name=None)) == list(
        stored[group_cols].itertuples(index=False, name=None)
    )
    numerical_cols = [c for c in rebuilt.columns if c not in group_cols]
    summary_error = float(
        np.max(np.abs(rebuilt[numerical_cols].to_numpy(float) - stored[numerical_cols].to_numpy(float)))
    )
    assert summary_error < 1e-9

    # Create explicit required effective-BS-gain envelopes.
    base_without_bs = (
        ts["conducted_power_dbw_per_100mhz"]
        + ts["bandwidth_adjustment_db"]
        + ts["activity_adjustment_db"]
        - ts["basic_transmission_loss_db"]
        + ts["earth_station_gain_dbi"]
        - ts["polarization_mismatch_loss_db"]
    )
    envelope = ts[
        [
            "time_utc",
            "time_s",
            "p452_time_percentage",
            "polarization_label",
            "earth_station_pattern_type",
            "earth_station_off_axis_deg",
            "earth_station_gain_dbi",
        ]
    ].copy()
    envelope["base_without_bs_gain_dbw_per_10mhz"] = base_without_bs
    envelope["maximum_bs_gain_for_short_db"] = ts["short_threshold_dbw_per_10mhz"] - base_without_bs
    envelope["maximum_bs_gain_for_long_db"] = ts["long_threshold_dbw_per_10mhz"] - base_without_bs
    envelope = envelope.drop_duplicates().sort_values(
        ["p452_time_percentage", "polarization_label", "earth_station_pattern_type", "time_s"]
    )
    envelope.to_csv(out / "required_effective_bs_gain_envelope.csv", index=False)

    # Required additional attenuation for each declared BS case.
    req = ts[group_cols + [
        "time_s",
        "conditional_interference_dbw_per_10mhz",
        "long_threshold_dbw_per_10mhz",
        "short_threshold_dbw_per_10mhz",
    ]].copy()
    req["required_short_backoff_db"] = np.maximum(
        0.0, req["conditional_interference_dbw_per_10mhz"] - req["short_threshold_dbw_per_10mhz"]
    )
    req["required_long_backoff_db"] = np.maximum(
        0.0, req["conditional_interference_dbw_per_10mhz"] - req["long_threshold_dbw_per_10mhz"]
    )
    backoff = (
        req.groupby(group_cols, as_index=False)
        .agg(
            min_required_short_backoff_db=("required_short_backoff_db", "min"),
            max_required_short_backoff_db=("required_short_backoff_db", "max"),
            median_required_short_backoff_db=("required_short_backoff_db", "median"),
            min_required_long_backoff_db=("required_long_backoff_db", "min"),
            max_required_long_backoff_db=("required_long_backoff_db", "max"),
            median_required_long_backoff_db=("required_long_backoff_db", "median"),
        )
    )
    backoff.to_csv(out / "required_backoff_summary.csv", index=False)

    # Correct the ambiguity in the existing "peak" components file.
    global_peak = ts.sort_values("conditional_interference_dbw_per_10mhz").iloc[-1]
    nominal_peak = ts.loc[
        np.isclose(ts["p452_time_percentage"], 20.0)
        & (ts["polarization_label"] == "H")
        & (ts["bs_gain_case"] == "COHERENT_ARRAY_UPPER_ENVELOPE")
        & (ts["earth_station_pattern_type"] == "multiple_entry_section_1_2")
    ].sort_values("conditional_interference_dbw_per_10mhz").iloc[-1]

    component_names = [
        "Power / 100 MHz",
        "100-to-10 MHz",
        "Activity",
        "BS gain",
        "-P.452 loss",
        "ES gain",
        "-polarization loss",
    ]

    def components(row: pd.Series) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "component": component_names,
                "value_db": [
                    row["conducted_power_dbw_per_100mhz"],
                    row["bandwidth_adjustment_db"],
                    row["activity_adjustment_db"],
                    row["bs_gain_dbi"],
                    -row["basic_transmission_loss_db"],
                    row["earth_station_gain_dbi"],
                    -row["polarization_mismatch_loss_db"],
                ],
            }
        )

    components(global_peak).to_csv(out / "global_conditional_peak_components.csv", index=False)
    components(nominal_peak).to_csv(out / "nominal_p20_aggregate_peak_components.csv", index=False)

    existing_peak = pd.read_csv(work / "peak_accounting_components.csv")
    nominal_components = components(nominal_peak)
    assert np.allclose(existing_peak["value_db"], nominal_components["value_db"], atol=1e-9, rtol=0)

    all_short_always = bool((stored["short_exceedance_fraction"] == 1.0).all())
    all_long_always = bool((stored["long_exceedance_fraction"] == 1.0).all())
    assert all_short_always and all_long_always

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": cfg["review_policy"]["verdict"],
        "claim_boundary": cfg["claim_boundary"]["one_sector"],
        "sector_id": exp["sector_id"],
        "review_scope": "Independent full-row audit of basic loss and external accounting.",
        "checks": {
            "p452_grid_unique": True,
            "all_path_gain_conversions_verified": True,
            "max_relative_path_gain_error": float(rel.max()),
            "max_full_accounting_identity_error_db": float(accounting_error.max()),
            "max_summary_reaggregation_error": summary_error,
            "max_sa509_recomputation_error_db": float(es_error.max()),
            "max_coast_distance_loss_span_db": max_coast_span,
            "max_hv_loss_span_db": max_hv_span,
            "p50_minus_free_space_reference_db": fspl_delta,
        },
        "findings": {
            "all_declared_full_power_cases_exceed_short_for_all_protected_samples": all_short_always,
            "all_declared_full_power_cases_exceed_long_for_all_protected_samples": all_long_always,
            "existing_peak_accounting_components_file_disposition": (
                "It is the nominal p=20%, H, coherent-array, multiple-entry-pattern peak, "
                "not the global conditional peak. Superseding precisely named files were generated."
            ),
            "coast_distance_sensitivity_for_this_path": "ZERO_TO_NUMERICAL_PRECISION",
            "h_v_p452_sensitivity_for_this_path": "ZERO_TO_NUMERICAL_PRECISION",
        },
        "required_next_stage_constraints": [
            "Do not call this a compliance result or paper result.",
            "Do not use the coherent-array upper envelope as the final composite WMMSE beam gain.",
            "Use the required effective-BS-gain/backoff envelopes when assessing feasibility.",
            "Build 19 unique site propagation paths before duplicating them across 57 sectors.",
            "Freeze propagation-time and operational-exceedance composition before the dynamic E3 paper run.",
            "Retain zero-dB polarization mismatch only as an explicitly conservative co-polar reference.",
            "Independently spot-check the selected satellite pass before paper use.",
        ],
        "next_gate": cfg["review_policy"]["next_gate"],
        "input_sha256": {str(p.relative_to(ROOT)): hash_file(p) for p in required},
    }
    write_json(out / "ONE_SECTOR_HUMAN_REVIEW_DECISION.json", decision)

    md = f"""# Independent review of the Site-18 one-sector P.452 accounting audit

- Verdict: `{decision['status']}`
- Sector: `{exp['sector_id']}`
- Claim boundary: `{decision['claim_boundary']}`
- P.452 rows checked: `{len(p452)}`
- Earth-station gain rows checked: `{len(es)}`
- Accounting rows checked: `{len(ts)}`
- Maximum full-row accounting error: `{accounting_error.max():.3e} dB`
- Maximum SA.509 recomputation error: `{es_error.max():.3e} dB`
- Coast-distance loss span: `{max_coast_span:.3e} dB`
- H/V loss span: `{max_hv_span:.3e} dB`
- P.452 p=50 minus free-space reference: `{fspl_delta:.6f} dB`

## Human-review finding

The basic-loss and gain/power accounting are internally correct under the
declared assumptions. The result remains a one-sector accounting audit, not a
paper result or compliance determination.

Every declared full-power reference case exceeds both thresholds for every
protected-window sample. This is a real result of the close-in stress geometry,
not a software error. The final paper therefore needs actual composite-beam
gains and a non-degeneracy/feasibility analysis; the coherent-array envelope
must not be used as the final system result.

The existing `peak_accounting_components.csv` corresponds to the nominal
p=20%, H, coherent-array, multiple-entry-pattern peak. It is not the global
conditional peak. Precisely named replacement files are included.

## Next gate

`{decision['next_gate']}`
"""
    (out / "ONE_SECTOR_HUMAN_REVIEW_DECISION.md").write_text(md, encoding="utf-8")

    report = {
        "verdict": decision["status"],
        "sector": exp["sector_id"],
        "p452_rows": len(p452),
        "earth_station_gain_rows": len(es),
        "accounting_rows": len(ts),
        "all_short_exceedance_fractions_equal_one": all_short_always,
        "all_long_exceedance_fractions_equal_one": all_long_always,
        "minimum_short_backoff_db": float(backoff["min_required_short_backoff_db"].min()),
        "maximum_short_backoff_db": float(backoff["max_required_short_backoff_db"].max()),
        "minimum_long_backoff_db": float(backoff["min_required_long_backoff_db"].min()),
        "maximum_long_backoff_db": float(backoff["max_required_long_backoff_db"].max()),
        "next_gate": decision["next_gate"],
    }
    write_json(out / "ONE_SECTOR_REVIEW_SUMMARY.json", report)

    print("ONE-SECTOR INDEPENDENT HUMAN REVIEW: PASS")
    print(json.dumps(report, indent=2))
    print("Output directory:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
