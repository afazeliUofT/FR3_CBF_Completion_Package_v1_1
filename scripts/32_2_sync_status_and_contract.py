#!/usr/bin/env python3
"""Synchronize project status after the successful one-seed gate."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/one_seed_18658301_freeze.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    evidence = ROOT / cfg["paths"]["evidence_dir"]
    validation = json.loads(
        (evidence / "ONE_SEED_FREEZE_VALIDATION.json").read_text(
            encoding="utf-8"
        )
    )
    metrics = json.loads(
        (evidence / "ONE_SEED_METRICS.json").read_text(encoding="utf-8")
    )
    if validation["status"] != "PASS_FROZEN_ONE_SEED_EVIDENCE":
        raise ValueError("One-seed evidence has not passed validation")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"status_before_one_seed_freeze_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for relative in [
        "PROJECT_STATUS.md",
        "NEXT_IMMEDIATE_STEP.md",
        "ROADMAP.md",
        "config/current_audited_state.yaml",
        "NIBI_FR3_EXECUTION_SUPERSEDED.md",
    ]:
        source = ROOT / relative
        if source.is_file():
            shutil.copy2(source, backup / source.name)

    today = datetime.now(timezone.utc).date().isoformat()
    minimum_retention = metrics["network_utility"]["minimum_retention"]
    project = f"""# Current Project Status

## Status date

{today}

## Status in one sentence

The propagation, incumbent, topology, standards-subset, exact steering, and
distributed DLP-RZF foundations are complete as non-paper evidence. Nibi job
18658301 successfully closed the one-seed 57-sector, 228-user software and
physical-accounting gate with zero local budget violations and zero projection
power-increase violations. The dynamic delayed/rate-limited controller and
paper-grade statistical campaign remain open.

## Frozen successful gate

- Job: `18658301`
- GPU: NVIDIA H100 80 GB HBM3
- Sectors/users: 57 / 228
- Users per sector: 4
- BS ports: 128
- Frequency samples: 9
- Protected-pass samples: 587
- Minimum network sum-rate retention: `{minimum_retention:.6%}`
- Claim boundary: `ONE_SEED_SOFTWARE_AND_PHYSICAL_ACCOUNTING_GATE_NOT_PAPER_RESULT`

## Current gate

`{cfg['next_gate']}`

## Immediate requirements

1. Review and merge the frozen job-18658301 evidence and provenance overlay.
2. Freeze the delayed/rate-limited dynamic experiment contract.
3. Prepare one controller-ready full-228-user topology export.
4. Compare the full-topology export with the four-user-chunk reference.
5. Implement practical static, myopic, virtual-queue, and predictive/CBF
   controllers locally before launching a multi-seed campaign.

## Open paper gates

- exact long-term incumbent criterion;
- uncertainty calibration;
- practical array/hybrid sensitivity;
- full-topology spatial correlation;
- rate-limit counterexample;
- controller runtime and message overhead;
- multi-seed, multi-pass confidence intervals.
"""
    (ROOT / "PROJECT_STATUS.md").write_text(
        project, encoding="utf-8", newline="\n"
    )

    next_step = f"""# Next Immediate Step

## Gate

`{cfg['next_gate']}`

## Work location

Local WSL only for the present freeze and contract review. Do not submit a new
Nibi seed yet.

## Required sequence

1. Accept job 18658301 only as a one-seed software/physical-accounting gate.
2. Preserve the immutable executed input and return hashes.
3. Use the execution metadata overlay rather than editing the old bundle.
4. Review `config/dynamic_safety_experiment_v1.yaml`.
5. Review `config/controller_ready_full_topology_export_v1.yaml`.
6. After independent review, prepare one Nibi H100 export using all 228 users
   in one Sionna topology call.
7. Export protected-tone amplitude components and coupling sufficient
   statistics so controller experiments can run locally.
8. Do not launch multiple channel seeds until the dynamic rate-limit
   counterexample passes.
"""
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        next_step, encoding="utf-8", newline="\n"
    )

    roadmap = """# FR3 TWC Roadmap

## Phase 1 — foundation

Status: substantially complete as non-paper evidence.

- public/modelled incumbent records;
- terrain and P.452 propagation;
- EESS pass and receive-pattern geometry;
- 19-site/57-sector modelled cellular layout;
- Sionna channel/API qualification;
- exact port order and incumbent local frame;
- distributed local DLP-RZF certificate.

## Phase 2 — physical/accounting platform

Status: one-seed gate passed.

- Nibi job 18658301 completed;
- 57 sectors, 228 users, 128 ports;
- full inter-cell rate accounting;
- 587 protected samples;
- zero local budget and power-increase violations.

Boundary: not a paper result. The current proportional allocator collapses to
a common oracle scale.

## Phase 3 — controller-ready export

Status: next.

- generate all 228 users in one topology call;
- export protected-tone amplitude components;
- export local utility sufficient statistics;
- compare full topology against the chunked reference;
- retain exact fingerprints and provenance.

