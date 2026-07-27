#!/usr/bin/env python3
"""Freeze a precise used-subset TR 38.901 V19.4.0 mapping for the GPU pilot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C_M_S = 299_792_458.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/tr38901_nibi_dlp_pilot_prep.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    inputs = {key: ROOT / value for key, value in cfg["inputs"].items() if not value.startswith("/")}
    work = ROOT / cfg["outputs"]["work_dir"]
    work.mkdir(parents=True, exist_ok=True)

    required = [
        inputs["etsi_pdf"],
        inputs["etsi_source_record"],
        inputs["prior_mapping_checklist"],
        inputs["topology_decision"],
        inputs["cpu_pilot_audit"],
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    if inputs["etsi_pdf"].stat().st_size != int(expected["etsi_pdf_bytes"]):
        raise ValueError("Unexpected ETSI PDF size")
    if sha256_file(inputs["etsi_pdf"]) != expected["etsi_pdf_sha256"]:
        raise ValueError("Unexpected ETSI PDF SHA-256")

    source_record = json.loads(inputs["etsi_source_record"].read_text(encoding="utf-8"))
    topology = json.loads(inputs["topology_decision"].read_text(encoding="utf-8"))
    cpu_pilot = json.loads(inputs["cpu_pilot_audit"].read_text(encoding="utf-8"))
    assert source_record["sha256"] == expected["etsi_pdf_sha256"]
    assert topology["status"] == "PASS_TO_GPU_4USER_PILOT_WITH_STANDARDS_MAPPING_OPEN"
    assert cpu_pilot["status"] == "PASS_CUSTOM_57_SECTOR_CPU_ADAPTER_AUDIT"

    carrier = float(expected["carrier_frequency_hz"])
    wavelength = C_M_S / carrier
    rows = int(expected["array_rows"])
    cols = int(expected["array_cols"])
    aperture_y = (cols - 1) * 0.5 * wavelength
    aperture_z = (rows - 1) * 0.5 * wavelength
    aperture_diagonal = math.hypot(aperture_y, aperture_z)
    fraunhofer = 2.0 * aperture_diagonal**2 / wavelength
    min_distance = 35.0
    if fraunhofer >= min_distance:
        raise ValueError("Pilot array is not safely in the far field at the minimum UMa distance")

    mapping_rows = [
        {
            "clause": "1",
            "model_item": "frequency scope",
            "experiment_choice": "8.15 GHz",
            "status": "USED_AND_IN_SCOPE",
            "evidence": "Official V19.4.0 scope is 0.5-100 GHz.",
        },
        {
            "clause": "7.1.2-7.1.4",
            "model_item": "local/global coordinates and downtilt",
            "experiment_choice": "local x=east/y=north; Sionna yaw and positive downtilt mapping frozen",
            "status": "USED_ADAPTER_AUDITED",
            "evidence": "57-sector CPU adapter passed with frozen IDs and orientations.",
        },
        {
            "clause": "7.2, Table 7.2-1",
            "model_item": "UMa evaluation geometry",
            "experiment_choice": "19 sites, 3 sectors/site, 500 m ISD, 25 m BS, 1.5 m UT, min 35 m, 80% indoor",
            "status": "USED_MATCHED",
            "evidence": "Frozen E3 layout and Sionna qualification.",
        },
        {
            "clause": "7.3.0-7.3.2",
            "model_item": "array, antenna port, and polarization model",
            "experiment_choice": "8x8 dual-cross 3GPP element, half-wavelength spacing",
            "status": "USED_PORT_ORDER_AUDIT_REQUIRED",
            "evidence": "Completed by the companion Sionna port-ordering audit.",
        },
        {
            "clause": "7.4.1",
            "model_item": "UMa pathloss",
            "experiment_choice": "Sionna UMa with enable_pathloss=True",
            "status": "USED_LIBRARY_IMPLEMENTATION_VERSION_BOUNDARY",
            "evidence": "Sionna 2.0.1 source hashed; exact V19.4 delta tables are not claimed.",
        },
        {
            "clause": "7.4.2",
            "model_item": "LOS probability",
            "experiment_choice": "Sionna-generated LOS state",
            "status": "USED_LIBRARY_IMPLEMENTATION_VERSION_BOUNDARY",
            "evidence": "No forced LOS state.",
        },
        {
            "clause": "7.4.3",
            "model_item": "O2I penetration",
            "experiment_choice": "low-loss O2I; indoor probability 0.8",
            "status": "USED_LIBRARY_IMPLEMENTATION_VERSION_BOUNDARY",
            "evidence": "Release-19 7-24 GHz material changes remain a paper sensitivity item.",
        },
        {
            "clause": "7.4.4",
            "model_item": "shadow fading",
            "experiment_choice": "enable_shadow_fading=True",
            "status": "USED_LIBRARY_IMPLEMENTATION_VERSION_BOUNDARY",
            "evidence": "One-seed pilot only; spatial consistency is not claimed.",
        },
        {
            "clause": "7.5",
            "model_item": "fast fading clusters/rays/LSPs",
            "experiment_choice": "Sionna 2.0.1 UMa system-level channel",
            "status": "USED_LIBRARY_IMPLEMENTATION_VERSION_BOUNDARY",
            "evidence": "Installed source hashes and delay sanity are preserved.",
        },
        {
            "clause": "7.6.2",
            "model_item": "large bandwidth/large array",
            "experiment_choice": "9 frequency samples over 100 MHz; 8x8 dual-polarized pilot array",
            "status": "PILOT_APPROXIMATION",
            "evidence": "Paper run requires tone-grid sensitivity and larger-array sensitivity.",
        },
        {
            "clause": "7.6.3",
            "model_item": "spatial consistency",
            "experiment_choice": "single static channel snapshot",
            "status": "NOT_USED_IN_ONE_SEED_PILOT",
            "evidence": "Dynamic mobility campaign remains open.",
        },
        {
            "clause": "7.6.13",
            "model_item": "near-field channel",
            "experiment_choice": "not enabled",
            "status": "EXCLUDED_WITH_FAR_FIELD_JUSTIFICATION",
            "evidence": f"8x8 pilot diagonal aperture={aperture_diagonal:.6f} m; Fraunhofer distance={fraunhofer:.6f} m; minimum UMa distance={min_distance:.1f} m.",
        },
        {
            "clause": "7.6.14",
            "model_item": "spatial non-stationarity",
            "experiment_choice": "not enabled",
            "status": "NOT_USED_PILOT_SENSITIVITY_OPEN",
            "evidence": "Pilot array aperture is small relative to BS-UT distance; larger 16x16 sensitivity remains open.",
        },
        {
            "clause": "7.6.15-7.6.16",
            "model_item": "cluster-count and polarization-power variability",
            "experiment_choice": "not separately enabled",
            "status": "RELEASE19_SENSITIVITY_OPEN",
            "evidence": "Not required to validate the software pilot; must be discussed/tested before paper claim.",
        },
        {
            "clause": "7.8",
            "model_item": "calibration",
            "experiment_choice": "not a 3GPP calibration campaign",
            "status": "PAPER_CALIBRATION_OPEN",
            "evidence": "The pilot is a reproducibility and accounting gate only.",
        },
    ]

    mapping_path = work / "TR38901_V19_4_USED_SUBSET_MAPPING.csv"
    with mapping_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mapping_rows[0].keys()))
        writer.writeheader()
        writer.writerows(mapping_rows)

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "USED_SUBSET_READY_FOR_NONPAPER_GPU_PILOT_WITH_RELEASE19_GAPS",
        "claim_boundary": cfg["claim_boundary"]["mapping"],
        "etsi_source": {
            "bytes": inputs["etsi_pdf"].stat().st_size,
            "sha256": sha256_file(inputs["etsi_pdf"]),
            "document": source_record["document"],
        },
        "pilot_array": {
            "rows": rows,
            "cols": cols,
            "polarization": expected["array_polarization"],
            "ports": expected["array_port_count"],
            "wavelength_m": wavelength,
            "aperture_diagonal_m": aperture_diagonal,
            "fraunhofer_distance_m": fraunhofer,
            "minimum_uma_distance_m": min_distance,
        },
        "used_subset_mapping_csv": str(mapping_path.relative_to(ROOT)),
        "full_v19_4_certification": False,
        "pilot_allowed": True,
        "paper_claim_allowed": False,
        "mandatory_before_paper": [
            "Review/patch the exact 7-24 GHz Release-19 pathloss, O2I, and LSP deltas used by the selected scenario.",
            "Run larger-array and frequency-grid sensitivity.",
            "Add finite-network edge/wraparound sensitivity.",
            "Run mobility/spatial-consistency, uncertainty, multi-seed, and multi-pass campaigns.",
        ],
        "next_gate": "SIONNA_DUAL_POLARIZATION_PORT_ORDER_AUDIT",
    }
    write_json(work / "TR38901_USED_SUBSET_MAPPING_DECISION.json", decision)
    (work / "TR38901_USED_SUBSET_MAPPING_DECISION.md").write_text(
        "# TR 38.901 V19.4.0 used-subset mapping decision\n\n"
        f"- Status: `{decision['status']}`\n"
        f"- Pilot allowed: `{decision['pilot_allowed']}`\n"
        f"- Paper claim allowed: `{decision['paper_claim_allowed']}`\n"
        f"- Pilot Fraunhofer distance: `{fraunhofer:.6f}` m\n"
        f"- Minimum UMa distance: `{min_distance:.1f}` m\n\n"
        "The mapping is sufficient to run a non-paper GPU pilot. It is not a "
        "claim that Sionna 2.0.1 exactly implements every V19.4.0 Release-19 "
        "delta. Those deltas remain explicit paper gates.\n",
        encoding="utf-8",
    )
    print("TR 38.901 V19.4.0 USED-SUBSET MAPPING: PASS")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
