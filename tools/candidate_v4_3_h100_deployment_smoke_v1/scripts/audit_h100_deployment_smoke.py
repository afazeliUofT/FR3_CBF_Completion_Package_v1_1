#!/usr/bin/env python3
"""Compare the excluded H100 replay with the frozen v4.3 CPU evidence."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
from typing import Any

import numpy as np
import pandas as pd

EXPECTED_STATUS = (
    "PASS_EXCLUDED_SEED43999_CANDIDATE_V4_3_"
    "ALL5_FLOOR_EESS_AND_STRICT_POWER_GATES"
)
PRED = "robust_predictive_constrained_pf_with_sector_selective_fallback"
STATIC = "static_robust_constrained_pf_with_sector_selective_fallback"
NUMERIC_LIMIT = 1e-10


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"invalid env line: {line!r}")
        values[key] = value
    return values


def verify_manifest(base: Path, manifest: Path) -> None:
    result = subprocess.run(
        ["sha256sum", "-c", str(manifest)],
        cwd=base,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"manifest failed: {manifest}\n{result.stdout}\n{result.stderr}"
        )


def infer_eligible(trace: np.lib.npyio.NpzFile) -> np.ndarray:
    seconds = float(np.asarray(trace["interval_lengths"])[0])
    alpha = math.exp(-seconds / 100.0)
    moving = np.asarray(trace["candidate_moving_average_rate"])[0]
    rate = np.asarray(trace["candidate_total_rate"])[0]
    initial = (moving - (1.0 - alpha) * rate) / alpha
    return initial >= 0.1


def gmean_positive(value: np.ndarray) -> float:
    samples = np.asarray(value, dtype=np.float64)
    positive = samples[samples > 0.0]
    if positive.size == 0:
        return 0.0
    return float(np.exp(np.mean(np.log(positive))))


def utility_summary(summary: Path) -> pd.DataFrame:
    with np.load(summary / "CANDIDATE_PASS_0_TRACE.npz", allow_pickle=False) as z:
        eligible = infer_eligible(z)
    if int(np.sum(eligible)) != 205:
        raise AssertionError("eligible-user reconstruction mismatch")
    methods = pd.read_csv(summary / "ALL_METHOD_CELL_SUMMARY.csv")
    rows: list[dict[str, Any]] = []
    for slot in range(5):
        with np.load(
            summary / f"CANDIDATE_PASS_{slot}_TRACE.npz", allow_pickle=False
        ) as z:
            moving = np.asarray(z["candidate_moving_average_rate"], np.float64)
            total = np.asarray(z["candidate_total_rate"], np.float64)
            protected = np.asarray(z["candidate_protected_rate"], np.float64)
            lengths = np.asarray(z["interval_lengths"], np.float64)
            utility = np.log(moving[:, eligible] + 0.001).sum(axis=1)
            active = total[:, eligible] > 0.0
            total_samples = total[:, eligible][active]
            protected_samples = protected[:, eligible][active]
            pred = methods[
                (methods.pass_slot == slot) & (methods.method_id == PRED)
            ].iloc[0]
            static = methods[
                (methods.pass_slot == slot) & (methods.method_id == STATIC)
            ].iloc[0]
            duration = float(np.average(utility, weights=lengths))
            rows.append(
                {
                    "pass_slot": slot,
                    "candidate_final_moving_pf_utility": float(utility[-1]),
                    "candidate_duration_weighted_mean_moving_pf_utility": duration,
                    "candidate_total_active_eligible_p05_bps_hz": float(
                        np.percentile(total_samples, 5.0)
                    ),
                    "candidate_total_active_eligible_geometric_mean_bps_hz": gmean_positive(
                        total_samples
                    ),
                    "candidate_protected_active_eligible_p05_bps_hz": float(
                        np.percentile(protected_samples, 5.0)
                    ),
                    "candidate_protected_active_eligible_positive_geometric_mean_bps_hz": gmean_positive(
                        protected_samples
                    ),
                    "candidate_protected_active_eligible_zero_fraction": float(
                        np.mean(protected_samples <= 0.0)
                    ),
                    "candidate_minus_predictive_final_pf": float(
                        utility[-1] - pred.final_moving_pf_utility
                    ),
                    "candidate_minus_predictive_duration_mean_pf": float(
                        duration - pred.duration_weighted_mean_moving_pf_utility
                    ),
                    "candidate_minus_static_final_pf": float(
                        utility[-1] - static.final_moving_pf_utility
                    ),
                    "candidate_minus_static_duration_mean_pf": float(
                        duration - static.duration_weighted_mean_moving_pf_utility
                    ),
                }
            )
    return pd.DataFrame(rows)


def compare_traces(cpu: Path, h100: Path) -> dict[str, Any]:
    numeric_keys = [
        "q_db",
        "reviewed_sector_scale",
        "integrated_pre_repair_sector_scale",
        "integrated_pre_repair_envelope_ratio",
        "candidate_stream_scale",
        "candidate_sector_equivalent",
        "candidate_total_rate",
        "candidate_protected_rate",
        "candidate_moving_average_rate",
        "candidate_floor_count",
        "candidate_normalized_shortfall",
        "candidate_long_ratio",
        "candidate_short_ratio",
        "interval_lengths",
    ]
    maxima = {key: 0.0 for key in numeric_keys}
    action_exact = True
    for slot in range(5):
        with np.load(
            cpu / f"CANDIDATE_PASS_{slot}_TRACE.npz", allow_pickle=False
        ) as a, np.load(
            h100 / f"CANDIDATE_PASS_{slot}_TRACE.npz", allow_pickle=False
        ) as b:
            for key in numeric_keys:
                av = np.asarray(a[key])
                bv = np.asarray(b[key])
                if av.shape != bv.shape:
                    raise AssertionError(f"pass {slot} {key}: shape mismatch")
                maxima[key] = max(
                    maxima[key],
                    float(np.max(np.abs(av.astype(np.float64) - bv.astype(np.float64))))
                    if av.size
                    else 0.0,
                )
            if not np.array_equal(a["action_class"], b["action_class"]):
                action_exact = False
    hard_keys = numeric_keys
    if any(maxima[key] > NUMERIC_LIMIT for key in hard_keys):
        raise AssertionError(f"H100 replay differs from CPU evidence: {maxima}")
    if not action_exact:
        raise AssertionError("H100 action-class trace differs from CPU evidence")
    return {
        "maximum_absolute_difference_by_array": maxima,
        "action_class_trace_exact": action_exact,
        "numeric_limit": NUMERIC_LIMIT,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu-summary", required=True)
    parser.add_argument("--h100-summary", required=True)
    parser.add_argument("--h100-environment", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-env", required=True)
    parser.add_argument("--utility-csv", required=True)
    args = parser.parse_args()

    cpu = Path(args.cpu_summary).expanduser().resolve()
    h100 = Path(args.h100_summary).expanduser().resolve()
    environment = json.loads(
        Path(args.h100_environment).read_text(encoding="utf-8")
    )
    output_json = Path(args.output_json).expanduser().resolve()
    output_env = Path(args.output_env).expanduser().resolve()
    utility_csv = Path(args.utility_csv).expanduser().resolve()
    for path in (output_json, output_env, utility_csv):
        path.parent.mkdir(parents=True, exist_ok=True)

    verify_manifest(cpu, cpu / "OUTPUT_MANIFEST.sha256")
    verify_manifest(h100, h100 / "OUTPUT_MANIFEST.sha256")
    cpu_status = parse_env(cpu / "RUN_STATUS.env")
    h100_status = parse_env(h100 / "RUN_STATUS.env")
    if cpu_status["CANDIDATE_STATUS"] != EXPECTED_STATUS:
        raise AssertionError("frozen CPU evidence is not a v4.3 pass")
    if h100_status["CANDIDATE_STATUS"] != EXPECTED_STATUS:
        raise AssertionError("H100 replay is not a v4.3 pass")

    hard_fields = [
        "CANDIDATE_LONG_VIOLATION_SECONDS",
        "CANDIDATE_SHORT_VIOLATION_SECONDS",
        "CANDIDATE_FLOOR_VIOLATION_USER_SECONDS",
        "CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS",
        "NETWORK_WIDE_SHUTDOWN_INTERVALS",
        "STRICT_LOCAL_SCOPE_GATE",
        "STRICT_POST_MODE_SELECTED_POWER_GATE",
        "Q0_ENVELOPE_DEPLOYABLE_ACTIONS",
        "Q0_HEADROOM_USED_INTERVALS",
        "STRICT_POST_MODE_STREAM_INFEASIBLE_INTERVALS",
        "STRICT_POST_MODE_STREAM_UNCERTIFIED_INTERVALS",
        "LOCAL_FROZEN_GRID_REPAIRED_INTERVALS",
        "LOCAL_STREAM_POWER_REPAIRED_INTERVALS",
        "LOCAL_STREAM_POWER_PROVEN_INFEASIBLE_INTERVALS",
        "UNRESOLVED_DEPLOYABLE_INTERVALS",
        "MAX_MUTABLE_SECTOR_COUNT",
        "PREDICTIVE_REPRODUCTION_USER_SECONDS",
        "PREDICTIVE_REPRODUCTION_USER_INTERVALS",
        "CANDIDATE_RESIDUAL_USER_COUNT",
        "MAXIMUM_CANDIDATE_NORMALIZED_FLOOR_SHORTFALL",
        "SOLVER_CONSTRAINT_RESERVE",
        "SOLVER_PRIMAL_FEASIBILITY_TOLERANCE",
        "SOLVER_DUAL_FEASIBILITY_TOLERANCE",
        "CHANNEL_RECORD_SHA256",
        "FREQUENCY_RESPONSE_ARRAY_SHA256",
    ]
    for field in hard_fields:
        if h100_status[field] != cpu_status[field]:
            raise AssertionError(
                f"H100/CPU hard-field mismatch for {field}: "
                f"{h100_status[field]} != {cpu_status[field]}"
            )

    if environment["status"] != "PASS_H100_ENVIRONMENT_AND_PRESERVED_CHANNEL_ACCESS":
        raise AssertionError("H100 environment gate failed")
    if environment["channel_regenerated"]:
        raise AssertionError("channel was regenerated")
    if environment.get("controller_replay_execution") != (
        "CPU_NUMPY_SCIPY_HIGHS_ON_H100_NODE"
    ):
        raise AssertionError("controller execution boundary is not explicit")

    comparison = compare_traces(cpu, h100)
    cpu_utility = utility_summary(cpu)
    h100_utility = utility_summary(h100)
    utility_diff = float(
        np.max(
            np.abs(
                cpu_utility.select_dtypes(include=[np.number]).to_numpy()
                - h100_utility.select_dtypes(include=[np.number]).to_numpy()
            )
        )
    )
    if utility_diff > NUMERIC_LIMIT:
        raise AssertionError(f"utility replay mismatch: {utility_diff}")
    h100_utility.to_csv(utility_csv, index=False)

    action = pd.read_csv(h100 / "CANDIDATE_ACTION_INTERVALS.csv")
    repaired = action[action.chosen_action_class != "BASELINE_NOOP"]
    if len(repaired) != 104 or int(repaired.interval_seconds.sum()) != 519:
        raise AssertionError("H100 repair coverage mismatch")
    if not np.all(repaired.strict_local_scope_gate == "PASS"):
        raise AssertionError("H100 action-scope locality failed")

    audit = {
        "schema_version": 1,
        "status": "PASS_EXCLUDED_H100_DEPLOYMENT_SMOKE_V4_3",
        "candidate_version": "v4.3",
        "excluded_seed": 43999,
        "h100_environment": environment,
        "cpu_h100_trace_comparison": comparison,
        "maximum_utility_metric_absolute_difference": utility_diff,
        "candidate_utility_by_pass": h100_utility.to_dict(orient="records"),
        "hard_gates": {
            field: h100_status[field] for field in hard_fields
        },
        "repair_intervals": int(len(repaired)),
        "repair_physical_seconds": int(repaired.interval_seconds.sum()),
        "maximum_mutable_sector_count": int(repaired.mutable_sector_count.max()),
        "maximum_changed_sector_count": int(repaired.changed_sector_count.max()),
        "action_scope_locality_verified": True,
        "information_exchange_locality_certified": False,
        "channel_reused": True,
        "channel_regenerated": False,
        "controller_replay_execution": "CPU_NUMPY_SCIPY_HIGHS_ON_H100_NODE",
        "confirmatory_campaign_authorized": False,
        "claim_boundary": (
            "EXCLUDED_H100_INTEGRATION_SMOKE_NOT_CONFIRMATORY_"
            "NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE"
        ),
        "next_gate": "FREEZE_V4_3_AND_INDEPENDENTLY_REVIEW_CAMPAIGN_READINESS",
    }
    output_json.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    env = {
        "H100_DEPLOYMENT_SMOKE_STATUS": "PASS_EXCLUDED_H100_DEPLOYMENT_SMOKE_V4_3",
        "H100_ENVIRONMENT_GATE": "PASS",
        "H100_CPU_TRACE_REPRODUCTION_GATE": "PASS",
        "H100_ACTION_CLASS_TRACE_EXACT": "PASS",
        "H100_MAXIMUM_TRACE_ABSOLUTE_DIFFERENCE": (
            f"{max(comparison['maximum_absolute_difference_by_array'].values()):.17g}"
        ),
        "H100_MAXIMUM_UTILITY_ABSOLUTE_DIFFERENCE": f"{utility_diff:.17g}",
        "CANDIDATE_LONG_VIOLATION_SECONDS": h100_status[
            "CANDIDATE_LONG_VIOLATION_SECONDS"
        ],
        "CANDIDATE_SHORT_VIOLATION_SECONDS": h100_status[
            "CANDIDATE_SHORT_VIOLATION_SECONDS"
        ],
        "CANDIDATE_FLOOR_VIOLATION_USER_SECONDS": h100_status[
            "CANDIDATE_FLOOR_VIOLATION_USER_SECONDS"
        ],
        "CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS": h100_status[
            "CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS"
        ],
        "STRICT_LOCAL_SCOPE_GATE": h100_status["STRICT_LOCAL_SCOPE_GATE"],
        "STRICT_POST_MODE_SELECTED_POWER_GATE": h100_status[
            "STRICT_POST_MODE_SELECTED_POWER_GATE"
        ],
        "Q0_ENVELOPE_DEPLOYABLE_ACTIONS": h100_status[
            "Q0_ENVELOPE_DEPLOYABLE_ACTIONS"
        ],
        "H100_CHANNEL_REGENERATION": "NO",
        "CONTROLLER_REPLAY_EXECUTION": "CPU_NUMPY_SCIPY_HIGHS_ON_H100_NODE",
        "ACTION_SCOPE_LOCALITY_GATE": "PASS",
        "INFORMATION_EXCHANGE_LOCALITY_CERTIFIED": "NO",
        "CONFIRMATORY_CAMPAIGN_AUTHORIZED": "NO",
        "NEXT_GATE": "FREEZE_V4_3_AND_INDEPENDENTLY_REVIEW_CAMPAIGN_READINESS",
    }
    output_env.write_text(
        "".join(f"{key}={value}\n" for key, value in env.items()),
        encoding="utf-8",
    )
    for key, value in env.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
