#!/usr/bin/env python3
"""Generate five immutable, uniformly formatted protected-pass records."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import numpy as np
import pandas as pd

from fr3_cbf.protected_pass_records import (
    complete_pass_catalog,
    kappa_from_gain_table,
    parse_utc,
    protected_track,
    select_passes_by_peak_date,
    sha256_file,
    site_gain_table,
    threshold_w,
)

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def first_existing(candidates: list[str], kind: str) -> Path:
    for relative in candidates:
        path = ROOT / relative
        if path.exists():
            return path
    raise FileNotFoundError(
        f"No {kind} candidate exists: {candidates}"
    )


def run_track(
    tle: Path,
    start_utc: datetime,
    duration_s: int,
    step_s: float,
    station: pd.Series,
    engine: str,
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "scripts/06_generate_tle_track.py"),
        "--tle",
        str(tle),
        "--start-utc",
        start_utc.isoformat().replace("+00:00", "Z"),
        "--duration-s",
        str(int(duration_s)),
        "--step-s",
        str(float(step_s)),
        "--station-lat",
        str(float(station["latitude_deg"])),
        "--station-lon",
        str(float(station["longitude_deg"])),
        "--station-alt-m",
        str(float(station["altitude_m_asl"])),
        "--engine",
        str(engine),
        "--output",
        str(output.relative_to(ROOT)),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def manifest_for(directory: Path, exclude: set[str] | None = None) -> Path:
    exclude = exclude or set()
    manifest = directory / "RECORD_MANIFEST.sha256"
    lines = []
    for path in sorted(directory.rglob("*")):
        if (
            path.is_file()
            and path != manifest
            and path.name not in exclude
        ):
            lines.append(
                f"{sha256_file(path)}  "
                f"{path.relative_to(directory).as_posix()}"
            )
    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return manifest


def zip_directory(directory: Path, output: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(
                    path,
                    path.relative_to(directory).as_posix(),
                )
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"Corrupt ZIP member: {bad}")
    digest = sha256_file(output)
    Path(str(output) + ".sha256").write_text(
        f"{digest}  {output.name}\n",
        encoding="utf-8",
    )
    return digest


def build_record(
    slot: int,
    detailed_track_path: Path,
    selection: dict[str, object],
    cfg: dict,
    inputs: dict[str, Path],
    output_root: Path,
    tle_record: dict,
    nominal_mode_leakage: np.ndarray,
    expected_slot0_kappa: np.ndarray | None,
    expected_slot0_time_s: np.ndarray | None,
) -> dict[str, object]:
    record = output_root / f"slot_{slot}"
    if record.exists():
        shutil.rmtree(record)
    record.mkdir(parents=True)

    detailed = pd.read_csv(detailed_track_path)
    protected = protected_track(
        detailed,
        float(cfg["selection_policy"]["minimum_elevation_deg"]),
    )
    station = pd.read_csv(inputs["station"]).iloc[0]
    sites = pd.read_csv(inputs["sites"])
    parameters = pd.read_csv(inputs["pattern_parameters"])
    multiple = parameters.loc[
        np.isclose(
            parameters["aperture_efficiency"],
            float(cfg["criteria"]["aperture_efficiency"]),
        )
        & (
            parameters["pattern_type"]
            == cfg["criteria"]["pattern_primary"]
        )
    ]
    single = parameters.loc[
        np.isclose(
            parameters["aperture_efficiency"],
            float(cfg["criteria"]["aperture_efficiency"]),
        )
        & (
            parameters["pattern_type"]
            == cfg["criteria"]["pattern_sensitivity"]
        )
    ]
    if len(multiple) != 1 or len(single) != 1:
        raise ValueError("nominal SA.509 pattern rows are not unique")

    gain = site_gain_table(
        protected,
        station,
        sites,
        multiple.iloc[0],
        single.iloc[0],
    )
    static = pd.read_csv(inputs["static_accounting"])

    arrays: dict[str, np.ndarray] = {}
    sector_ids: list[str] | None = None
    for criterion, p_value in [
        ("long", cfg["criteria"]["long_term"]["p452_time_percentage"]),
        ("short", cfg["criteria"]["short_term"]["p452_time_percentage"]),
    ]:
        for pattern, gain_column in [
            ("multiple", "gain_multiple_entry_dbi"),
            ("single", "gain_single_entry_dbi"),
        ]:
            value, ids = kappa_from_gain_table(
                gain,
                static,
                float(p_value),
                str(cfg["criteria"]["polarization_label"]),
                str(cfg["criteria"]["bs_gain_case"]),
                gain_column,
            )
            arrays[f"kappa_{criterion}_{pattern}"] = value
            if sector_ids is None:
                sector_ids = ids
            elif sector_ids != ids:
                raise RuntimeError("sector ordering changed")

    if expected_slot0_kappa is not None:
        reconstructed = arrays["kappa_long_multiple"]
        maximum_relative = float(
            np.max(
                np.abs(reconstructed - expected_slot0_kappa)
                / np.maximum(np.abs(expected_slot0_kappa), 1e-300)
            )
        )
        if not np.allclose(
            reconstructed,
            expected_slot0_kappa,
            rtol=2e-12,
            atol=1e-24,
        ):
            raise RuntimeError(
                "slot-0 historical kappa reconstruction failed: "
                f"{maximum_relative}"
            )
        if expected_slot0_time_s is None or not np.array_equal(
            protected["time_s"].to_numpy(float),
            expected_slot0_time_s,
        ):
            raise RuntimeError(
                "slot-0 protected time vector reconstruction failed"
            )
    else:
        maximum_relative = None

    peak_utc = parse_utc(str(selection["peak_utc"]))
    tle_epoch = parse_utc(str(tle_record["tle_epoch_utc"]))
    tle_age_days = (peak_utc - tle_epoch).total_seconds() / 86400.0
    maximum_tle_age = float(tle_record["maximum_tle_age_days"])
    if not (0.0 <= tle_age_days <= maximum_tle_age):
        raise RuntimeError(
            f"slot {slot} TLE age {tle_age_days:.3f} d is invalid"
        )

    long_allowance = threshold_w(
        cfg["criteria"]["long_term"]["threshold_dbw_per_10mhz"]
    )
    short_allowance = threshold_w(
        cfg["criteria"]["short_term"]["threshold_dbw_per_10mhz"]
    )
    np.save(
        record / "protected_time_s.npy",
        protected["time_s"].to_numpy(np.float64),
        allow_pickle=False,
    )
    np.save(
        record / "allowance_long_exact_w.npy",
        np.full(len(protected), long_allowance, dtype=np.float64),
        allow_pickle=False,
    )
    np.save(
        record / "allowance_short_exact_w.npy",
        np.full(len(protected), short_allowance, dtype=np.float64),
        allow_pickle=False,
    )
    for name, value in arrays.items():
        np.save(
            record / f"{name}.npy",
            value.astype(np.float64),
            allow_pickle=False,
        )

    detailed.to_csv(record / "track_1s_with_margin.csv", index=False)
    protected.to_csv(record / "protected_track_1s.csv", index=False)
    gain.to_csv(
        record / "site_gain_timeseries.csv.gz",
        index=False,
        compression="gzip",
    )
    pd.DataFrame({"sector_id": sector_ids}).to_csv(
        record / "sector_order.csv",
        index=False,
    )
    shutil.copy2(inputs["tle"], record / "active_case.tle")
    shutil.copy2(
        inputs["tle_source_record"],
        record / "TLE_SOURCE_RECORD.json",
    )

    summary: dict[str, object] = {}
    mode_power = nominal_mode_leakage.sum(axis=1)
    for name, value in arrays.items():
        aggregate = value @ mode_power
        allowance = (
            long_allowance if "_long_" in f"_{name}_" else short_allowance
        )
        required_db = np.maximum(
            0.0,
            10.0 * np.log10(
                np.maximum(aggregate, 1e-300) / allowance
            ),
        )
        summary[name] = {
            "nominal_aggregate_interference_w_min": float(
                aggregate.min()
            ),
            "nominal_aggregate_interference_w_max": float(
                aggregate.max()
            ),
            "required_common_attenuation_db_min": float(
                required_db.min()
            ),
            "required_common_attenuation_db_median": float(
                np.median(required_db)
            ),
            "required_common_attenuation_db_max": float(
                required_db.max()
            ),
        }

    metadata = {
        "schema_version": 1,
        "slot": slot,
        "status": (
            "CURRENT_VALIDATED_PASS_RECONSTRUCTED"
            if slot == 0
            else "IMMUTABLE_ADDITIONAL_PASS_RECORD_READY"
        ),
        "selection": selection,
        "selection_policy": cfg["selection_policy"],
        "protected_window": {
            "sample_count": int(len(protected)),
            "start_utc": str(protected.iloc[0]["time_utc"]),
            "end_utc": str(protected.iloc[-1]["time_utc"]),
            "minimum_elevation_deg": float(
                protected["elevation_deg"].min()
            ),
            "maximum_elevation_deg": float(
                protected["elevation_deg"].max()
            ),
        },
        "tle": {
            "sha256": sha256_file(inputs["tle"]),
            "recorded_sha256": str(tle_record["tle_sha256"]),
            "epoch_utc": str(tle_record["tle_epoch_utc"]),
            "retrieved_utc": str(tle_record["retrieved_utc"]),
            "age_days_at_peak": tle_age_days,
            "maximum_age_days": maximum_tle_age,
        },
        "criteria": cfg["criteria"],
        "static_accounting_sha256": sha256_file(
            inputs["static_accounting"]
        ),
        "pattern_parameters_sha256": sha256_file(
            inputs["pattern_parameters"]
        ),
        "slot0_historical_kappa_max_relative_error": maximum_relative,
        "nominal_mode_leakage_sha256": hashlib.sha256(
            np.ascontiguousarray(nominal_mode_leakage).tobytes()
        ).hexdigest(),
        "screening_summary": summary,
        "claim_boundary": (
            "Orbit geometry is a model input. Same-TLE pass records provide "
            "temporal geometry diversity, not independent ephemeris-error "
            "calibration or evidence that the public station tracked the "
            "modelled object."
        ),
    }
    write_json(record / "PASS_RECORD_METADATA.json", metadata)
    manifest_for(record)

    record_zip = output_root / f"FR3_PROTECTED_PASS_SLOT_{slot}.zip"
    record_sha = zip_directory(record, record_zip)
    return {
        "slot": slot,
        "status": metadata["status"],
        "record_zip": record_zip.name,
        "record_zip_sha256": record_sha,
        "record_manifest_sha256": sha256_file(
            record / "RECORD_MANIFEST.sha256"
        ),
        "selection": selection,
        "protected_sample_count": int(len(protected)),
        "tle_age_days_at_peak": tle_age_days,
        "tle_sha256": sha256_file(inputs["tle"]),
        "criteria": cfg["criteria"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/protected_pass_records_phase1_v1.json",
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    inputs_cfg = cfg["input_candidates"]
    inputs = {
        name: first_existing(paths, name)
        for name, paths in inputs_cfg.items()
        if name not in {
            "validated_full_output",
            "phase1_candidate_v1",
        }
    }
    full_output = first_existing(
        inputs_cfg["validated_full_output"],
        "validated full output",
    )
    if not full_output.is_dir():
        raise NotADirectoryError(full_output)

    tle_record = json.loads(
        inputs["tle_source_record"].read_text(encoding="utf-8")
    )
    if sha256_file(inputs["tle"]) != str(tle_record["tle_sha256"]):
        raise ValueError("archived TLE hash does not match its source record")

    station = pd.read_csv(inputs["station"]).iloc[0]
    existing_selection = json.loads(
        inputs["existing_pass_selection"].read_text(encoding="utf-8")
    )
    existing_peak = parse_utc(
        str(existing_selection["selected_pass"]["peak_utc"])
    )
    offsets = [
        int(x)
        for x in cfg["selection_policy"][
            "target_day_offsets_from_existing_peak_utc"
        ]
    ]
    target_dates = [
        (existing_peak.date() + timedelta(days=offset)).isoformat()
        for offset in offsets
    ]
    search_start = datetime.combine(
        existing_peak.date() + timedelta(days=min(offsets)),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    search_days = (
        max(offsets)
        - min(offsets)
        + 1
        + int(cfg["selection_policy"]["coarse_search_extra_days"])
    )

    work = ROOT / cfg["paths"]["work_dir"]
    records = ROOT / cfg["paths"]["pass_records_dir"]
    for path in [work, records]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    coarse = work / "coarse_search.csv"
    run_track(
        inputs["tle"],
        search_start,
        search_days * 86400,
        float(cfg["selection_policy"]["coarse_step_s"]),
        station,
        str(cfg["selection_policy"]["orbit_engine"]),
        coarse,
    )
    coarse_frame = pd.read_csv(coarse)
    catalog = complete_pass_catalog(
        coarse_frame,
        float(cfg["selection_policy"]["minimum_elevation_deg"]),
    )
    catalog.to_csv(work / "PASS_CATALOG.csv", index=False)
    selections = select_passes_by_peak_date(catalog, target_dates)

    leakage = np.load(
        full_output / "nominal_mode_leakage_w.npy",
        allow_pickle=False,
    )
    expected_kappa = np.load(
        full_output / "kappa_time_sector.npy",
        allow_pickle=False,
    )
    expected_time = np.load(
        full_output / "protected_time_s.npy",
        allow_pickle=False,
    )

    slot_records: list[dict[str, object]] = []
    slot0_selection = {
        "target_peak_date": existing_peak.date().isoformat(),
        "start_utc": str(
            existing_selection["selected_pass"]["start_utc"]
        ),
        "end_utc": str(existing_selection["selected_pass"]["end_utc"]),
        "peak_utc": str(existing_selection["selected_pass"]["peak_utc"]),
        "maximum_elevation_deg": float(
            existing_selection["detailed_max_elevation_deg"]
        ),
        "duration_s": float(
            existing_selection["selected_pass"]["duration_s"]
        ),
        "selection_rule": "existing independently validated slot-0 pass",
    }
    slot_records.append(
        build_record(
            0,
            inputs["existing_pass_track"],
            slot0_selection,
            cfg,
            inputs,
            records,
            tle_record,
            leakage,
            expected_kappa,
            expected_time,
        )
    )

    margin = int(cfg["selection_policy"]["detailed_margin_s"])
    for slot, selected in enumerate(selections, start=1):
        detailed_start = parse_utc(selected.start_utc) - timedelta(
            seconds=margin
        )
        detailed_end = parse_utc(selected.end_utc) + timedelta(
            seconds=margin
        )
        detailed = work / f"slot_{slot}_track_1s.csv"
        run_track(
            inputs["tle"],
            detailed_start,
            int((detailed_end - detailed_start).total_seconds()),
            float(cfg["selection_policy"]["detailed_step_s"]),
            station,
            str(cfg["selection_policy"]["orbit_engine"]),
            detailed,
        )
        selection = {
            "target_peak_date": selected.target_peak_date,
            "start_utc": selected.start_utc,
            "end_utc": selected.end_utc,
            "peak_utc": selected.peak_utc,
            "maximum_elevation_deg": selected.maximum_elevation_deg,
            "duration_s": selected.duration_s,
            "selection_rule": cfg["selection_policy"]["daily_rule"],
        }
        slot_records.append(
            build_record(
                slot,
                detailed,
                selection,
                cfg,
                inputs,
                records,
                tle_record,
                leakage,
                None,
                None,
            )
        )

    index = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_FIVE_IMMUTABLE_PROTECTED_PASS_RECORDS_READY_FOR_REVIEW",
        "source_commit_required": cfg["required_ancestor_commit"],
        "selection_policy": cfg["selection_policy"],
        "pass_slots": slot_records,
        "all_five_slots_ready": len(slot_records) == 5,
        "campaign_execution_authorized": False,
        "next_gate": cfg["next_gate"],
    }
    write_json(records / "PASS_RECORD_INDEX.json", index)
    pd.DataFrame(
        [
            {
                "slot": row["slot"],
                "status": row["status"],
                "target_peak_date": row["selection"]["target_peak_date"],
                "start_utc": row["selection"]["start_utc"],
                "peak_utc": row["selection"]["peak_utc"],
                "end_utc": row["selection"]["end_utc"],
                "maximum_elevation_deg": row["selection"][
                    "maximum_elevation_deg"
                ],
                "protected_sample_count": row["protected_sample_count"],
                "tle_age_days_at_peak": row["tle_age_days_at_peak"],
                "record_zip": row["record_zip"],
                "record_zip_sha256": row["record_zip_sha256"],
            }
            for row in slot_records
        ]
    ).to_csv(records / "PASS_RECORD_CATALOG.csv", index=False)

    print("PROTECTED-PASS RECORD GENERATION: PASS")
    print(json.dumps(index, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
