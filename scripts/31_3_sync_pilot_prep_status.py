#!/usr/bin/env python3
"""Synchronize project status after Nibi GPU-pilot preparation."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/tr38901_nibi_dlp_pilot_prep.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["outputs"]["work_dir"]
    mapping = json.loads(
        (work / "TR38901_USED_SUBSET_MAPPING_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    port = json.loads(
        (work / "SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    bundle = json.loads(
        (work / "NIBI_BUNDLE_METADATA.json").read_text(encoding="utf-8")
    )
    if not mapping["pilot_allowed"] or mapping["paper_claim_allowed"]:
        raise ValueError("Unexpected mapping decision")
    if port["status"] != "PASS_SIONNA_DUAL_POLARIZATION_PORT_ORDER_AND_BASIS":
        raise ValueError("Port audit did not pass")
    if bundle["status"] != "READY_FOR_NIBI_ONE_SEED_GPU_PILOT_REVIEW":
        raise ValueError("Nibi bundle is not review-ready")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"status_before_nibi_pilot_prep_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for relative in [
        "PROJECT_STATUS.md",
        "NEXT_IMMEDIATE_STEP.md",
        "config/current_audited_state.yaml",
    ]:
        source = ROOT / relative
        if source.is_file():
            shutil.copy2(source, backup / source.name)

    project = """# Current Project Status

## Status date

27 July 2026

## Status in one sentence

The propagation/E3 foundation, distributed DLP-RZF architecture, Sionna 2.0.1
CPU qualification, custom 57-sector adapter, used-subset V19.4.0 mapping, and
exact dual-polarized Sionna port-order audit are complete as non-paper evidence.
A self-contained Nibi H100 bundle for the one-seed 57-sector/four-user DLP-RZF
pilot is prepared but has not yet been executed or independently accepted.

## Current gate

`INDEPENDENT_REVIEW_THEN_RUN_NIBI_ONE_SEED_GPU_PILOT`

## Completed in the preparation stage

- Clause-level used-subset ETSI TR 138 901 V19.4.0 mapping for a non-paper pilot.
- Explicit Release-19 delta gaps retained; no full V19.4 certification claim.
- 8x8 dual-cross Sionna port positions and polarization index sets audited.
- Far-field justification for the reduced pilot array.
- Reviewable Nibi H100 source bundle with 57 sectors, four users per sector,
  nine frequency samples, local RZF, all inter-cell interference, and protected-
  tone dual-polarization DLP projection.

## Immediate requirements

1. Independently review the generated GitHub source and bundle manifest.
2. Run the one-seed Nibi H100 pilot only after that review.
3. Validate power, SINR, rate, leakage, port order, runtime, and GPU memory.
4. Keep the result explicitly non-paper evidence.
5. Complete Release-19 delta patches/sensitivities before the final campaign.
"""
    (ROOT / "PROJECT_STATUS.md").write_text(project, encoding="utf-8", newline="\n")

    next_step = """# Next Immediate Step

## Gate

Independent review, then Nibi execution of the one-seed 57-sector/four-user
DLP-RZF GPU pilot.

## Review before execution

- `evidence/tr38901_nibi_dlp_pilot_prep/TR38901_USED_SUBSET_MAPPING_DECISION.json`
- `evidence/tr38901_nibi_dlp_pilot_prep/TR38901_V19_4_USED_SUBSET_MAPPING.csv`
- `evidence/tr38901_nibi_dlp_pilot_prep/SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json`
- `nibi/dlp_rzf_pilot_v1/run_gpu_pilot.py`
- `nibi/dlp_rzf_pilot_v1/validate_gpu_pilot.py`
- `evidence/tr38901_nibi_dlp_pilot_prep/NIBI_BUNDLE_METADATA.json`

## Pilot claim boundary

One seed, finite network, 8x8 dual-polarized array, nine frequency samples,
and instantaneous proportional budgets. It is a GPU/accounting gate, not the
dynamic-controller paper experiment.
"""
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        next_step, encoding="utf-8", newline="\n"
    )

    audited = {
        "schema_version": 6,
        "as_of_date": "2026-07-27",
        "main_method": "DLP_RZF",
        "sionna": {
            "version": "2.0.1",
            "torch_base_version": "2.9.1",
            "cpu_qualification": "passed",
            "custom_57_sector_adapter": "passed_nonpaper",
            "dual_pol_port_order": "passed",
        },
        "standards": {
            "reference": "ETSI_TR_138_901_V19_4_0",
            "used_subset_mapping": mapping["status"],
            "full_v19_4_certification": False,
            "release19_delta_sensitivities": "open",
        },
        "nibi_gpu_pilot": {
            "status": "prepared_not_executed",
            "sites": 19,
            "sectors": 57,
            "users_per_sector": 4,
            "users": 228,
            "ports_per_bs": 128,
            "frequency_samples": 9,
            "bundle_sha256": bundle["zip_sha256"],
        },
        "next_gate": cfg["next_gate"],
    }
    (ROOT / "config/current_audited_state.yaml").write_text(
        yaml.safe_dump(audited, sort_keys=False), encoding="utf-8", newline="\n"
    )
    record = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "backup_directory": str(backup.relative_to(ROOT)),
        "updated_files": [
            "PROJECT_STATUS.md",
            "NEXT_IMMEDIATE_STEP.md",
            "config/current_audited_state.yaml",
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(work / "NIBI_PILOT_PREP_STATUS_SYNC.json", record)
    print("NIBI PILOT PREPARATION STATUS SYNCHRONIZATION: PASS")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
