#!/usr/bin/env python3
"""Build the centralized human-review folder and upload bundle."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def unique_existing(paths: list[Path]) -> list[Path]:
    output: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved.is_file() and resolved not in seen:
            seen.add(resolved)
            output.append(resolved)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/e3_first_sector_p452.yaml",
    )
    args = parser.parse_args()

    config_path = ROOT / args.config
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    work_dir = ROOT / config["outputs"]["work_dir"]
    review_dir = ROOT / config["outputs"]["review_dir"]
    log_dir = ROOT / config["outputs"]["log_dir"]
    upload_dir = review_dir / "review_upload"
    review_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    validation = json.loads(
        (work_dir / "FIRST_SECTOR_P452_VALIDATION.json").read_text(
            encoding="utf-8"
        )
    )
    accounting_audit = json.loads(
        (work_dir / "FIRST_SECTOR_P452_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    matlab_audit = json.loads(
        (work_dir / "P452_FIRST_SECTOR_MATLAB_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    conditional_summary = pd.read_csv(
        work_dir / "conditional_threshold_summary.csv"
    )
    bs_gain = pd.read_csv(work_dir / "bs_gain_accounting.csv")

    # These are the files that a human reviewer should actively inspect.
    review_files = [
        work_dir / "FIRST_SECTOR_TERRAIN_DECISION.json",
        work_dir / "p452_profile.csv",
        work_dir / "p452_parameters.json",
        work_dir / "FIRST_SECTOR_P452_PREP_AUDIT.json",
        work_dir / "p452_basic_loss.csv",
        work_dir / "p452_coupling_export.csv",
        work_dir / "P452_FIRST_SECTOR_MATLAB_AUDIT.json",
        work_dir / "bs_gain_accounting.csv",
        work_dir / "earth_station_gain_timeseries.csv",
        work_dir / "gain_accounting_timeseries.csv.gz",
        work_dir / "conditional_threshold_summary.csv",
        work_dir / "p452_coast_distance_sensitivity.csv",
        work_dir / "peak_accounting_components.csv",
        work_dir / "FIRST_SECTOR_P452_AUDIT.json",
        work_dir / "FIRST_SECTOR_P452_AUDIT.md",
        work_dir / "FIRST_SECTOR_P452_VALIDATION.json",
        work_dir / "FIRST_SECTOR_P452_VALIDATION.md",
        review_dir / "p452_basic_loss_vs_time_percentage.png",
        review_dir / "earth_station_off_axis_and_gain.png",
        review_dir / "conditional_interference_p20_H.png",
        review_dir / "peak_accounting_components.png",
        ROOT / config["inputs"]["terrain_review_pdf"],
    ]

    missing = [str(path) for path in review_files if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing review files:\n" + "\n".join(f"  - {x}" for x in missing)
        )

    top_case = conditional_summary.sort_values(
        "max_interference_dbw_per_10mhz",
        ascending=False,
    ).iloc[0]

    summary_text = (
        "E3 FIRST-SECTOR P.452 DROP-IN SUMMARY\n"
        "Status: PASS\n"
        f"Sector: {validation['sector_id']}\n"
        f"P.452 rows: {validation['p452_basic_loss_rows']}\n"
        "P.452 basic-loss range: "
        f"{matlab_audit['minimum_basic_loss_db']:.9f} to "
        f"{matlab_audit['maximum_basic_loss_db']:.9f} dB\n"
        f"Gain-accounting rows: {validation['gain_accounting_rows']}\n"
        f"Protected samples: {validation['protected_samples']}\n"
        f"MATLAB release: {validation['matlab_release']}\n"
        f"P.452 commit: {validation['p452_reference_commit']}\n"
        "Minimum ES off-axis: "
        f"{accounting_audit['earth_station_minimum_off_axis_deg']:.9f} deg\n"
        "Maximum nominal aggregate ES gain: "
        f"{accounting_audit['earth_station_maximum_aggregate_gain_dbi']:.9f} dBi\n"
        "Highest conditional accounting value: "
        f"{float(top_case['max_interference_dbw_per_10mhz']):.9f} dBW/10 MHz\n"
        f"Highest-value BS case: {top_case['bs_gain_case']}\n"
        f"Highest-value ES pattern: {top_case['earth_station_pattern_type']}\n"
        f"Highest-value P.452 p: {top_case['p452_time_percentage']} %\n"
        f"Highest-value polarization: {top_case['polarization_label']}\n"
        f"Claim boundary: {validation['claim_boundary']}\n"
        f"Next gate: {validation['next_gate']}\n\n"
        "Open items:\n"
        + "\n".join(f" - {item}" for item in accounting_audit["open_items"])
        + "\n"
    )

    (review_dir / "RUN_SUMMARY.txt").write_text(
        summary_text,
        encoding="utf-8",
    )
    write_json(
        review_dir / "RUN_SUMMARY.json",
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "validation": validation,
            "accounting_audit": accounting_audit,
            "matlab_audit": matlab_audit,
            "highest_conditional_case": top_case.to_dict(),
        },
    )

    review_relative = [
        path.resolve().relative_to(ROOT).as_posix() for path in review_files
    ]
    (review_dir / "REVIEW_FILES.txt").write_text(
        "\n".join(review_relative) + "\n",
        encoding="utf-8",
    )

    top_table = conditional_summary.sort_values(
        "max_interference_dbw_per_10mhz",
        ascending=False,
    ).head(12)

    review_page = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>E3 first-sector review</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 28px; max-width: 1300px; }}
img {{ max-width: 100%; border: 1px solid #bbb; margin: 10px 0; }}
table {{ border-collapse: collapse; font-size: 12px; }}
th, td {{ border: 1px solid #bbb; padding: 4px; }}
pre {{ background: #f4f4f4; padding: 12px; white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>E3 Site-18 first-sector P.452 accounting review</h1>
<pre>{html.escape(summary_text)}</pre>
<h2>BS gain cases</h2>
{bs_gain.to_html(index=False, float_format=lambda x: f'{x:.6g}')}
<h2>Highest conditional interference scenarios</h2>
{top_table.to_html(index=False, float_format=lambda x: f'{x:.6g}')}
<h2>Figures</h2>
<h3>P.452 loss</h3><img src="p452_basic_loss_vs_time_percentage.png">
<h3>Earth-station geometry/gain</h3><img src="earth_station_off_axis_and_gain.png">
<h3>Conditional interference</h3><img src="conditional_interference_p20_H.png">
<h3>Peak accounting terms</h3><img src="peak_accounting_components.png">
<h2>Files requiring review</h2>
<pre>{html.escape(chr(10).join(review_relative))}</pre>
</body>
</html>
"""
    (review_dir / "REVIEW_INDEX.html").write_text(
        review_page,
        encoding="utf-8",
    )

    bundle_name = "E3_SITE18_FIRST_SECTOR_P452_REVIEW_BUNDLE_2026-07-26.zip"
    bundle_path = upload_dir / bundle_name

    dropin_source_files = [
        ROOT / "README_E3_FIRST_SECTOR_P452_DROPIN.md",
        ROOT / "RUN_E3_FIRST_SECTOR_P452_DROPIN.sh",
        ROOT / "config/e3_first_sector_p452.yaml",
        ROOT / "scripts/24_1_prepare_e3_first_sector_p452.py",
        ROOT / "scripts/24_2_preflight_e3_first_sector_p452.py",
        ROOT / "scripts/24_3_build_e3_first_sector_gain_accounting.py",
        ROOT / "scripts/24_4_validate_e3_first_sector_p452.py",
        ROOT / "scripts/24_5_package_e3_first_sector_review.py",
        ROOT / "matlab/run_e3_first_sector_p452.m",
        ROOT / "tests/test_e3_first_sector_p452_dropin.py",
        ROOT / "wrappers/e3_first_sector_p452/00_prepare.sh",
        ROOT / "wrappers/e3_first_sector_p452/10_matlab.sh",
        ROOT / "wrappers/e3_first_sector_p452/20_postprocess_validate.sh",
        ROOT / "wrappers/e3_first_sector_p452/30_package_review.sh",
    ]

    generated_files = [
        review_dir / "RUN_SUMMARY.txt",
        review_dir / "RUN_SUMMARY.json",
        review_dir / "REVIEW_FILES.txt",
        review_dir / "REVIEW_INDEX.html",
    ]

    # Do not include the package-review log while it is being written. Include
    # all complete prior wrapper logs and run-context records.
    selected_logs = [
        log_dir / "RUN_CONTEXT.txt",
        log_dir / "python_environment.txt",
        log_dir / "00_prepare.log",
        log_dir / "00_prepare.exitcode",
        log_dir / "10_matlab.log",
        log_dir / "10_matlab.exitcode",
        log_dir / "20_postprocess_validate.log",
        log_dir / "20_postprocess_validate.exitcode",
    ]

    include = unique_existing(
        dropin_source_files + review_files + generated_files + selected_logs
    )

    manifest_lines: list[str] = []
    with ZipFile(
        bundle_path,
        "w",
        compression=ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in include:
            arcname = path.relative_to(ROOT).as_posix()
            archive.write(path, arcname)
            manifest_lines.append(f"{sha256_file(path)}  {arcname}")
        archive.writestr(
            "BUNDLE_MANIFEST.sha256",
            "\n".join(manifest_lines) + "\n",
        )
        archive.writestr(
            "BUNDLE_METADATA.json",
            json.dumps(
                {
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "claim_boundary": config["claim_boundary"],
                    "sector_id": validation["sector_id"],
                    "file_count": len(include),
                    "review_file_count": len(review_files),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    checksum_path = upload_dir / f"{bundle_name}.sha256"
    checksum_path.write_text(
        f"{sha256_file(bundle_path)}  {bundle_path.name}\n",
        encoding="utf-8",
    )

    # Verify the newly created ZIP before declaring PASS.
    with ZipFile(bundle_path) as archive:
        bad_member = archive.testzip()
    if bad_member is not None:
        raise RuntimeError(f"Review ZIP CRC failure at: {bad_member}")

    print("FIRST-SECTOR REVIEW PACKAGE: PASS")
    print("Review directory:", review_dir)
    print("Review index:", review_dir / "REVIEW_INDEX.html")
    print("Review files list:", review_dir / "REVIEW_FILES.txt")
    print("Review-required file count:", len(review_files))
    print("Upload-bundle source-file count:", len(include))
    print("UPLOAD THESE TWO FILES:")
    print(bundle_path)
    print(checksum_path)
    print("All review-required files are listed in REVIEW_FILES.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
