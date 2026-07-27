#!/usr/bin/env python3
"""Create the standards mapping scaffold and final topology-readiness decision."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/sionna2_topology_readiness.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["environment"]["work_dir"]
    etsi_path = ROOT / cfg["environment"]["etsi_pdf_path"]
    source_record_path = work / "ETSI_TR_138901_V19_4_SOURCE_RECORD.json"

    if not etsi_path.is_file():
        raise FileNotFoundError(etsi_path)
    if etsi_path.stat().st_size != int(cfg["etsi"]["expected_bytes"]):
        raise ValueError(
            f"Unexpected ETSI PDF size: {etsi_path.stat().st_size}; "
            f"expected {cfg['etsi']['expected_bytes']}"
        )
    if etsi_path.read_bytes()[:4] != b"%PDF":
        raise ValueError("ETSI source is not a PDF")

    source_record = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "document": cfg["etsi"]["document"],
        "directory_url": cfg["etsi"]["directory_url"],
        "pdf_url": cfg["etsi"]["pdf_url"],
        "bytes": etsi_path.stat().st_size,
        "sha256": sha256_file(etsi_path),
        "local_path": str(etsi_path.relative_to(ROOT)),
        "git_policy": "PDF_NOT_COMMITTED; source record and hash only",
    }
    write_json(source_record_path, source_record)

    mapping_rows = [
        ["carrier_frequency", "0.5-100 GHz scope / experiment at 8.15 GHz", "8.15 GHz API verified", "USED_API_VERIFIED"],
        ["primary_scenario", "UMa", "UMa class and 25 m qualification verified", "USED_API_VERIFIED"],
        ["sensitivity_scenario", "UMi street canyon", "UMi class and 10 m qualification verified", "QUALIFICATION_VERIFIED_NOT_IN_PRIMARY_PILOT"],
        ["pathloss", "TR 38.901 UMa/UMi pathloss", "enable_pathloss=True", "USED_LIBRARY_REQUIRES_CLAUSE_MAPPING"],
        ["shadow_fading", "TR 38.901 large-scale shadowing", "enable_shadow_fading=True", "USED_LIBRARY_REQUIRES_CLAUSE_MAPPING"],
        ["los_probability", "TR 38.901 scenario-dependent LoS state", "Library-generated because los=None", "USED_LIBRARY_REQUIRES_CLAUSE_MAPPING"],
        ["o2i_penetration", "Low-loss O2I model", "o2i_model=low", "USED_LIBRARY_REQUIRES_CLAUSE_MAPPING"],
        ["large_scale_parameters", "Delay/angle spreads, K-factor, correlations", "Sionna-generated", "USED_LIBRARY_REQUIRES_PARAMETER_TABLE_AUDIT"],
        ["small_scale_clusters", "Cluster/ray generation", "Sionna-generated", "USED_LIBRARY_REQUIRES_PARAMETER_TABLE_AUDIT"],
        ["bs_antenna", "TR 38.901 element pattern", "2x2 dual cross, 8 ports for adapter pilot", "PILOT_ONLY"],
        ["ut_antenna", "Omnidirectional single-polarized UT", "One port", "PILOT_ONLY"],
        ["release19_7_24ghz_changes", "V19.4.0 additions/validations in 7-24 GHz", "Not certified by library version label", "OPEN_MANDATORY_BEFORE_PAPER"],
        ["near_field", "Release-19 near-field framework", "Not enabled", "NOT_USED_OPEN_SENSITIVITY"],
        ["spatial_nonstationarity", "Release-19 SNS framework", "Not enabled", "NOT_USED_OPEN_SENSITIVITY"],
        ["realistic_ut_antenna_and_blockage", "Release-19 UT antenna/blockage enhancements", "Not enabled", "NOT_USED_OPEN_SENSITIVITY"],
        ["custom_57_sector_topology", "Frozen 19-site/57-sector layout", "Finite custom adapter, no wraparound", "ADAPTER_AUDIT_ONLY_EDGE_SENSITIVITY_OPEN"],
        ["inter_cell_rate", "All 57 sectors included", "One UE/sector center-frequency rate reconstructed", "ADAPTER_AUDIT_ONLY"],
        ["dlp_rzf", "Distributed leakage-projected RZF", "Not applied in adapter pilot", "NEXT_GPU_PILOT"],
    ]
    mapping_path = work / "TR38901_V19_4_MAPPING_CHECKLIST.csv"
    with mapping_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["model_item", "standards_role", "current_implementation", "status"]
        )
        writer.writerows(mapping_rows)

    delay = json.loads(
        (work / "SIONNA2_DELAY_AND_SOURCE_AUDIT.json").read_text(encoding="utf-8")
    )
    topology_skipped = work / "CUSTOM_TOPOLOGY_ADAPTER_SKIPPED.json"
    if delay["status"] != "PASS_ENERGY_WEIGHTED_DELAY_SANITY":
        status = "SCIENTIFIC_STOP_DELAY_SANITY"
        next_gate = delay["next_gate"]
        topology_status = "SKIPPED"
    else:
        topology = json.loads(
            (work / "CUSTOM_57_SECTOR_TOPOLOGY_AUDIT.json").read_text(
                encoding="utf-8"
            )
        )
        pilot = json.loads(
            (work / "CUSTOM_57_SECTOR_SIONNA_PILOT_AUDIT.json").read_text(
                encoding="utf-8"
            )
        )
        if topology["status"] != "PASS_CUSTOM_TOPOLOGY_GEOMETRY_READY":
            raise ValueError("Topology geometry audit did not pass")
        if pilot["status"] != "PASS_CUSTOM_57_SECTOR_CPU_ADAPTER_AUDIT":
            raise ValueError("Custom Sionna adapter pilot did not pass")
        status = "PASS_TO_GPU_4USER_PILOT_WITH_STANDARDS_MAPPING_OPEN"
        next_gate = cfg["next_gate"]
        topology_status = pilot["status"]

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "claim_boundary": cfg["claim_boundary"]["topology_adapter"],
        "delay_audit_status": delay["status"],
        "topology_adapter_status": topology_status,
        "etsi_source_record": source_record,
        "mapping_checklist": str(mapping_path.relative_to(ROOT)),
        "exact_tr_138_901_v19_4_mapping_complete": False,
        "four_user_gpu_pilot_complete": False,
        "required_before_paper_evidence": [
            "Complete and review the V19.4.0 clause/parameter mapping.",
            "Run four users per sector on a pinned GPU environment.",
            "Apply local RZF and DLP-RZF using the actual Sionna port ordering.",
            "Include inter-cell interference on the declared tone/resource grid.",
            "Independently reconstruct powers, SINRs, rates, and incumbent leakage.",
            "Run load, delay, uncertainty, multi-seed, and multi-pass campaigns."
        ],
        "next_gate": next_gate,
    }
    write_json(work / "SIONNA2_TOPOLOGY_READINESS_DECISION.json", decision)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"status_before_sionna2_topology_readiness_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for relative in [
        "PROJECT_STATUS.md",
        "NEXT_IMMEDIATE_STEP.md",
        "config/current_audited_state.yaml",
    ]:
        path = ROOT / relative
        if path.is_file():
            shutil.copy2(path, backup / path.name)

    project = f"""# Current Project Status

