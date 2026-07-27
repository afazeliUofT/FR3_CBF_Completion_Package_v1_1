#!/usr/bin/env python3
"""Freeze the distributed IA-RZF/leakage-budget architecture and update status."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

from _bootstrap import ROOT


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/distributed_ia_rzf_architecture.yaml"
    )
    args = parser.parse_args()
    cfg_path = ROOT / args.config
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    inp = {key: ROOT / value for key, value in cfg["inputs"].items()}
    out = ROOT / cfg["outputs"]["work_dir"]
    out.mkdir(parents=True, exist_ok=True)

    required = [
        inp["reference_screen_decision_json"],
        inp["reference_screen_validation_json"],
        inp["sector_static_csv"],
        inp["earth_station_gain_csv_gz"],
        inp["bs_sectors_csv"],
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    screen = json.loads(
        inp["reference_screen_decision_json"].read_text(encoding="utf-8")
    )
    validation = json.loads(
        inp["reference_screen_validation_json"].read_text(encoding="utf-8")
    )
    expected = cfg["expected"]
    assert screen["status"] == "REFERENCE_SCREEN_READY_FOR_HUMAN_REVIEW"
    assert validation["status"] == "PASS_REVIEW_REQUIRED"
    assert screen["site_count"] == int(expected["site_count"])
    assert screen["sector_count"] == int(expected["sector_count"])
    assert screen["protected_sample_count"] == int(
        expected["protected_sample_count"]
    )
    assert screen["aggregate_row_count"] == int(expected["aggregate_row_count"])

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN_DISTRIBUTED_ARCHITECTURE_NOT_PAPER_RESULT",
        "claim_boundary": cfg["claim_boundary"]["architecture"],
        "main_operational_method": (
            "LOCAL_RZF_PLUS_CLOSED_FORM_CERTIFIED_LEAKAGE_PROJECTION"
        ),
        "wmmse_disposition": {
            "main_operational_method": "REMOVED",
            "reason": (
                "The deployable architecture must not require network-wide "
                "instantaneous UE CSI, joint precoder computation, or iterative "
                "inter-BS beam exchange."
            ),
            "optional_small_scale_role": (
                "A centralized optimizer may be retained only as a labelled "
                "small-network upper bound, not as the proposed architecture."
            ),
        },
        "information_partition": {
            "slow_budget_layer_knows": cfg["distributed_architecture"][
                "coordinator_receives"
            ],
            "slow_budget_layer_never_knows": cfg["distributed_architecture"][
                "coordinator_never_receives"
            ],
            "local_bs_knows": [
                "local UE CSI",
                "local incumbent steering direction",
                "local scalar leakage budget",
                "local previous certified action",
            ],
        },
        "local_precoder": {
            "baseline": "local regularized zero forcing",
            "safety_action": (
                "closed-form minimum-Frobenius projection of the incumbent-"
                "direction component"
            ),
            "power_property": "projection never increases BS transmit power",
            "computation": "one local RZF solve plus rank-one projection",
        },
        "aggregate_certificate": {
            "condition": (
                "Every BS enforces I_b(t)<=beta_b(t), beta_b(t)>=0, and "
                "sum_b beta_b(t)<=I_max(t)-margin(t)."
            ),
            "conclusion": (
                "The aggregate received interference satisfies "
                "sum_b I_b(t)<=I_max(t)-margin(t)."
            ),
            "requires_inter_bs_ue_csi": False,
            "requires_joint_beam_computation": False,
        },
        "timescales": {
            "local_precoder_slots": int(
                cfg["distributed_architecture"][
                    "local_precoder_update_period_slots"
                ]
            ),
            "budget_update_slots": int(
                cfg["distributed_architecture"]["budget_update_period_slots"]
            ),
            "between_budget_updates": "hold the last certified local budget",
        },
        "reference_screen_context": {
            "global_maximum_interference_dbw_per_10mhz": screen[
                "global_maximum_aggregate_interference_dbw_per_10mhz"
            ],
            "global_short_backoff_db": screen[
                "global_maximum_required_short_backoff_db"
            ],
            "interpretation": (
                "The completed 57-sector full-load result remains a severe "
                "stress envelope used to size budgets and active sets."
            ),
        },
        "next_gate": cfg["next_gate"]["name"],
    }
    write_json(out / "DISTRIBUTED_IA_RZF_ARCHITECTURE_DECISION.json", decision)

    docs = ROOT / "docs"
    paper = ROOT / "paper_ready"
    docs.mkdir(parents=True, exist_ok=True)
    paper.mkdir(parents=True, exist_ok=True)

    architecture_md = r"""# Distributed incumbent-aware local precoding

