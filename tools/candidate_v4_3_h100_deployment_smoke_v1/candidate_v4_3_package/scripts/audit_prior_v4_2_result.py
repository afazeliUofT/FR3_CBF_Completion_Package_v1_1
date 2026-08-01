#!/usr/bin/env python3
"""Reclassify the immutable v4.2 return without changing its evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

EXPECTED_RETURN_SHA = "5665acb504b6751700a9e305baaaba2e47c3bf265825e0accba01b2f532a1e33"


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    root = Path(args.input_root).resolve()
    out = Path(args.output_json).resolve()

    required = [
        "V4_2_RETURN_BINDING.json",
        "RUN_STATUS.env",
        "SCIENTIFIC_VERDICT.json",
        "CANDIDATE_CELL_SUMMARY.csv",
        "AFFECTED_USER_INTERVAL_FEASIBILITY.csv",
        "CANDIDATE_ACTION_INTERVALS.csv",
        "INTERVAL_FEASIBILITY_CERTIFICATES.json",
    ]
    for name in required:
        if not (root / name).is_file():
            raise FileNotFoundError(root / name)

    binding = json.loads((root / "V4_2_RETURN_BINDING.json").read_text())
    status = parse_env(root / "RUN_STATUS.env")
    verdict = json.loads((root / "SCIENTIFIC_VERDICT.json").read_text())
    cells = pd.read_csv(root / "CANDIDATE_CELL_SUMMARY.csv")
    affected = pd.read_csv(root / "AFFECTED_USER_INTERVAL_FEASIBILITY.csv")
    actions = pd.read_csv(root / "CANDIDATE_ACTION_INTERVALS.csv")
    certificates = json.loads(
        (root / "INTERVAL_FEASIBILITY_CERTIFICATES.json").read_text()
    )["certificates"]

    assert binding["return_zip_sha256"] == EXPECTED_RETURN_SHA
    assert status["CHANNEL_RECORD_SHA256"] == binding["channel_record_sha256"]
    assert status["FREQUENCY_RESPONSE_ARRAY_SHA256"] == binding[
        "frequency_response_array_sha256"
    ]
    assert status["PREDICTIVE_REPRODUCTION_USER_INTERVALS"] == "104"
    assert status["PREDICTIVE_REPRODUCTION_USER_SECONDS"] == "519"
    assert status["CANDIDATE_LONG_VIOLATION_SECONDS"] == "0"
    assert status["CANDIDATE_SHORT_VIOLATION_SECONDS"] == "0"
    assert status["CANDIDATE_FLOOR_VIOLATION_USER_INTERVALS"] == "16"
    assert status["CANDIDATE_FLOOR_VIOLATION_USER_SECONDS"] == "80"
    assert status["STRICT_POST_MODE_STREAM_FEASIBLE_INTERVALS"] == "98"
    assert status["STRICT_POST_MODE_STREAM_INFEASIBLE_INTERVALS"] == "0"
    assert status["Q0_HEADROOM_USED_INTERVALS"] == "9"
    assert status["UNRESOLVED_DEPLOYABLE_INTERVALS"] == "0"
    assert status["CONFIRMATORY_CAMPAIGN_AUTHORIZED"] == "NO"

    # All 104 originally affected intervals have an exact candidate witness.
    assert len(affected) == 104
    assert set(affected.user_id) == {
        "E3_SITE_02_SEC_3_UE_4",
        "E3_SITE_07_SEC_1_UE_2",
    }
    assert float(affected.candidate_floor_ratio.min()) >= 1.0 - 1e-13

    residual_actions = actions.loc[actions.candidate_floor_violation_count > 0]
    assert len(residual_actions) == 16
    assert int(residual_actions.interval_seconds.sum()) == 80
    assert set(residual_actions.pass_slot) == {0, 1}
    assert set(residual_actions.chosen_action_class) == {
        "SPARSE_LOCAL_STREAM_POWER_REPAIR"
    }
    assert not bool(residual_actions.q0_power_headroom_used.any())

    maximum_shortfall = float(cells.maximum_normalized_floor_shortfall.max())
    assert maximum_shortfall <= 2.5e-10

    residual_keys = set(
        zip(
            residual_actions.pass_slot.astype(int),
            residual_actions.interval_index.astype(int),
        )
    )
    residual_certificates = [
        item
        for item in certificates
        if (int(item["pass_slot"]), int(item["interval_index"])) in residual_keys
    ]
    assert len(residual_certificates) == 16
    residual_excess = [
        float(item["strict_post_mode_sparse_stream_comparator"][
            "maximum_constraint_excess"
        ])
        for item in residual_certificates
    ]
    assert min(residual_excess) > 0.0
    assert max(residual_excess) < 1e-9

    site02 = affected.loc[affected.user_id == "E3_SITE_02_SEC_3_UE_4"]
    site07 = affected.loc[affected.user_id == "E3_SITE_07_SEC_1_UE_2"]
    assert len(site02) == 100 and len(site07) == 4
    assert float(site02.current_load_nominal_total_rate_bps_hz.min()) > float(
        site02.floor_bps_hz.max()
    )
    assert float(site02.reviewed_same_sector_fraction_of_nonnoise_interference.mean()) > 0.85
    assert float(site07.current_load_nominal_total_rate_bps_hz.max()) < 0.1
    assert float(site07.reviewed_external_fraction_of_nonnoise_interference.mean()) > 0.98

    record = {
        "schema_version": 1,
        "status": "PASS_PRIOR_V4_2_RECLASSIFIED_AS_NUMERICAL_WITNESS_BOUNDARY_DEFECT",
        "source_supported_facts": {
            "return_zip_sha256": EXPECTED_RETURN_SHA,
            "source_commit": binding["source_commit"],
            "reviewed_original_violating_intervals": 104,
            "reviewed_original_violating_user_seconds": 519,
            "original_affected_intervals_repaired": 104,
            "new_boundary_residual_intervals": 16,
            "new_boundary_residual_user_seconds": 80,
            "maximum_normalized_boundary_shortfall": maximum_shortfall,
            "maximum_strict_lp_constraint_excess_on_boundary_residuals": max(
                residual_excess
            ),
            "strict_post_mode_stream_feasible_intervals": 98,
            "strict_post_mode_stream_infeasible_intervals": 0,
            "q0_headroom_selected_intervals": 9,
            "eess_long_violation_seconds": 0,
            "eess_short_violation_seconds": 0,
        },
        "scientific_inference": {
            "v4_2_is_not_a_physical_infeasibility_certificate": True,
            "boundary_residual_cause": (
                "untightened L1 witnesses were accepted with positive linear "
                "constraint excess below 5e-9 and then failed the unchanged exact "
                "floor audit by at most 2.5e-10 normalized"
            ),
            "q0_headroom_is_unnecessary": (
                "the strict post-mode comparator was feasible in every one of the "
                "98 stream-repair intervals"
            ),
            "required_v4_3_correction": (
                "normalized solver-side reserve with unchanged exact tolerances; "
                "select strict post-mode witnesses only; retain q0 only as a diagnostic"
            ),
        },
        "root_cause_by_user": {
            "E3_SITE_02_SEC_3_UE_4": {
                "intervals": 100,
                "floor_branch": "RELATIVE_0P9_CURRENT_LOAD_NOMINAL",
                "minimum_reviewed_floor_ratio": float(
                    site02.reviewed_floor_ratio.min()
                ),
                "mean_same_sector_nonnoise_interference_fraction": float(
                    site02.reviewed_same_sector_fraction_of_nonnoise_interference.mean()
                ),
                "classification": (
                    "common sector scaling cannot redistribute fixed-RZF power "
                    "against dominant same-sector interference"
                ),
            },
            "E3_SITE_07_SEC_1_UE_2": {
                "intervals": 4,
                "floor_branch": "ABSOLUTE_0P1",
                "minimum_reviewed_floor_ratio": float(
                    site07.reviewed_floor_ratio.min()
                ),
                "current_load_nominal_rate_bps_hz": float(
                    site07.current_load_nominal_total_rate_bps_hz.iloc[0]
                ),
                "mean_external_nonnoise_interference_fraction": float(
                    site07.reviewed_external_fraction_of_nonnoise_interference.mean()
                ),
                "classification": (
                    "full-load eligibility plus absolute current-load floor is not "
                    "met by nominal all-sector action, but sparse external-sector "
                    "backoff provides a feasible witness"
                ),
            },
        },
        "confirmatory_campaign_authorized": False,
        "next_gate": "RUN_CANDIDATE_V4_3_ON_PRESERVED_SEED43999_CHANNEL",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print("PRIOR_V4_2_RETURN_BINDING=PASS")
    print("PRIOR_V4_2_NUMERICAL_RECLASSIFICATION=PASS")
    print("PRIOR_V4_2_ORIGINAL_AFFECTED_INTERVALS_REPAIRED=104")
    print("PRIOR_V4_2_BOUNDARY_RESIDUAL_INTERVALS=16")
    print(f"PRIOR_V4_2_MAXIMUM_NORMALIZED_BOUNDARY_SHORTFALL={maximum_shortfall:.17g}")
    print("PRIOR_V4_2_Q0_HEADROOM_UNNECESSARY=PASS")
    print("CONFIRMATORY_CAMPAIGN_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