## Status date

27 July 2026

## Status in one sentence

The validated propagation/E3 foundation, distributed DLP-RZF architecture,
and clean Sionna 2.0.1 CPU API qualification are complete as non-paper
evidence. The current hardening stage records `{status}`. The exact ETSI
TR 138 901 V19.4.0 clause/parameter mapping and the four-user-per-sector GPU
DLP-RZF pilot remain open.

## Current gate

`{next_gate}`

## Immediate requirements

1. Review the energy-weighted delay audit rather than the misleading raw
   maximum delay alone.
2. Complete the V19.4.0 mapping checklist.
3. Freeze Sionna antenna-port ordering for the DLP incumbent steering vector.
4. Run four users per sector with inter-cell interference on GPU.
5. Reconstruct rates, powers, and leakage independently.
6. Keep the finite-network/no-wraparound pilot as non-paper evidence and add
   an edge/wraparound sensitivity for the final campaign.
"""
    (ROOT / "PROJECT_STATUS.md").write_text(project, encoding="utf-8", newline="\n")

    next_text = f"""# Next Immediate Step

## Gate

`{next_gate}`

## Completed in the readiness stage

- Energy-weighted Sionna delay/source audit.
- Official ETSI TR 138 901 V19.4.0 source record and SHA-256.
- Release-19 mapping checklist scaffold.
- Deterministic custom 19-site/57-sector geometry adapter.
- One-user-per-sector finite-network inter-cell rate adapter audit, when the
  delay gate passes.

## Stop condition before the paper campaign

Do not launch the final campaign until the exact V19.4.0 mapping, Sionna port
ordering, four-user GPU pilot, DLP leakage verification, and independent
power/SINR/rate reconstruction pass.
"""
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        next_text, encoding="utf-8", newline="\n"
    )

    audited = {
        "schema_version": 5,
        "as_of_date": "2026-07-27",
        "main_method": "DLP_RZF",
        "sionna": {
            "version": "2.0.1",
            "torch_base_version": "2.9.1",
            "qualification": "cpu_api_passed",
            "delay_audit": delay["status"],
            "topology_readiness": status,
        },
        "standards": {
            "reference": "ETSI_TR_138_901_V19_4_0",
            "source_sha256": source_record["sha256"],
            "exact_mapping_complete": False,
        },
        "next_gate": next_gate,
    }
    write_json(work / "SIONNA2_TOPOLOGY_STATUS_SYNC.json", audited)
    import yaml

    (ROOT / "config/current_audited_state.yaml").write_text(
        yaml.safe_dump(audited, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )

    print("SIONNA 2.0.1 TOPOLOGY READINESS FINALIZATION: PASS")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
