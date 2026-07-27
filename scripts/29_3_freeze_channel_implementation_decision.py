#!/usr/bin/env python3
"""Freeze the clean channel implementation candidate and synchronize status."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/sionna2_channel_qualification.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["environment"]["work_dir"]
    validation = json.loads(
        (work / "SIONNA2_CHANNEL_QUALIFICATION_VALIDATION.json").read_text(
            encoding="utf-8"
        )
    )
    audit = json.loads(
        (work / "SIONNA2_API_QUALIFICATION_AUDIT.json").read_text(encoding="utf-8")
    )
    if validation["status"] != "PASS_CLEAN_SIONNA_2_0_1_IMPLEMENTATION_CANDIDATE":
        raise ValueError("Qualification validation did not pass")

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "CLEAN_SIONNA_2_0_1_SELECTED_FOR_PILOT",
        "claim_boundary": cfg["claim_boundary"]["implementation_decision"],
        "selected_distribution": cfg["expected"]["sionna_distribution"],
        "selected_sionna_version": cfg["expected"]["sionna_version"],
        "selected_torch_version": cfg["expected"]["torch_version"],
        "pilot_device": "cpu",
        "legacy_baseline_disposition": (
            "No reusable executable Sionna UMa/UMi channel engine or archived "
            "channel bundle was found in the reviewed FR3 source root."
        ),
        "scenario_correction": {
            "primary_uma_bs_height_m": 25.0,
            "umi_sensitivity_bs_height_m": 10.0,
            "reason": (
                "UMa and UMi use their scenario-consistent default BS heights; "
                "the prior global 25 m value must not be applied to the UMi "
                "street-canyon sensitivity."
            ),
        },
        "qualification": {
            "uma_api_passed": True,
            "umi_api_passed": True,
            "seeded_cpu_reproducibility_passed": True,
            "environment": audit["environment"],
        },
        "open_before_paper_evidence": [
            "Exact ETSI TR 138 901 V19.4.0 clause-and-parameter mapping.",
            "Frozen custom 19-site/57-sector topology and sector/user ordering.",
            "Paper-scale GPU environment and deterministic seed controls.",
            "Inter-cell UE interference and independently reconstructed rates.",
            "DLP-RZF controller comparisons under identical rate limits and delays.",
            "Uncertainty, runtime, multi-pass, and multi-seed evidence."
        ],
        "next_gate": cfg["next_gate"],
    }
    write_json(work / "CHANNEL_IMPLEMENTATION_DECISION.json", decision)
    (work / "CHANNEL_IMPLEMENTATION_DECISION.md").write_text(
        "# Channel implementation decision\n\n"
        f"- Status: `{decision['status']}`\n"
        f"- Sionna: `{decision['selected_sionna_version']}`\n"
        f"- PyTorch: `{decision['selected_torch_version']}`\n"
        "- Qualification device: CPU\n"
        "- Primary UMa BS height: 25 m\n"
        "- UMi sensitivity BS height: 10 m\n"
        "- Exact Release-19 V19.4.0 mapping: open\n"
        f"- Next gate: `{decision['next_gate']}`\n",
        encoding="utf-8",
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"status_before_sionna2_qualification_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for relative in [
        "PROJECT_STATUS.md",
        "NEXT_IMMEDIATE_STEP.md",
        "config/current_audited_state.yaml",
    ]:
        path = ROOT / relative
        if path.is_file():
            shutil.copy2(path, backup / path.name)

    project_status = """# Current Project Status

## Status date

27 July 2026

## Status in one sentence

The standards/data foundation, validated P.452 engine, E3 geometry and
propagation audits, 57-sector stress screen, and distributed DLP-RZF
architecture are complete as non-paper evidence. The reviewed FR3 source root
contains no reusable executable cellular channel engine. A clean Sionna 2.0.1
PyTorch implementation has passed a CPU UMa/UMi API qualification and is the
selected pilot candidate. Exact Release-19 V19.4.0 mapping and the frozen
57-sector channel adapter are the current gate.

## Completed

- Public incumbent data, pairing, terrain, P.530/S1, and P.452 validation.
- E3 earth-station/pass/pattern/layout and all 19 terrestrial paths.
- 798-row all-site P.452 audit and mechanism-isolation audit.
- 57-sector full-load reference screen.
- Distributed Leakage-Projected RZF architecture and local/aggregate
  certificate software audit.
- Channel-source review: no reusable executable Sionna UMa/UMi engine found.
- Clean Sionna 2.0.1 / PyTorch 2.9.1 CPU UMa/UMi API qualification.
- Scenario-height correction: UMa primary uses 25 m; UMi sensitivity uses 10 m.

