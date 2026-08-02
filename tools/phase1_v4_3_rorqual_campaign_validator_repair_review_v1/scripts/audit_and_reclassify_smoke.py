#!/usr/bin/env python3
"""Independently audit and reclassify the excluded Rorqual final-worker smoke."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import numpy as np
import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = "candidate_v4_3_floor_feasibility_repair"
COMPARATORS = [
    "robust_predictive_constrained_pf_with_sector_selective_fallback",
    "static_robust_constrained_pf_with_sector_selective_fallback",
    "delayed_myopic_constrained_pf_with_reactive_sector_fallback",
    "delayed_myopic_constrained_pf_unshielded",
    "virtual_queue_unshielded",
    "uniform_protected_tone_backoff",
    "hard_spatial_null_or_exact_mute",
    "common_scale_instantaneous_noncausal_reference",
]
TOL = 1e-12


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        return {name: data[name] for name in data.files}


def max_abs(a: np.ndarray, b: np.ndarray) -> float:
    aa = np.asarray(a)
    bb = np.asarray(b)
    if aa.shape != bb.shape:
        raise ValueError(f"array shape mismatch: {aa.shape} != {bb.shape}")
    if aa.dtype.kind in "USO" or bb.dtype.kind in "USO":
        return 0.0 if np.array_equal(aa, bb) else float("inf")
    return float(np.max(np.abs(aa.astype(float) - bb.astype(float))))


def verify_sidecar(zip_path: Path, sidecar: Path, expected: str) -> None:
    parts = sidecar.read_text(encoding="utf-8").split()
    if len(parts) != 2 or parts[1] != zip_path.name:
        raise ValueError(f"sidecar is not basename-only: {sidecar}")
    actual = sha256_file(zip_path)
    if actual != expected or parts[0] != actual:
        raise ValueError(f"ZIP SHA-256 mismatch: {zip_path}")




def _json_default(value: object) -> object:
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    output = Path(args.output_root).expanduser().resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    contract = json.loads(
        (PACKAGE_ROOT / "config/REPAIR_REVIEW_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    smoke_zip = PACKAGE_ROOT / "immutable_bindings" / contract["smoke_return"][
        "filename"
    ]
    smoke_sidecar = Path(str(smoke_zip) + ".sha256")
    verify_sidecar(smoke_zip, smoke_sidecar, contract["smoke_return"]["sha256"])
    with zipfile.ZipFile(smoke_zip) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError(f"smoke return ZIP CRC failure: {bad}")

    legacy_zip = (
        PACKAGE_ROOT
        / "immutable_bindings/locked_campaign"
        / contract["legacy_locked_campaign"]["filename"]
    )
    legacy_sidecar = Path(str(legacy_zip) + ".sha256")
    verify_sidecar(
        legacy_zip,
        legacy_sidecar,
        contract["legacy_locked_campaign"]["sha256"],
    )

    with tempfile.TemporaryDirectory(prefix="fr3-v43-smoke-audit-") as temp_name:
        temp = Path(temp_name)
        smoke_extract = temp / "smoke"
        job_extract = temp / "job"
        smoke_extract.mkdir()
        job_extract.mkdir()
        with zipfile.ZipFile(smoke_zip) as archive:
            archive.extractall(smoke_extract)
        with zipfile.ZipFile(legacy_zip) as archive:
            archive.extractall(job_extract)
        smoke_roots = [p for p in smoke_extract.iterdir() if p.is_dir()]
        if len(smoke_roots) != 1:
            raise ValueError(f"unexpected smoke ZIP roots: {smoke_roots}")
        smoke = smoke_roots[0]
        result = smoke / "result"

        subprocess.run(
            ["sha256sum", "-c", "RETURN_MANIFEST.sha256"],
            cwd=smoke,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        validator_dir = temp / "validator"
        validator_dir.mkdir()
        shutil.copy2(PACKAGE_ROOT / "templates/validate_seed_result.py", validator_dir)
        shutil.copy2(PACKAGE_ROOT / "templates/validator_contract.py", validator_dir)
        corrected_validator = validator_dir / "validate_seed_result.py"
        old_contract = job_extract / "JOB_PACKAGE_CONTRACT.json"
        for require_pass in (False, True):
            command = [
                "python3",
                str(corrected_validator),
                "--result-dir",
                str(result),
                "--package-contract",
                str(old_contract),
            ]
            if require_pass:
                command.append("--require-scientific-pass")
            completed = subprocess.run(command, capture_output=True, text=True)
            (output / (
                "CORRECTED_VALIDATOR_SCIENTIFIC.log"
                if require_pass
                else "CORRECTED_VALIDATOR_STRUCTURAL.log"
            )).write_text(completed.stdout + completed.stderr, encoding="utf-8")
            if completed.returncode != 0:
                raise RuntimeError(
                    f"corrected seed validator failed ({require_pass=}):\n"
                    + completed.stdout
                    + completed.stderr
                )

        metadata = json.loads((smoke / "RETURN_METADATA.json").read_text())
        seed = json.loads((result / "SEED_RESULT.json").read_text())
        audit = json.loads(
            (smoke / "provenance/FINAL_WORKER_SMOKE_AUDIT.json").read_text()
        )
        channel = json.loads((smoke / "channel/CHANNEL_RECORD.json").read_text())
        reference = PACKAGE_ROOT / "immutable_bindings/reference_seed43999"
        reference_channel = json.loads(
            (reference / "REFERENCE_CHANNEL_RECORD.json").read_text()
        )
        cells = pd.read_csv(result / "CELL_SUMMARY.csv")
        candidate = cells.loc[cells["method_id"] == CANDIDATE].sort_values(
            "pass_slot"
        )

        hard_checks = {
            "worker_exit_zero": int(metadata["worker_exit_code"]) == 0,
            "seed_scientific_status_pass": seed["status"]
            == "PASS_PHASE1_V4_3_SEED_RESULT_REVIEW_REQUIRED",
            "seed_scientific_exit_zero": int(seed["scientific_exit_code"]) == 0,
            "seed_hard_gate_boolean": bool(seed["candidate_hard_gates_pass"]),
            "zero_floor_seconds": int(
                candidate["eligible_floor_violation_user_seconds"].sum()
            )
            == 0,
            "zero_floor_intervals": int(
                candidate["eligible_floor_violation_user_intervals"].sum()
            )
            == 0,
            "zero_long_eess": int(candidate["long_violation_seconds"].sum()) == 0,
            "zero_short_eess": int(candidate["short_violation_seconds"].sum())
            == 0,
            "strict_local_scope": (
                candidate["candidate_strict_local_scope_gate"] == "PASS"
            ).all(),
            "strict_post_mode_power": (
                candidate["candidate_strict_post_mode_power_gate"] == "PASS"
            ).all(),
            "zero_q0_actions": int(
                candidate["candidate_q0_envelope_deployable_actions"].sum()
            )
            == 0,
            "zero_unresolved": int(
                candidate["candidate_unresolved_deployable_intervals"].sum()
            )
            == 0,
            "zero_shutdown": int(
                candidate["candidate_network_wide_shutdown_intervals"].sum()
            )
            == 0,
            "strict_power_ratio": float(
                candidate["candidate_maximum_strict_post_mode_power_ratio"].max()
            )
            <= 1.0 + 1e-10,
            "independent_hard_gate_audit": audit["candidate_hard_gates"] == "PASS",
        }
        if not all(hard_checks.values()):
            raise ValueError(f"candidate hard-gate re-audit failed: {hard_checks}")

        channel_checks = {
            "array_bytes": channel["frequency_response_sha256_array_bytes"]
            == reference_channel["frequency_response_sha256_array_bytes"],
            "campaign_seed": int(channel["campaign_seed"]) == 43999,
            "user_seed": int(channel["user_seed"]) == 87998,
            "channel_seed": int(channel["channel_seed"]) == 87999,
            "coefficients": channel["channel_generation"]["coefficients_sha256"]
            == reference_channel["channel_generation"]["coefficients_sha256"],
            "delays": channel["channel_generation"]["delays_sha256"]
            == reference_channel["channel_generation"]["delays_sha256"],
            "user_topology": channel["files"]["USER_TOPOLOGY.csv"]["sha256"]
            == reference_channel["files"]["USER_TOPOLOGY.csv"]["sha256"],
            "sector_topology": channel["files"]["SECTOR_TOPOLOGY.csv"]["sha256"]
            == reference_channel["files"]["SECTOR_TOPOLOGY.csv"]["sha256"],
        }
        if not all(channel_checks.values()):
            raise ValueError(f"channel exactness failed: {channel_checks}")

        # Every common metric for the eight legacy comparators is exact.
        reference_comparators = pd.read_csv(
            reference / "REFERENCE_ALL_METHOD_CELL_SUMMARY.csv"
        ).sort_values(["pass_slot", "method_id"])
        actual_comparators = cells.loc[cells["method_id"].isin(COMPARATORS)].sort_values(
            ["pass_slot", "method_id"]
        )
        common_exact = [
            "long_violation_seconds",
            "short_violation_seconds",
            "eligible_floor_violation_user_intervals",
            "eligible_floor_violation_user_seconds",
            "sector_mute_interval_count",
            "intervals_with_any_sector_mute",
            "maximum_muted_sector_count",
            "protected_sample_count",
            "interval_count",
        ]
        common_float = [
            "long_maximum_excess_db",
            "short_maximum_excess_db",
            "total_normalized_floor_shortfall",
            "final_moving_pf_utility",
            "duration_weighted_mean_moving_pf_utility",
            "protected_active_eligible_p05_bps_hz",
            "protected_active_eligible_geometric_mean_bps_hz",
            "total_active_eligible_p05_bps_hz",
            "total_active_eligible_geometric_mean_bps_hz",
        ]
        comparator_errors: dict[str, float] = {}
        for column in common_exact:
            if not np.array_equal(
                actual_comparators[column].to_numpy(),
                reference_comparators[column].to_numpy(),
            ):
                raise ValueError(f"comparator exact column mismatch: {column}")
            comparator_errors[column] = 0.0
        for column in common_float:
            error = max_abs(
                actual_comparators[column].to_numpy(float),
                reference_comparators[column].to_numpy(float),
            )
            comparator_errors[column] = error
            if error > TOL:
                raise ValueError(f"comparator metric mismatch: {column}={error}")

        reference_utility = pd.read_csv(
            reference / "REFERENCE_CANDIDATE_UTILITY_SUMMARY.csv"
        ).sort_values("pass_slot")
        metric_records: list[dict[str, float | int]] = []
        trace_max = 0.0
        action_class_exact = True
        for slot in range(5):
            ref_trace = load_npz(
                reference / f"REFERENCE_CANDIDATE_PASS_{slot}_TRACE.npz"
            )
            actual_action = load_npz(
                result / f"PASS_{slot}_CANDIDATE_ACTION_TRACE.npz"
            )
            actual_method = load_npz(result / f"PASS_{slot}_METHOD_TRACES.npz")
            pairs = [
                (actual_action["candidate_stream_scale"], ref_trace["candidate_stream_scale"]),
                (
                    actual_action["candidate_pre_repair_sector_scale"],
                    ref_trace["integrated_pre_repair_sector_scale"],
                ),
                (
                    actual_action["candidate_maximum_shortfall_trace"],
                    ref_trace["candidate_normalized_shortfall"],
                ),
                (actual_action["interval_lengths"], ref_trace["interval_lengths"]),
                (actual_method["m0_long_ratio"], ref_trace["candidate_long_ratio"]),
                (actual_method["m0_short_ratio"], ref_trace["candidate_short_ratio"]),
                (actual_method["m0_floor_count"], ref_trace["candidate_floor_count"]),
                (
                    actual_method["m0_shortfall"],
                    ref_trace["candidate_normalized_shortfall"],
                ),
                (actual_method["m0_pf_utility"], np.log(ref_trace["candidate_moving_average_rate"][:, _eligible_mask(ref_trace)] + 0.001).sum(axis=1)),
            ]
            for left, right in pairs:
                trace_max = max(trace_max, max_abs(left, right))
            action_class_exact = action_class_exact and np.array_equal(
                actual_action["candidate_action_class"], ref_trace["action_class"]
            )

            eligible = _eligible_mask(ref_trace)
            values = []
            for row in ref_trace["candidate_total_rate"]:
                selected = row[eligible]
                values.extend(selected[selected > 0].tolist())
            values_array = np.asarray(values, dtype=float)
            standard = float(np.exp(np.mean(np.log(values_array))))
            stabilized = float(
                np.exp(np.mean(np.log(values_array + 0.001))) - 0.001
            )
            actual_row = candidate.loc[candidate["pass_slot"] == slot].iloc[0]
            ref_row = reference_utility.loc[
                reference_utility["pass_slot"] == slot
            ].iloc[0]
            actual_stabilized = float(
                actual_row["total_active_eligible_geometric_mean_bps_hz"]
            )
            reference_standard = float(
                ref_row["candidate_total_active_eligible_geometric_mean_bps_hz"]
            )
            if abs(actual_stabilized - stabilized) > TOL:
                raise ValueError(f"pass {slot}: campaign summary GM formula mismatch")
            if abs(reference_standard - standard) > TOL:
                raise ValueError(f"pass {slot}: excluded reference GM formula mismatch")
            metric_records.append(
                {
                    "pass_slot": slot,
                    "standard_positive_geometric_mean_bps_hz": standard,
                    "epsilon_stabilized_geometric_mean_bps_hz": stabilized,
                    "expected_definition_difference_bps_hz": stabilized - standard,
                    "actual_campaign_summary_value_bps_hz": actual_stabilized,
                    "excluded_reference_value_bps_hz": reference_standard,
                }
            )

        if trace_max > TOL or not action_class_exact:
            raise ValueError(
                f"candidate trace mismatch: max={trace_max}, action={action_class_exact}"
            )

        # Primary and mandatory secondary endpoints are exact and are the
        # preregistered statistical endpoints; the GM mismatch is descriptive.
        endpoint_map = {
            "candidate_final_moving_pf_utility": "final_moving_pf_utility",
            "candidate_duration_weighted_mean_moving_pf_utility": (
                "duration_weighted_mean_moving_pf_utility"
            ),
            "candidate_total_active_eligible_p05_bps_hz": (
                "total_active_eligible_p05_bps_hz"
            ),
            "candidate_protected_active_eligible_p05_bps_hz": (
                "protected_active_eligible_p05_bps_hz"
            ),
        }
        endpoint_errors: dict[str, float] = {}
        for ref_column, actual_column in endpoint_map.items():
            error = max_abs(
                reference_utility[ref_column].to_numpy(float),
                candidate[actual_column].to_numpy(float),
            )
            endpoint_errors[actual_column] = error
            if error > TOL:
                raise ValueError(f"candidate endpoint mismatch: {actual_column}")

        paired = pd.read_csv(result / "PRIMARY_PAIRED_EFFECTS.csv")
        paired_columns = [
            "candidate_minus_static_final_pf",
            "candidate_minus_static_duration_mean_pf",
            "candidate_minus_predictive_final_pf",
            "candidate_minus_predictive_duration_mean_pf",
        ]
        paired_errors: dict[str, float] = {}
        for column in paired_columns:
            error = max_abs(
                paired.sort_values("pass_slot")[column].to_numpy(float),
                reference_utility.sort_values("pass_slot")[column].to_numpy(float),
            )
            paired_errors[column] = error
            if error > TOL:
                raise ValueError(f"paired-effect mismatch: {column}")

        candidate_only_na_count = int(
            cells.loc[
                cells["method_id"] != CANDIDATE,
                [column for column in cells.columns if column.startswith("candidate_") and pd.api.types.is_numeric_dtype(cells[column])],
            ].isna().to_numpy().sum()
        )
        structural_failure = (
            "legacy validator applied an all-numeric finite test to intentional "
            "candidate-only N/A fields on comparator rows"
        )
        scientific_failure = (
            "legacy smoke audit directly compared an epsilon-stabilized campaign "
            "geometric mean with an ordinary positive geometric mean reference"
        )
        reclassification = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS_EXCLUDED_RORQUAL_FINAL_WORKER_SMOKE_AFTER_VALIDATOR_CONTRACT_REPAIR",
            "scientific_result": "PASS",
            "paper_result": False,
            "campaign_seed": 43999,
            "job_id": "18132931",
            "source_commit": "fa00b2a4d81b98a2089c992f56fdca63e23c24f3",
            "smoke_return_sha256": sha256_file(smoke_zip),
            "smoke_return_manifest_sha256": sha256_file(
                smoke / "RETURN_MANIFEST.sha256"
            ),
            "channel_record_file_sha256": sha256_file(
                smoke / "channel/CHANNEL_RECORD.json"
            ),
            "channel_record_canonical_json_sha256": canonical_json_sha256(channel),
            "generated_frequency_response_array_sha256": channel[
                "frequency_response_sha256_array_bytes"
            ],
            "channel_exact_reference_gate": "PASS",
            "comparator_reference_summary_gate": "PASS",
            "candidate_action_class_trace_exact": action_class_exact,
            "candidate_trace_maximum_absolute_error": trace_max,
            "candidate_primary_secondary_endpoint_gate": "PASS",
            "candidate_hard_gates": "PASS",
            "candidate_floor_violation_user_seconds": 0,
            "candidate_floor_violation_user_intervals": 0,
            "candidate_long_eess_violation_seconds": 0,
            "candidate_short_eess_violation_seconds": 0,
            "candidate_local_grid_repair_intervals": int(
                candidate["candidate_local_grid_repair_intervals"].sum()
            ),
            "candidate_local_stream_repair_intervals": int(
                candidate["candidate_local_stream_repair_intervals"].sum()
            ),
            "candidate_unresolved_intervals": int(
                candidate["candidate_unresolved_deployable_intervals"].sum()
            ),
            "candidate_network_wide_shutdown_intervals": int(
                candidate["candidate_network_wide_shutdown_intervals"].sum()
            ),
            "maximum_strict_post_mode_power_ratio": float(
                candidate["candidate_maximum_strict_post_mode_power_ratio"].max()
            ),
            "structural_validator_defect": structural_failure,
            "legacy_independent_audit_defect": scientific_failure,
            "intentional_candidate_only_na_count": candidate_only_na_count,
            "geometric_mean_definition_records": metric_records,
            "candidate_endpoint_maximum_absolute_errors": endpoint_errors,
            "paired_effect_maximum_absolute_errors": paired_errors,
            "comparator_maximum_absolute_errors": comparator_errors,
            "hard_checks": hard_checks,
            "channel_checks": channel_checks,
            "full_campaign_execution_authorized": False,
            "next_gate": "BUILD_AND_REVIEW_CORRECTED_RORQUAL_NATIVE_LOCKED_30_SEED_CAMPAIGN_PACKAGE",
            "claim_boundary": "EXCLUDED_DEVELOPMENT_SEED_NOT_CONFIRMATORY_NOT_PAPER_RESULT_NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE",
        }
        write_json(output / "SMOKE_RECLASSIFICATION_VERDICT.json", reclassification)
        pd.DataFrame(metric_records).to_csv(
            output / "GEOMETRIC_MEAN_DEFINITION_AUDIT.csv", index=False
        )
        pd.DataFrame(
            [
                {
                    "mean_candidate_minus_static_final_pf": float(
                        paired["candidate_minus_static_final_pf"].mean()
                    ),
                    "mean_candidate_minus_static_duration_mean_pf": float(
                        paired["candidate_minus_static_duration_mean_pf"].mean()
                    ),
                    "mean_candidate_minus_predictive_final_pf": float(
                        paired["candidate_minus_predictive_final_pf"].mean()
                    ),
                    "mean_candidate_minus_predictive_duration_mean_pf": float(
                        paired["candidate_minus_predictive_duration_mean_pf"].mean()
                    ),
                }
            ]
        ).to_csv(output / "EXCLUDED_SEED_PAIRED_EFFECT_SUMMARY.csv", index=False)

    print("SMOKE_RETURN_SHA256_GATE=PASS")
    print("SMOKE_RETURN_CONTENT_MANIFEST_GATE=PASS")
    print("CORRECTED_STRUCTURAL_VALIDATOR=PASS")
    print("CORRECTED_SCIENTIFIC_PASS_VALIDATOR=PASS")
    print("CHANNEL_EXACT_REFERENCE_GATE=PASS")
    print("COMPARATOR_REFERENCE_SUMMARY_GATE=PASS")
    print("CANDIDATE_PRIMARY_SECONDARY_ENDPOINT_GATE=PASS")
    print("CANDIDATE_ACTION_CLASS_TRACE_EXACT=PASS")
    print("CANDIDATE_TRACE_MAXIMUM_ABSOLUTE_ERROR=0")
    print("CANDIDATE_HARD_GATES=PASS")
    print("VALIDATOR_CONTRACT_DEFECT_CLASSIFICATION=PASS")
    print(
        "SMOKE_RECLASSIFICATION_STATUS="
        "PASS_EXCLUDED_RORQUAL_FINAL_WORKER_SMOKE_AFTER_VALIDATOR_CONTRACT_REPAIR"
    )
    print("FULL_CAMPAIGN_EXECUTION_AUTHORIZED=NO")
    return 0


def _eligible_mask(trace: dict[str, np.ndarray]) -> np.ndarray:
    alpha = 1.0 - np.exp(-5.0 / 100.0)
    initial = (
        trace["candidate_moving_average_rate"][0]
        - alpha * trace["candidate_total_rate"][0]
    ) / (1.0 - alpha)
    return np.asarray(initial >= 0.1, dtype=bool)


if __name__ == "__main__":
    raise SystemExit(main())
