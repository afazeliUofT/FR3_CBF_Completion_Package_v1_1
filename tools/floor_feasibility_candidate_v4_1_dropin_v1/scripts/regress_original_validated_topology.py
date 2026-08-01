#!/usr/bin/env python3
"""Source-bound compatibility/no-op regression on the validated topology export.

The packaged July-29 export predates the dynamic five-pass dual-criterion
controller and therefore cannot reproduce the seed-43999 repair run.  This gate
checks what the export can establish without overclaiming:

* immutable source validation is PASS;
* candidate-v4.1's fixed-beam rate formula reconstructs the stored nominal rates;
* the frozen floor system accepts the nominal all-stream action as an exact no-op;
* the source validator's common-scale incumbent-safety result remains bound;
* an independent reconstruction from stored float32-derived mode coefficients
  agrees within the export's numerical reconstruction envelope.

The reconstruction tolerance below is not a fairness or EESS policy tolerance
and is never used by the seed-43999 candidate safety gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from fr3_cbf.floor_feasibility_repair import (
    exact_eess_ratio_from_stream_scale,
    exact_rates_from_stream_scale,
    floor_system_for_stream_scales,
    sector_mapping,
    solve_continuous_l1,
)


EXPORT_RECONSTRUCTION_TOLERANCE = 3e-6


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.data_root).resolve()

    def load(name: str) -> np.ndarray:
        return np.load(root / name, allow_pickle=False)

    validation = json.loads(
        (root / "FULL_TOPOLOGY_EXPORT_VALIDATION_V4.json").read_text(
            encoding="utf-8"
        )
    )
    expected_status = "PASS_CONTROLLER_READY_FULL_TOPOLOGY_EXPORT_VALIDATION_V4"
    assert validation["status"] == expected_status
    source_common_scale = validation["checks"]["common_scale_aggregate_safety"]
    assert source_common_scale["pass"] is True

    serving = load("serving_bs_index.npy").astype(np.int64)
    stream = load("serving_stream_index.npy").astype(np.int64)
    nominal = load("nominal_total_weighted_rate_per_user.npy")
    other = load("other_frequency_weighted_rate_per_user.npy")
    nominal_protected = load("nominal_protected_rate_per_user.npy")
    a0 = load("protected_amp_perpendicular.npy")
    a1 = load("protected_amp_pol1.npy")
    a2 = load("protected_amp_pol2.npy")
    noise = float(load("noise_power_by_frequency_w.npy")[4])
    protected_weight = float(load("frequency_weights.npy")[4])
    active = np.ones(len(nominal), dtype=bool)

    gain_nominal = np.abs(a0 + a1 + a2) ** 2
    reconstructed_total, reconstructed_protected = exact_rates_from_stream_scale(
        gain_nominal,
        np.ones(gain_nominal.shape[1:]),
        other,
        active,
        serving,
        stream,
        noise,
        protected_weight,
    )
    total_error = float(np.max(np.abs(reconstructed_total - nominal)))
    protected_error = float(
        np.max(np.abs(reconstructed_protected - nominal_protected))
    )
    assert total_error < 6e-6
    assert protected_error < 6e-5

    eligible = nominal >= 0.1
    floors = np.zeros_like(nominal)
    floors[eligible] = np.maximum(0.1, 0.9 * nominal[eligible])
    floor_system = floor_system_for_stream_scales(
        gain_nominal,
        other,
        active,
        eligible,
        floors,
        serving,
        stream,
        noise,
        protected_weight,
    )
    sector_outcome = solve_continuous_l1(
        floor_system,
        sector_mapping(57, 4),
        np.zeros(57 * 4),
        np.ones(57),
        np.zeros(57),
        np.ones(57),
    )
    assert sector_outcome.feasible
    assert sector_outcome.status == "FEASIBLE_BASELINE_NOOP"

    common_scale = load("common_scale_reference.npy")
    common_rate = load("common_scale_user_rate.npy")
    common_floor_violations = common_rate[:, eligible] < (
        floors[eligible][None, :] - 1e-12
    )
    assert not np.any(common_floor_violations)
    minimum_common_ratio = float(
        np.min(common_rate[:, eligible] / floors[eligible][None, :])
    )

    coefficients = load("protected_mode_coefficients.npy")
    per_stream_leakage = np.sum(np.abs(coefficients) ** 2, axis=1)
    kappa = load("kappa_time_sector.npy")
    allowance = load("aggregate_allowance_w.npy")
    reconstructed_common_eess = np.empty(len(common_scale), dtype=float)
    for second, amplitude_scale in enumerate(common_scale):
        reconstructed_common_eess[second] = exact_eess_ratio_from_stream_scale(
            kappa[second : second + 1],
            per_stream_leakage,
            np.full((57, 4), amplitude_scale**2),
            allowance[second : second + 1],
            0.0,
        )[0]
    maximum_reconstructed_ratio = float(np.max(reconstructed_common_eess))
    assert maximum_reconstructed_ratio <= 1.0 + EXPORT_RECONSTRUCTION_TOLERANCE

    report = {
        "schema_version": 2,
        "status": "PASS_ORIGINAL_VALIDATED_TOPOLOGY_COMPATIBILITY_REGRESSION",
        "source_validation_status": validation["status"],
        "source_common_scale_aggregate_safety": {
            "pass": bool(source_common_scale["pass"]),
            "maximum_safe_minus_allowance_w": float(
                source_common_scale["maximum_safe_minus_allowance_w"]
            ),
        },
        "eligible_user_count": int(eligible.sum()),
        "nominal_rate_reconstruction_max_abs_error": total_error,
        "protected_rate_reconstruction_max_abs_error": protected_error,
        "nominal_floor_candidate": sector_outcome.status,
        "common_scale_floor_violation_user_seconds": int(
            np.sum(common_floor_violations)
        ),
        "minimum_common_scale_floor_ratio": minimum_common_ratio,
        "maximum_reconstructed_common_scale_eess_ratio": (
            maximum_reconstructed_ratio
        ),
        "export_reconstruction_tolerance": EXPORT_RECONSTRUCTION_TOLERANCE,
        "export_reconstruction_tolerance_scope": (
            "stored float32-derived mode-coefficient reconstruction only; not a "
            "fairness/EESS gate tolerance and not used by seed-43999 candidate-v4.1"
        ),
        "candidate_change": "NOOP_ON_ORIGINAL_VALIDATED_NOMINAL_FLOOR_SYSTEM",
        "dynamic_dual_criterion_candidate_run": False,
        "dynamic_dual_criterion_reason": (
            "pre-campaign export has one protected criterion/pass and no five-pass "
            "controller trajectories"
        ),
        "claim_boundary": (
            "ONE_VALIDATED_FULL_TOPOLOGY_COMPATIBILITY_REGRESSION_NOT_"
            "STATISTICAL_NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE"
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print("ORIGINAL_VALIDATED_INPUT_BINDING=PASS")
    print("ORIGINAL_VALIDATION_V4_STATUS=" + validation["status"])
    print("ORIGINAL_VALIDATED_COMPATIBILITY_REGRESSION=PASS")
    print("ORIGINAL_CANDIDATE_NOMINAL_FLOOR_NOOP=PASS")
    print("ORIGINAL_SOURCE_COMMON_SCALE_SAFETY_GATE=PASS")
    print(
        "ORIGINAL_COMMON_SCALE_EXPORT_RECONSTRUCTION="
        "PASS_WITH_DECLARED_FLOAT32_RECONSTRUCTION_TOLERANCE"
    )
    print(
        "ORIGINAL_EXPORT_RECONSTRUCTION_TOLERANCE="
        f"{EXPORT_RECONSTRUCTION_TOLERANCE:.17g}"
    )
    print(
        "ORIGINAL_EXACT_DYNAMIC_DUAL_CRITERION_CANDIDATE="
        "NOT_APPLICABLE_TO_PRECAMPAIGN_EXPORT"
    )
    print("ORIGINAL_DISTINCT_SHORT_TERM_CRITERION_ASSERTED=NO")
    print("CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