## Operational architecture

Each BS computes its own regularized zero-forcing precoder from local UE CSI.
A slow safety layer sends only one scalar received-interference budget to each
BS. The slow layer never receives UE channel vectors or complex precoders.

Let \(W_b^0\) be the nominal local RZF precoder, \(a_b\) the local steering
vector toward the earth station, and \(\kappa_b(t)\) the slow propagation and
earth-station gain factor. The received contribution is

\[
I_b(t)=\kappa_b(t)\|a_b^H W_b(t)\|_2^2.
\]

The local budget \(\beta_b(t)\) gives the transmit-domain target

\[
\gamma_b(t)=\beta_b(t)/\kappa_b(t).
\]

With \(u_b=a_b/\|a_b\|\), decompose

\[
W_b^0=W_{b,\perp}^0+W_{b,\parallel}^0,
\qquad
W_{b,\parallel}^0=u_bu_b^H W_b^0.
\]

The minimum-Frobenius local repair is

\[
W_b^{\rm safe}
=
W_{b,\perp}^0+s_bW_{b,\parallel}^0,
\qquad
s_b=
\min\!\left\{
1,\sqrt{\frac{\gamma_b}{\|a_b^H W_b^0\|_2^2}}
\right\}.
\]

It is closed form, needs no inter-BS CSI, and never increases BS power.

## Aggregate certificate

When every BS enforces \(I_b(t)\le\beta_b(t)\), and the slow layer enforces

\[
\sum_b\beta_b(t)\le I_{\max}(t)-m(t),
\]

then

\[
\sum_b I_b(t)\le I_{\max}(t)-m(t).
\]

The aggregate guarantee therefore follows from independent local actions and a
certified scalar-budget sum.

## Rate-limited implementation

- Local UE precoding can follow the normal scheduler/CSI timescale.
- Scalar budgets change on a slower RRM timescale.
- Between updates, each BS holds the last certified budget.
- On missing or stale messages, each BS uses a preloaded safe schedule or local
  power-backoff fallback.
- Hybrid/codebook implementations must re-evaluate the actual transmitted
  composite precoder after quantization/factorization.

## Claim boundary

RZF, null steering, and Euclidean projection are not individually new. The
paper contribution must be the certified aggregate-to-local decomposition,
dynamic geometry-aware budgets, delayed/rate-limited updates, robustness,
hybrid re-verification, and the resulting safety/utility/runtime evidence.
"""
    (docs / "DISTRIBUTED_IA_RZF_ARCHITECTURE.md").write_text(
        architecture_md, encoding="utf-8", newline="\n"
    )

    latex = r"""\subsection{Distributed Local Precoding with Certified Leakage Budgets}
Each base station (BS) computes its nominal regularized zero-forcing precoder
$\mathbf W_b^0[k]$ using only its locally estimated user channels.  The slow
coordination layer does not collect user channel vectors or complex
precoders.  It sends BS $b$ only a scalar received-interference budget
$\beta_b[k]$ and a validity interval.

Let $\mathbf a_b$ denote the local array steering vector toward the protected
earth station and let $\kappa_b[k]$ collect the validated terrestrial
propagation gain, spectral overlap, element response, and earth-station receive
gain.  The received contribution of BS $b$ is
\begin{equation}
 I_b[k]=\kappa_b[k]\left\|\mathbf a_b^H\mathbf W_b[k]\right\|_2^2.
