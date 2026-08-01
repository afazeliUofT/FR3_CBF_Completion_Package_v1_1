#!/usr/bin/env python3
"""Source-bound regression on the original validated full-topology export.

The July-29 export predates the dynamic five-pass dual-criterion controller, so
it cannot reproduce the preserved seed-43999 candidate trajectory.  It does,
however, contain the original 128-port protected-tone RZF precoder and both
stored incumbent steering modes.  This gate therefore establishes, without
promoting the export to confirmatory evidence, that:

* the immutable source validation is PASS;
* candidate-v4.2 reconstructs the stored nominal rates;
* the unchanged floor accepts the nominal action as a no-op;
* the reviewed common-scale incumbent-safety result remains bound;
* the reviewed protected-mode decomposition is independently reconstructed;
* for both frozen 65/3 dB mode orientations, post-mode conducted power is no
  greater than the original q=0 nominal conducted-power envelope; and
* the candidate's exact decision-space q=0 power rows agree with direct
  conducted-power evaluation on these real 128-port matrices.

The declared reconstruction tolerance concerns only float32-derived archived
arrays.  It is not a fairness/EESS policy tolerance and is not used by the
seed-43999 candidate safety gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from fr3_cbf.floor_feasibility_repair import (
    exact_eess_ratio_from_stream_scale,
    exact_rates_from_stream_scale,
    floor_system_for_stream_scales,
    local_sector_power_budget_system,
    sector_mapping,
    solve_continuous_l1,
    sparse_hybrid_mapping,
    stream_power_envelopes,
)


EXPORT_RECONSTRUCTION_TOLERANCE = 3e-6
PROTECTED_FREQUENCY_INDEX = 4
FROZEN_MODE_PATTERNS_DB = {
    "POL1_65_POL2_3": (65.0, 3.0),
    "POL1_3_POL2_65": (3.0, 65.0),
}
FROZEN_BASELINE_BACKOFF_DB = 3.0


def _reconstruct_reviewed_mode_matrices(
    nominal_precoder: np.ndarray,
    steering_pol1: np.ndarray,
    steering_pol2: np.ndarray,
) -> SimpleNamespace:
    """Reconstruct the exact projector decomposition used by the export."""
    w = np.asarray(nominal_precoder)
    a1 = np.asarray(steering_pol1)
    a2 = np.asarray(steering_pol2)
    if w.ndim != 3 or a1.shape != a2.shape or a1.shape != w.shape[:2]:
        raise ValueError("precoder/steering dimensions do not align")
    n1 = np.linalg.norm(a1, axis=1)
    n2 = np.linalg.norm(a2, axis=1)
    if np.any(n1 <= 0.0) or np.any(n2 <= 0.0):
        raise ValueError("stored steering vector has zero norm")
    u1 = a1 / n1[:, None]
    u2 = a2 / n2[:, None]
    coefficient1 = np.einsum("bm,bmk->bk", u1.conj(), w, optimize=True)
    coefficient2 = np.einsum("bm,bmk->bk", u2.conj(), w, optimize=True)
    p1 = u1[:, :, None] * coefficient1[:, None, :]
    p2 = u2[:, :, None] * coefficient2[:, None, :]
    p0 = w - p1 - p2
    return SimpleNamespace(
        perpendicular=p0,
        polarization_1=p1,
        polarization_2=p2,
    )


def _power_envelope_audit(
    *,
    matrices: SimpleNamespace,
    nominal_precoder: np.ndarray,
    stored_precoder_power_sector: np.ndarray,
    stored_transmit_power: float,
) -> dict[str, object]:
    sector_count, _port_count, stream_count = nominal_precoder.shape
    q0_direct_stream = np.sum(np.abs(nominal_precoder) ** 2, axis=1).astype(float)
    _unused_actual, q0_reconstructed_stream = stream_power_envelopes(
        matrices, np.zeros((sector_count, 2), dtype=float)
    )
    q0_stream_error = float(
        np.max(np.abs(q0_reconstructed_stream - q0_direct_stream))
    )
    q0_sector = np.sum(q0_reconstructed_stream, axis=1)
    stored_sector = np.asarray(stored_precoder_power_sector, dtype=float)
    if stored_sector.shape != (sector_count,):
        raise ValueError("stored protected precoder power has the wrong shape")
    stored_sector_error = float(np.max(np.abs(q0_sector - stored_sector)))
    transmit_power_error = float(
        np.max(np.abs(q0_sector - float(stored_transmit_power)))
    )
    assert q0_stream_error <= 2e-6
    assert stored_sector_error <= 2e-6
    assert transmit_power_error <= 2e-6

    baseline = np.full(
        sector_count,
        10.0 ** (-FROZEN_BASELINE_BACKOFF_DB / 10.0),
        dtype=float,
    )
    mapping, offset, baseline_decision, mutable_names = sparse_hybrid_mapping(
        baseline,
        tuple(range(sector_count)),
        tuple(),
        stream_count=stream_count,
    )
    assert len(mutable_names) == sector_count * stream_count
    pattern_reports: dict[str, object] = {}
    global_max_ratio = 0.0
    global_min_mode_to_q0 = 1.0
    nonvacuous_headroom_sectors = 0

    for pattern_name, pair in FROZEN_MODE_PATTERNS_DB.items():
        q_db = np.tile(np.asarray(pair, dtype=float), (sector_count, 1))
        actual_stream, nominal_q0_stream = stream_power_envelopes(matrices, q_db)
        q0_match_error = float(
            np.max(np.abs(nominal_q0_stream - q0_reconstructed_stream))
        )
        assert q0_match_error <= 1e-13

        actual_sector = np.sum(actual_stream, axis=1)
        nominal_sector = np.sum(nominal_q0_stream, axis=1)
        mode_to_q0 = np.divide(
            actual_sector,
            nominal_sector,
            out=np.zeros_like(actual_sector),
            where=nominal_sector > 0.0,
        )
        assert np.all(mode_to_q0 <= 1.0 + 1e-11)

        budget = local_sector_power_budget_system(
            mapping=mapping,
            offset=offset,
            actual_stream_power=actual_stream,
            envelope_stream_power=nominal_q0_stream,
            baseline_sector_scale=baseline,
            constrained_sectors=tuple(range(sector_count)),
            label_prefix="q0_nominal_power_envelope",
        )
        row_lhs = budget.a_ub @ baseline_decision
        assert np.all(row_lhs <= budget.b_ub + 1e-12)
        baseline_stream_scale = (
            offset + mapping @ baseline_decision
        ).reshape(sector_count, stream_count)
        direct_ratio = np.divide(
            np.sum(actual_stream * baseline_stream_scale, axis=1),
            baseline * nominal_sector,
            out=np.zeros(sector_count, dtype=float),
            where=(baseline * nominal_sector) > 0.0,
        )
        row_excess = float(np.max(row_lhs - budget.b_ub))
        max_ratio = float(np.max(direct_ratio))
        assert max_ratio <= 1.0 + 1e-11

        # Demonstrate that the corrected action space is non-vacuous on the
        # real matrices: concentrating the allowed q=0-envelope budget into one
        # fixed RZF stream can raise that stream above the reviewed scalar while
        # remaining within the exact physical sector cap.  This is an action-
        # space check only; it makes no rate or EESS claim for this constructed
        # allocation.
        concentrated = np.zeros_like(actual_stream)
        uplifted = 0
        maximum_uplift = 1.0
        for sector in range(sector_count):
            positive = np.flatnonzero(actual_stream[sector] > 0.0)
            if len(positive) == 0:
                continue
            target = int(positive[np.argmin(actual_stream[sector, positive])])
            cap = baseline[sector] * nominal_sector[sector]
            concentrated[sector, target] = min(
                1.0, cap / actual_stream[sector, target]
            )
            if concentrated[sector, target] > baseline[sector] + 1e-12:
                uplifted += 1
                maximum_uplift = max(
                    maximum_uplift,
                    float(concentrated[sector, target] / baseline[sector]),
                )
        concentrated_ratio = np.divide(
            np.sum(actual_stream * concentrated, axis=1),
            baseline * nominal_sector,
            out=np.zeros(sector_count, dtype=float),
            where=(baseline * nominal_sector) > 0.0,
        )
        assert float(np.max(concentrated_ratio)) <= 1.0 + 1e-11

        pattern_reports[pattern_name] = {
            "mode_command_db": list(pair),
            "minimum_mode_adjusted_to_q0_sector_power_ratio": float(
                np.min(mode_to_q0)
            ),
            "maximum_mode_adjusted_to_q0_sector_power_ratio": float(
                np.max(mode_to_q0)
            ),
            "maximum_q0_budget_direct_ratio_at_reviewed_scalar": max_ratio,
            "maximum_normalized_budget_row_excess": row_excess,
            "q0_reconstruction_max_abs_error_w_per_stream": q0_match_error,
            "nonvacuous_headroom_sector_count": int(uplifted),
            "maximum_constructed_target_stream_uplift_over_reviewed_scalar": float(
                maximum_uplift
            ),
            "maximum_constructed_q0_power_envelope_ratio": float(
                np.max(concentrated_ratio)
            ),
        }
        global_max_ratio = max(global_max_ratio, max_ratio)
        global_min_mode_to_q0 = min(
            global_min_mode_to_q0, float(np.min(mode_to_q0))
        )
        nonvacuous_headroom_sectors = max(nonvacuous_headroom_sectors, uplifted)

    return {
        "q0_direct_vs_reconstructed_max_abs_error_w_per_stream": q0_stream_error,
        "q0_sector_vs_stored_precoder_power_max_abs_error_w": stored_sector_error,
        "q0_sector_vs_transmit_power_max_abs_error_w": transmit_power_error,
        "frozen_baseline_backoff_db": FROZEN_BASELINE_BACKOFF_DB,
        "frozen_mode_pattern_results": pattern_reports,
        "maximum_q0_nominal_power_envelope_ratio": global_max_ratio,
        "minimum_mode_adjusted_to_q0_sector_power_ratio": global_min_mode_to_q0,
        "maximum_nonvacuous_headroom_sector_count": int(
            nonvacuous_headroom_sectors
        ),
    }


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
    noise = float(load("noise_power_by_frequency_w.npy")[PROTECTED_FREQUENCY_INDEX])
    protected_weight = float(load("frequency_weights.npy")[PROTECTED_FREQUENCY_INDEX])
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

    nominal_precoder_all = load("nominal_precoder_by_frequency.npy")
    nominal_precoder = nominal_precoder_all[PROTECTED_FREQUENCY_INDEX]
    matrices = _reconstruct_reviewed_mode_matrices(
        nominal_precoder,
        load("protected_steering_pol1.npy"),
        load("protected_steering_pol2.npy"),
    )
    power_audit = _power_envelope_audit(
        matrices=matrices,
        nominal_precoder=nominal_precoder,
        stored_precoder_power_sector=load("nominal_precoder_power_w.npy")[
            PROTECTED_FREQUENCY_INDEX
        ],
        stored_transmit_power=float(
            load("transmit_power_by_frequency_w.npy")[PROTECTED_FREQUENCY_INDEX]
        ),
    )

    report = {
        "schema_version": 3,
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
        "q0_physical_power_envelope_audit": power_audit,
        "export_reconstruction_tolerance": EXPORT_RECONSTRUCTION_TOLERANCE,
        "export_reconstruction_tolerance_scope": (
            "stored float32-derived mode-coefficient reconstruction only; not a "
            "fairness/EESS gate tolerance and not used by seed-43999 candidate-v4.2"
        ),
        "candidate_change": (
            "NOOP_ON_ORIGINAL_VALIDATED_NOMINAL_FLOOR_SYSTEM_PLUS_EXACT_"
            "Q0_POWER_ENVELOPE_RECONSTRUCTION"
        ),
        "dynamic_dual_criterion_candidate_run": False,
        "dynamic_dual_criterion_reason": (
            "pre-campaign export has one protected criterion/pass and no five-pass "
            "controller trajectories"
        ),
        "claim_boundary": (
            "ONE_VALIDATED_FULL_TOPOLOGY_COMPATIBILITY_AND_ACTION_ENVELOPE_"
            "REGRESSION_NOT_STATISTICAL_NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE"
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
    print("ORIGINAL_Q0_POWER_ENVELOPE_RECONSTRUCTION=PASS")
    print("ORIGINAL_65DB_3DB_POWER_ENVELOPE_GATE=PASS")
    print(
        "ORIGINAL_MAXIMUM_Q0_NOMINAL_POWER_ENVELOPE_RATIO="
        f"{power_audit['maximum_q0_nominal_power_envelope_ratio']:.17g}"
    )
    print(
        "ORIGINAL_MINIMUM_MODE_ADJUSTED_TO_Q0_POWER_RATIO="
        f"{power_audit['minimum_mode_adjusted_to_q0_sector_power_ratio']:.17g}"
    )
    print(
        "ORIGINAL_NONVACUOUS_Q0_HEADROOM_SECTORS="
        f"{power_audit['maximum_nonvacuous_headroom_sector_count']}"
    )
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
