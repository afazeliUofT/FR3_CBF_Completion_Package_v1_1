#!/usr/bin/env python3
"""Column-domain contract for candidate-v4.3 campaign summaries."""
from __future__ import annotations

from collections.abc import Iterable
import numpy as np
import pandas as pd

CANDIDATE = "candidate_v4_3_floor_feasibility_repair"

COMMON_NUMERIC_COLUMNS = [
    "long_violation_seconds",
    "short_violation_seconds",
    "long_maximum_excess_db",
    "short_maximum_excess_db",
    "eligible_floor_violation_user_intervals",
    "eligible_floor_violation_user_seconds",
    "total_normalized_floor_shortfall",
    "final_moving_pf_utility",
    "duration_weighted_mean_moving_pf_utility",
    "protected_active_eligible_p05_bps_hz",
    "protected_active_eligible_geometric_mean_bps_hz",
    "total_active_eligible_p05_bps_hz",
    "total_active_eligible_geometric_mean_bps_hz",
    "sector_mute_interval_count",
    "intervals_with_any_sector_mute",
    "maximum_muted_sector_count",
    "runtime_seconds",
    "pass_slot",
    "protected_sample_count",
    "interval_count",
    "campaign_seed",
    "array_index",
]

CANDIDATE_ONLY_NUMERIC_COLUMNS = [
    "candidate_q0_envelope_deployable_actions",
    "candidate_unresolved_deployable_intervals",
    "candidate_network_wide_shutdown_intervals",
    "candidate_maximum_mutable_sector_count",
    "candidate_maximum_external_interferers_per_violating_user",
    "candidate_maximum_eess_backoff_sectors",
    "candidate_maximum_strict_post_mode_power_ratio",
    "candidate_maximum_q0_power_envelope_ratio",
    "candidate_maximum_normalized_floor_shortfall",
    "candidate_baseline_noop_intervals",
    "candidate_local_grid_repair_intervals",
    "candidate_local_stream_repair_intervals",
    "candidate_local_table_build_seconds_sum",
    "candidate_repair_solver_seconds_sum",
    "candidate_local_table_build_seconds_max",
    "candidate_repair_solver_seconds_max",
    "candidate_repair_solver_seconds_p95_nonzero",
    "candidate_changed_stream_coefficient_count_sum",
    "candidate_changed_sector_interval_count_sum",
    "candidate_maximum_changed_stream_coefficients_per_interval",
    "candidate_maximum_changed_sectors_per_interval",
    "candidate_incremental_float32_payload_lower_bound_bytes_sum",
]

CANDIDATE_ONLY_REQUIRED_COLUMNS = [
    "candidate_strict_local_scope_gate",
    "candidate_strict_post_mode_power_gate",
    "candidate_information_exchange_locality_certified",
    "candidate_action_scope_locality_verified",
    "candidate_global_oracles_classification_only",
    "candidate_payload_claim_boundary",
] + CANDIDATE_ONLY_NUMERIC_COLUMNS


def _require_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"CELL_SUMMARY is missing required columns: {missing}")


def validate_cell_summary_numeric_domains(
    cells: pd.DataFrame,
    *,
    candidate_id: str = CANDIDATE,
) -> dict[str, int | str]:
    """Validate finite common fields and intentional candidate-only N/A fields.

    Candidate-only numeric fields are semantically not applicable to the eight
    comparator methods. Pandas serializes those blank CSV cells as NaN. They are
    therefore required to be finite on candidate rows and NaN on comparator
    rows; treating all numeric NaNs as data corruption is a validator defect.
    """
    _require_columns(cells, ["method_id"] + COMMON_NUMERIC_COLUMNS)
    _require_columns(cells, CANDIDATE_ONLY_REQUIRED_COLUMNS)

    common = cells[COMMON_NUMERIC_COLUMNS].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(common.to_numpy(dtype=float)).all():
        bad = np.argwhere(~np.isfinite(common.to_numpy(dtype=float)))
        row, col = map(int, bad[0])
        raise ValueError(
            "CELL_SUMMARY common numeric field is non-finite: "
            f"row={row}, column={COMMON_NUMERIC_COLUMNS[col]}"
        )

    candidate_mask = cells["method_id"].astype(str).eq(candidate_id)
    if int(candidate_mask.sum()) == 0:
        raise ValueError("CELL_SUMMARY has no candidate rows")

    candidate_numeric = cells.loc[
        candidate_mask, CANDIDATE_ONLY_NUMERIC_COLUMNS
    ].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(candidate_numeric.to_numpy(dtype=float)).all():
        bad = np.argwhere(~np.isfinite(candidate_numeric.to_numpy(dtype=float)))
        row, col = map(int, bad[0])
        raise ValueError(
            "candidate-only numeric field is non-finite on a candidate row: "
            f"candidate_row={row}, column={CANDIDATE_ONLY_NUMERIC_COLUMNS[col]}"
        )

    comparator_numeric = cells.loc[
        ~candidate_mask, CANDIDATE_ONLY_NUMERIC_COLUMNS
    ]
    if not comparator_numeric.isna().all().all():
        populated = [
            column
            for column in CANDIDATE_ONLY_NUMERIC_COLUMNS
            if comparator_numeric[column].notna().any()
        ]
        raise ValueError(
            "candidate-only numeric fields must be blank/NaN on comparator rows: "
            f"{populated}"
        )

    for column in [
        "candidate_strict_local_scope_gate",
        "candidate_strict_post_mode_power_gate",
        "candidate_payload_claim_boundary",
    ]:
        if cells.loc[candidate_mask, column].isna().any():
            raise ValueError(f"candidate-only field missing on candidate row: {column}")

    return {
        "status": "PASS",
        "row_count": int(len(cells)),
        "candidate_row_count": int(candidate_mask.sum()),
        "comparator_row_count": int((~candidate_mask).sum()),
        "intentional_candidate_only_na_count": int(
            comparator_numeric.isna().to_numpy().sum()
        ),
    }