## Current scientific gate

1. Complete an explicit ETSI TR 138 901 V19.4.0 parameter/clause mapping.
2. Build the frozen 19-site/57-sector Sionna topology adapter.
3. Run a one-seed GPU pilot with real inter-cell UE interference and local RZF.
4. Independently reconstruct rates, powers, serving-sector mapping, and DLP-RZF
   leakage constraints.
5. Only then launch the multi-seed, multi-pass dynamic-budget experiment.

## Remaining major paper gates

1. Paper-grade E3 distributed-beam and dynamic-budget experiment.
2. E1 real static fixed-service continuity experiment.
3. E2 dynamic rate-limit trap.
4. Held-out uncertainty calibration.
5. Layered runtime/scalability evidence.
6. Statistical campaign, confidence intervals, and ablations.
7. Results-complete manuscript, reproducibility release, and adversarial review.

## Claim boundaries

- The Sionna API pilot is not a paper result.
- Sionna's general TR 38.901 model label is not by itself certification of
  exact V19.4.0 coverage.
- The full-load 57-sector screen remains a severe sensitivity envelope.
- WMMSE is not the proposed operational method.
"""
    (ROOT / "PROJECT_STATUS.md").write_text(
        project_status, encoding="utf-8", newline="\n"
    )

    next_step = """# Next Immediate Step

## Gate

Frozen 57-sector Sionna 2.0.1 DLP-RZF pilot.

## Qualified foundation

- Clean `sionna-no-rt==2.0.1` candidate.
- `torch==2.9.1`.
- CPU UMa and UMi API qualification passed.
- UMa model-consistent BS height: 25 m.
- UMi model-consistent BS height: 10 m.
- Distributed local RZF plus exact local leakage projection.
- No network-wide UE CSI or joint precoder.

## Required sequence

1. Map the exact experiment parameters to ETSI TR 138 901 V19.4.0.
2. Adapt the frozen 19-site/57-sector IDs and geometry to the Sionna topology.
3. Generate one reproducible UMa seed with four users per sector.
4. Compute local RZF from local UE CSI only.
5. Include all inter-cell UE interference in SINR/rate metrics.
6. Reconstruct transmit power and rates independently from exported tensors.
7. Apply and verify DLP-RZF local leakage constraints.
8. Measure CPU/GPU memory and runtime.
9. Preserve the pilot as non-paper evidence before scaling.

## Stop condition

Do not launch the final campaign until the topology mapping, channel version
mapping, inter-cell rate reconstruction, leakage verification, and one-seed
GPU pilot all pass.
"""
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        next_step, encoding="utf-8", newline="\n"
    )

    audited = """schema_version: 4
as_of_date: "2026-07-27"

publication:
  primary_target: IEEE_TWC
  mode: operator_independent

main_operational_architecture:
  name: distributed_leakage_projected_rzf
  acronym: DLP_RZF
  wmmse_main_method: removed
  central_instantaneous_ue_csi: prohibited
  central_joint_precoder: prohibited

channel_implementation:
  selected_candidate:
    distribution: sionna-no-rt
    version: 2.0.1
    framework: PyTorch
    torch_version: 2.9.1
    qualification_device: CPU
    status: api_qualified_not_paper_evidence
  legacy_executable_baseline:
    status: not_found_in_reviewed_source_root
  standards_mapping:
    reference: ETSI_TR_138_901_V19_4_0
    exact_clause_mapping_status: open
  scenarios:
    uma_primary:
      bs_height_m: 25.0
      isd_m: 500.0
    umi_sensitivity:
      bs_height_m: 10.0
      isd_m: 200.0

e3:
  propagation_and_reference_screen:
    status: complete_reference_only
  distributed_architecture:
    status: software_audit_passed_not_paper_result
  next_gate: frozen_57_sector_sionna2_dlp_rzf_pilot

remaining_major_paper_gates:
  - full_e3_distributed_beam_dynamic_budget_experiment
  - e1_static_fixed_service
  - e2_dynamic_rate_limit
  - uncertainty_calibration
  - layered_runtime_scalability
  - statistical_campaign
  - final_manuscript_and_release
"""
    (ROOT / "config/current_audited_state.yaml").write_text(
        audited, encoding="utf-8", newline="\n"
    )

    status_sync = {
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
    write_json(work / "SIONNA2_STATUS_SYNC.json", status_sync)
    print("CHANNEL IMPLEMENTATION DECISION FREEZE: PASS")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