\end{equation}
The local transmit-domain leakage limit is
$\gamma_b[k]=\beta_b[k]/\kappa_b[k]$.

Define $\mathbf u_b=\mathbf a_b/\|\mathbf a_b\|_2$ and
$\mathbf W_{b,\parallel}^0=\mathbf u_b\mathbf u_b^H\mathbf W_b^0$.  The
minimum-Frobenius local safety repair is
\begin{equation}
 \mathbf W_b^{\mathrm safe}
 =
 \mathbf W_b^0-(1-s_b)\mathbf W_{b,\parallel}^0,
 \quad
 s_b=\min\!\left\{
 1,\sqrt{\frac{\gamma_b}
 {\|\mathbf a_b^H\mathbf W_b^0\|_2^2}}
 \right\}.
\end{equation}
The orthogonal component of the nominal precoder is unchanged.  Consequently,
the repair is the Euclidean projection onto the local leakage set and cannot
increase transmit power.

\begin{proposition}[Distributed aggregate certificate]
If each BS independently satisfies $I_b[k]\leq\beta_b[k]$, the budgets are
nonnegative, and
\begin{equation}
 \sum_b\beta_b[k]\leq I_{\max}[k]-m[k],
\end{equation}
then
\begin{equation}
 \sum_b I_b[k]\leq I_{\max}[k]-m[k].
\end{equation}
\end{proposition}
\begin{proof}
Summing the local inequalities gives
$\sum_b I_b[k]\leq\sum_b\beta_b[k]$, and the budget-sum condition gives the
result.
\end{proof}

The budget layer operates more slowly than local precoding.  Between budget
updates, each BS holds its last certified budget.  A stale-message fallback
uses a preloaded geometry-indexed safe schedule or local power backoff.
"""
    (paper / "distributed_ia_rzf_system_model.tex").write_text(
        latex, encoding="utf-8", newline="\n"
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"status_before_distributed_ia_rzf_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for relative in [
        "PROJECT_STATUS.md",
        "NEXT_IMMEDIATE_STEP.md",
        "config/current_audited_state.yaml",
    ]:
        source = ROOT / relative
        if source.is_file():
            shutil.copy2(source, backup / source.name)

    project_status = """# Current Project Status

## Status date

27 July 2026

## Status in one sentence

The standards/data foundation, validated propagation engine, E3 geometry, all
19 terrestrial paths, mechanism audit, and 57-sector full-load stress screen
are complete. WMMSE has been removed as the main operational architecture.
The proposed deployable method is distributed local RZF plus a closed-form
local incumbent-leakage projection under certified slowly updated scalar
per-BS budgets.

## Completed

- Operator-independent standards and claim boundary.
- Public TAFL pairing, terrain processing, P.530/S1 analysis.
- P.452-18 v18.0 reference validation under MATLAB R2026a.
- E3 earth-station record, archived pass, SA.509 pattern, 19-site/57-sector
  modelled layout.
- Manual review of all 19 terrain paths and 798-row P.452 audit.
- P.452 mechanism-isolation audit.
- 57-sector, 587-sample, 84-scenario full-load reference feasibility screen.
- Distributed architecture decision: local RZF, local leakage projection, and
  certified scalar leakage budgets without network-wide UE CSI.

## Current scientific gate

Build the standards-aligned 57-sector local-channel experiment:

1. generate reproducible local UE channels and user layouts;
2. implement local RZF and hybrid/codebook variants;
3. verify each actual transmitted composite precoder against its local budget;
4. compare static, myopic, virtual-queue, and predictive/CBF budget updates
   under identical information, latency, and update-rate limits;
5. report cellular rates, local/aggregate leakage, action changes, runtime, and
   feasibility without using a central joint beamformer.

## Remaining major paper gates

