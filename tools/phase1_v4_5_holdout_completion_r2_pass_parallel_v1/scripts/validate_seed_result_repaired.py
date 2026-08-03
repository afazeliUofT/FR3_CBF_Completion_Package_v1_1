#!/usr/bin/env python3
"""Strict structural and scientific-gate validation of one v4.5 fresh-holdout seed result."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

CANDIDATE = "candidate_v4_5_companion_aware_protected_subband_scheduling"
METHOD_IDS = [
    CANDIDATE,
    "robust_predictive_constrained_pf_with_sector_selective_fallback",
    "static_robust_constrained_pf_with_sector_selective_fallback",
    "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
    "delayed_myopic_constrained_pf_unshielded",
    "virtual_queue_unshielded",
    "uniform_protected_tone_backoff",
    "hard_spatial_null_or_exact_mute",
    "common_scale_instantaneous_noncausal_reference",
]
SAFE_EESS_IDS = {
    CANDIDATE,
    "robust_predictive_constrained_pf_with_sector_selective_fallback",
    "static_robust_constrained_pf_with_sector_selective_fallback",
    "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
    "uniform_protected_tone_backoff",
    "hard_spatial_null_or_exact_mute",
    "common_scale_instantaneous_noncausal_reference",
}
PASS_STATUS = "PASS_FRESH_V4_5_HOLDOUT_SEED_ALL_HARD_GATES"
FAIL_STATUS = "VALID_FRESH_V4_5_HOLDOUT_SEED_FEASIBILITY_CONDITIONED_FLOOR"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True)
    parser.add_argument("--package-contract", required=True)
    parser.add_argument("--require-scientific-pass", action="store_true")
    args = parser.parse_args()

    result = Path(args.result_dir).expanduser().resolve()
    contract = json.loads(
        Path(args.package_contract).read_text(encoding="utf-8")
    )
    required = [
        "SEED_RESULT.json",
        "RESULT_FILE_MANIFEST.json",
        "CELL_SUMMARY.csv",
        "PRIMARY_PAIRED_EFFECTS.csv",
    ]
    required += [f"PASS_{slot}_METHOD_TRACES.npz" for slot in range(5)]
    required += [f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz" for slot in range(5)]
    for name in required:
        if not (result / name).is_file():
            raise FileNotFoundError(result / name)

    audit = json.loads((result / "SEED_RESULT.json").read_text(encoding="utf-8"))
    if audit["status"] not in {PASS_STATUS, FAIL_STATUS}:
        raise ValueError(f"unexpected seed status: {audit['status']!r}")
    if audit["package_id"] != contract["package_id"]:
        raise ValueError("seed package ID mismatch")
    if audit["candidate_source_manifest_sha256"] != contract["candidate_v4_5"][
        "source_manifest_sha256"
    ]:
        raise ValueError("candidate source-manifest binding mismatch")
    if int(audit["cell_count"]) != 45 or audit["method_ids"] != METHOD_IDS:
        raise ValueError("seed method/cell design mismatch")
    if len(audit["pass_audits"]) != 5:
        raise ValueError("seed result must contain five pass audits")
    expected_exit = 0 if audit["candidate_hard_gates_pass"] else 42
    if int(audit["scientific_exit_code"]) != expected_exit:
        raise ValueError("scientific exit-code classification mismatch")
    if (audit["status"] == PASS_STATUS) != bool(audit["candidate_hard_gates_pass"]):
        raise ValueError("seed status and hard-gate boolean disagree")
    if args.require_scientific_pass and not audit["candidate_hard_gates_pass"]:
        raise ValueError("candidate hard gates failed")

    manifest = json.loads(
        (result / "RESULT_FILE_MANIFEST.json").read_text(encoding="utf-8")
    )
    for name, record in manifest.items():
        path = result / name
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"result manifest mismatch: {name}")

    cells = pd.read_csv(result / "CELL_SUMMARY.csv")
    if len(cells) != 45:
        raise ValueError(f"CELL_SUMMARY has {len(cells)} rows, expected 45")
    if sorted(cells["pass_slot"].unique().tolist()) != list(range(5)):
        raise ValueError("CELL_SUMMARY pass slots are wrong")
    for slot, frame in cells.groupby("pass_slot", sort=True):
        if frame["method_id"].tolist() != METHOD_IDS:
            raise ValueError(f"pass {slot}: method order mismatch")
    from validator_contract import validate_cell_summary_numeric_domains
    domain_audit = validate_cell_summary_numeric_domains(cells)
    print("CELL_SUMMARY_NUMERIC_DOMAIN_GATE=PASS")
    print(
        "CELL_SUMMARY_INTENTIONAL_CANDIDATE_ONLY_NA_COUNT="
        + str(domain_audit["intentional_candidate_only_na_count"])
    )
    print("PAYLOAD_LOWER_BOUND_CONTRACT_REPAIR=PASS")

    for method_id in SAFE_EESS_IDS:
        frame = cells.loc[cells["method_id"] == method_id]
        if int(frame["long_violation_seconds"].sum()) != 0:
            raise ValueError(f"safe method long EESS failure: {method_id}")
        if int(frame["short_violation_seconds"].sum()) != 0:
            raise ValueError(f"safe method short EESS failure: {method_id}")

    candidate = cells.loc[cells["method_id"] == CANDIDATE]
    hard_from_cells = (
        int(candidate["long_violation_seconds"].sum()) == 0
        and int(candidate["short_violation_seconds"].sum()) == 0
        and int(candidate["eligible_floor_violation_user_seconds"].sum()) == 0
        and int(candidate["eligible_floor_violation_user_intervals"].sum()) == 0
        and (candidate["candidate_strict_local_scope_gate"] == "PASS").all()
        and (candidate["candidate_strict_post_mode_power_gate"] == "PASS").all()
        and int(candidate["candidate_q0_envelope_deployable_actions"].sum()) == 0
        and int(candidate["candidate_unresolved_deployable_intervals"].sum()) == 0
        and int(candidate["candidate_network_wide_shutdown_intervals"].sum()) == 0
        and float(candidate["candidate_maximum_strict_post_mode_power_ratio"].max())
        <= 1.0 + 1e-10
    )
    if hard_from_cells != bool(audit["candidate_hard_gates_pass"]):
        raise ValueError("cell-level candidate gates disagree with SEED_RESULT")

    paired = pd.read_csv(result / "PRIMARY_PAIRED_EFFECTS.csv")
    expected_paired = {
        "pass_slot",
        "candidate_minus_static_final_pf",
        "candidate_minus_static_duration_mean_pf",
        "candidate_minus_predictive_final_pf",
        "candidate_minus_predictive_duration_mean_pf",
    }
    if len(paired) != 5 or not expected_paired.issubset(paired.columns):
        raise ValueError("PRIMARY_PAIRED_EFFECTS schema mismatch")
    if not np.isfinite(paired.select_dtypes(include=[np.number])).all().all():
        raise ValueError("paired effects contain non-finite values")

    for slot in range(5):
        trace = load_npz(result / f"PASS_{slot}_METHOD_TRACES.npz")
        if trace["method_ids"].tolist() != METHOD_IDS:
            raise ValueError(f"pass {slot}: method trace order mismatch")
        expected_seconds = int(
            cells.loc[cells["pass_slot"] == slot, "protected_sample_count"].iloc[0]
        )
        if int(trace["interval_lengths"].sum()) != expected_seconds:
            raise ValueError(f"pass {slot}: trace duration mismatch")
        action = load_npz(result / f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz")
        interval_count = int(
            cells.loc[cells["pass_slot"] == slot, "interval_count"].iloc[0]
        )
        if len(action["candidate_action_class"]) != interval_count:
            raise ValueError(f"pass {slot}: candidate action trace length mismatch")
        if int(action["interval_lengths"].sum()) != expected_seconds:
            raise ValueError(f"pass {slot}: candidate action duration mismatch")
        coefficient_counts = action[
            "candidate_changed_stream_coefficient_count_trace"
        ]
        sector_counts = action["candidate_changed_sector_count_trace"]
        payload_bytes = action[
            "candidate_incremental_float32_payload_lower_bound_bytes_trace"
        ]
        if not (
            len(coefficient_counts) == interval_count
            and len(sector_counts) == interval_count
            and len(payload_bytes) == interval_count
        ):
            raise ValueError(f"pass {slot}: candidate overhead trace length mismatch")
        if np.any(coefficient_counts < 0) or np.any(sector_counts < 0):
            raise ValueError(f"pass {slot}: negative candidate command counts")
        schedule_nonzero_counts = action[
            "candidate_schedule_nonzero_mode_count_trace"
        ]
        schedule_mutable_counts = action[
            "candidate_schedule_mutable_sector_count_trace"
        ]
        expected_payload_bytes = (
            4 * coefficient_counts
            + 4 * schedule_nonzero_counts
            + 2 * schedule_mutable_counts
        )
        if not np.array_equal(payload_bytes, expected_payload_bytes):
            raise ValueError(
                f"pass {slot}: repaired payload lower-bound trace mismatch"
            )
        candidate_row = cells.loc[
            (cells["pass_slot"] == slot) & (cells["method_id"] == CANDIDATE)
        ].iloc[0]
        if int(coefficient_counts.sum()) != int(
            candidate_row["candidate_changed_stream_coefficient_count_sum"]
        ):
            raise ValueError(f"pass {slot}: coefficient-count summary mismatch")
        if int(sector_counts.sum()) != int(
            candidate_row["candidate_changed_sector_interval_count_sum"]
        ):
            raise ValueError(f"pass {slot}: sector-count summary mismatch")
        if int(payload_bytes.sum()) != int(
            candidate_row[
                "candidate_incremental_float32_payload_lower_bound_bytes_sum"
            ]
        ):
            raise ValueError(f"pass {slot}: payload summary mismatch")
        for key in (
            "candidate_schedule_mode_count_trace",
            "candidate_schedule_nonzero_mode_count_trace",
            "candidate_schedule_guard_sector_limit_trace",
            "candidate_schedule_mutable_sector_count_trace",
        ):
            if key not in action or len(action[key]) != interval_count:
                raise ValueError(f"pass {slot}: missing/invalid {key}")
        if int(np.sum(action["candidate_schedule_nonzero_mode_count_trace"] > 0)) < 0:
            raise ValueError(f"pass {slot}: impossible schedule count")

    archive = result.parent / f"FR3_PHASE1_SEED_{audit['campaign_seed']}_RETURN.zip"
    if archive.exists():
        sidecar = Path(str(archive) + ".sha256")
        if not sidecar.is_file():
            raise FileNotFoundError(sidecar)
        parts = sidecar.read_text(encoding="utf-8").split()
        if len(parts) != 2 or parts[1] != archive.name:
            raise ValueError("seed return sidecar is not basename-only")
        if parts[0] != sha256_file(archive):
            raise ValueError("seed return ZIP checksum mismatch")
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                raise ValueError("seed return ZIP CRC failure")

    print("FRESH_V4_5_HOLDOUT_SEED_STRUCTURAL_VALIDATION=PASS")
    print(f"CAMPAIGN_SEED={audit['campaign_seed']}")
    print(f"CANDIDATE_HARD_GATES={'PASS' if hard_from_cells else 'FAIL'}")
    print(f"SCIENTIFIC_EXIT_CODE={audit['scientific_exit_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