## Phase 4 — dynamic contribution

- static geometry-aware nonuniform allocation;
- myopic utility-aware safety;
- virtual-queue control;
- predictive/CBF safety filter;
- equal delay, update period, information and slew constraints;
- decisive rate-limit counterexample.

## Phase 5 — robustness and practicality

- uncertainty calibration;
- short- and long-term criteria;
- CSI and array error;
- message delay/drop;
- hybrid or practical array sensitivity;
- coordinator and local-BS runtime;
- bytes per update.

## Phase 6 — paper campaign

- at least 30 seeds;
- at least 5 protected passes;
- four load levels;
- global layout rotations and placement sensitivity;
- finite-network/edge sensitivity;
- confidence intervals and ablations.

## TWC go/no-go condition

Proceed to manuscript submission only when the predictive/CBF method provides
a statistically supported safety-utility advantage under identical delayed
and rate-limited conditions, with no hidden emergency slack.
"""
    (ROOT / "ROADMAP.md").write_text(
        roadmap, encoding="utf-8", newline="\n"
    )

    compute = """# FR3 compute-execution status

The earlier Nibi-oriented bundle with SHA-256

`a6ad7c3e202b57ff002b330b1d2c4e0f5b58a90b10fb7e64d6ae86c7069bef69`

is superseded and must not be run.

Historical diagnostic jobs on Narval and Nibi are complete and require no
cancellation. The accepted FR3 execution is:

- cluster: Nibi;
- job: 18658301;
- job name: `fr3-dlp-nibi-proj-v6`;
- state: COMPLETED;
- exit code: 0:0;
- executed input SHA-256:
  `9be0d1a0eb58c4764871d92e95b84f8e85c18818257d08522beed83d67573144`;
- return SHA-256:
  `05e49566fc9a7dcef7279ff6324e46d35ceb4fc457ebccea53410ccf3706589c`.

All FR3 paths and job names were isolated from the user's unrelated
quantum-computing work.
"""
    (ROOT / "COMPUTE_EXECUTION_STATUS.md").write_text(
        compute, encoding="utf-8", newline="\n"
    )
    (ROOT / "NIBI_FR3_EXECUTION_SUPERSEDED.md").write_text(
        "# Historical FR3 Nibi note\n\n"
        "The old blanket statement that no FR3 Nibi execution occurred is "
        "superseded. See `COMPUTE_EXECUTION_STATUS.md` for the authoritative "
        "history and the successful job-18658301 record.\n",
        encoding="utf-8",
        newline="\n",
    )

    audited = f"""schema_version: 7
as_of_date: '{today}'
main_method: DLP_RZF
claim_boundary: ONE_SEED_SOFTWARE_AND_PHYSICAL_ACCOUNTING_GATE_NOT_PAPER_RESULT
foundation:
  propagation_and_incumbent: passed_nonpaper
  sionna_cpu_qualification: passed_nonpaper
  custom_57_sector_adapter: passed_nonpaper
  exact_local_frame_steering: passed
  dual_pol_port_order: passed
nibi_one_seed_gate:
  status: PASS_ONE_SEED_SOFTWARE_AND_PHYSICAL_ACCOUNTING_GATE
  job_id: '18658301'
  job_name: fr3-dlp-nibi-proj-v6
  gpu: NVIDIA_H100_80GB_HBM3
  sites: 19
  sectors: 57
  users: 228
  users_per_sector: 4
  ports_per_bs: 128
  frequency_samples: 9
  protected_pass_samples: 587
  local_budget_violations: 0
  power_increase_violations: 0
  minimum_network_rate_retention: {minimum_retention:.16f}
  input_bundle_sha256: 9be0d1a0eb58c4764871d92e95b84f8e85c18818257d08522beed83d67573144
  return_bundle_sha256: 05e49566fc9a7dcef7279ff6324e46d35ceb4fc457ebccea53410ccf3706589c
limitations:
  common_scale_oracle: true
  delayed_rate_limited_controller: open
  full_topology_cross_sector_correlation: open
  uncertainty_calibration: open
  statistical_campaign: open
next_gate: {cfg['next_gate']}
"""
    (ROOT / "config/current_audited_state.yaml").write_text(
        audited, encoding="utf-8", newline="\n"
    )

    status_sync = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_STATUS_SYNCHRONIZED_AFTER_JOB_18658301",
        "backup_directory": str(backup.relative_to(ROOT)),
        "updated_files": [
            "PROJECT_STATUS.md",
            "NEXT_IMMEDIATE_STEP.md",
            "ROADMAP.md",
            "COMPUTE_EXECUTION_STATUS.md",
            "NIBI_FR3_EXECUTION_SUPERSEDED.md",
            "config/current_audited_state.yaml",
        ],
        "next_gate": cfg["next_gate"],
    }
    (evidence / "STATUS_SYNC.json").write_text(
        json.dumps(status_sync, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("ONE-SEED STATUS AND DYNAMIC CONTRACT SYNC: PASS")
    print(json.dumps(status_sync, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