1. Complete the paper-grade E3 distributed-beam and dynamic-budget experiment.
2. E1 real static fixed-service continuity experiment.
3. E2 dynamic rate-limit trap.
4. Held-out uncertainty calibration.
5. Layered runtime and scalability evidence.
6. Statistical campaign, confidence intervals, and ablations.
7. Results-complete manuscript, reproducibility release, and adversarial review.

## Claim boundaries

- The full-load 57-sector screen is a severe reference envelope, not a paper
  result or compliance determination.
- WMMSE is not the proposed operational method.
- RZF and projection are established ingredients; novelty must come from the
  certified dynamic budget architecture and evidence.
- No O-RAN compliance claim is made without implemented interfaces and measured
  timing.
"""
    (ROOT / "PROJECT_STATUS.md").write_text(
        project_status, encoding="utf-8", newline="\n"
    )

    next_step = """# Next Immediate Step

## Gate

Standards-aligned 57-sector local-channel and distributed IA-RZF experiment.

## Frozen architecture

- Each BS uses only local UE CSI.
- Nominal local beamforming is RZF or a standards-compatible hybrid/codebook
  implementation.
- A closed-form local projection enforces one scalar incumbent-leakage budget.
- The slow layer exchanges scalar leakage/utility telemetry and scalar budgets,
  never UE channel vectors or complex precoders.
- Nonnegative local budgets sum to the aggregate protected-receiver allowance.

## Required sequence

1. Freeze a standards-aligned local channel/user model and exact software
   versions.
2. Generate local nominal RZF beams for the frozen 57 sectors.
3. Independently reconstruct local rates and transmit powers.
4. Apply the certified local leakage projection.
5. Implement static, myopic, queue-based, and predictive/CBF budget schedules
   with identical update periods, delays, and information.
6. Include realistic activity/load cases rather than only all-sector full load.
7. Re-verify the actual hybrid/codebook composite precoder when used.
8. Repeat across passes, user seeds, load levels, and uncertainty epochs.

## Stop condition

Do not call E3 paper-grade until actual local channels, composite beams, UE
rates, loading, rate-limited budget actions, zero-slack safety, runtime, and
statistical repetitions are all present.
"""
    (ROOT / "NEXT_IMMEDIATE_STEP.md").write_text(
        next_step, encoding="utf-8", newline="\n"
    )

    audited = f"""schema_version: 3
as_of_date: "2026-07-27"

publication:
  primary_target: IEEE_TWC
  mode: operator_independent

main_operational_architecture:
  status: frozen_not_paper_result
  name: distributed_local_rzf_with_certified_leakage_budgets
  wmmse_main_method: removed
  central_instantaneous_ue_csi: prohibited
  central_joint_precoder: prohibited
  local_precoder: regularized_zero_forcing
  local_safety_action: closed_form_incumbent_leakage_projection
  slow_coordination_payload: scalar_leakage_telemetry_and_scalar_budgets
  aggregate_certificate: sum_of_local_budgets_not_above_aggregate_allowance

e3:
  propagation_and_reference_screen:
    status: complete_reference_only
    sites: 19
    sectors: 57
    protected_samples: 587
    scenarios: 84
    aggregate_rows: 49308
    claim_boundary: severe_full_load_reference_not_paper_result
  next_gate: standards_aligned_57_sector_local_channel_experiment

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

    status_record = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "backup_directory": str(backup.relative_to(ROOT)),
        "updated_files": [
            "PROJECT_STATUS.md",
            "NEXT_IMMEDIATE_STEP.md",
            "config/current_audited_state.yaml",
            "docs/DISTRIBUTED_IA_RZF_ARCHITECTURE.md",
            "paper_ready/distributed_ia_rzf_system_model.tex",
        ],
        "next_gate": cfg["next_gate"]["name"],
    }
    write_json(out / "DISTRIBUTED_ARCHITECTURE_STATUS_SYNC.json", status_record)

    print("DISTRIBUTED IA-RZF ARCHITECTURE FREEZE: PASS")
    print(json.dumps(decision, indent=2))
    print("Next gate:", decision["next_gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
