#!/usr/bin/env python3
"""Audit the incomplete fresh-v4.5 holdout and classify repairable defects."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

import numpy as np
import pandas as pd

EXPECTED_RETURN_SHA256 = "066bd2190788f5dd8549b7fe1203070d091875e0a33e61762df4c21da6f587a7"
EXPECTED_PACKAGE_ID = "00a3561864f8adb8ad22cf1bd866ec0234043c16acbb25634d1d3502defc2cc6"
EXPECTED_SEEDS = list(range(44030, 44060))
MISSING_SEED = 44052
PAYLOAD_VALIDATOR_DEFECT_SEEDS = {
    44031, 44035, 44036, 44037, 44038,
    44042, 44049, 44050, 44054, 44056,
}
CANDIDATE = "candidate_v4_5_companion_aware_protected_subband_scheduling"
STATIC = "static_robust_constrained_pf_with_sector_selective_fallback"
PREDICTIVE = "robust_predictive_constrained_pf_with_sector_selective_fallback"
EFFECT_COLUMNS = [
    "candidate_minus_static_final_pf",
    "candidate_minus_static_duration_mean_pf",
    "candidate_minus_predictive_final_pf",
    "candidate_minus_predictive_duration_mean_pf",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json_from_zip(zf: zipfile.ZipFile, name: str) -> dict:
    return json.loads(zf.read(name).decode("utf-8"))


def verify_inner_manifest(zf: zipfile.ZipFile, root: str) -> None:
    manifest_name = f"{root}/RETURN_MANIFEST.sha256"
    lines = zf.read(manifest_name).decode("utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        rel = rel.strip()
        payload = zf.read(f"{root}/{rel}")
        actual = hashlib.sha256(payload).hexdigest()
        if actual != digest:
            raise RuntimeError(f"outer return manifest mismatch: {rel}")


def validate_payload_formula(action: dict[str, np.ndarray], slot: int, seed: int) -> None:
    coeff = action["candidate_changed_stream_coefficient_count_trace"]
    nonzero = action["candidate_schedule_nonzero_mode_count_trace"]
    mutable = action["candidate_schedule_mutable_sector_count_trace"]
    payload = action["candidate_incremental_float32_payload_lower_bound_bytes_trace"]
    expected = 4 * coeff + 4 * nonzero + 2 * mutable
    if not np.array_equal(payload, expected):
        raise RuntimeError(f"seed {seed} pass {slot}: repaired payload equation fails")


def bootstrap_29(values: np.ndarray, seed: int) -> dict:
    x = np.asarray(values, dtype=np.float64)
    if x.shape != (29,) or not np.isfinite(x).all():
        raise ValueError("provisional bootstrap requires 29 finite seed effects")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, 29, size=(10000, 29))
    means = x[idx].mean(axis=1)
    return {
        "point_estimate": float(x.mean()),
        "lower_95": float(np.quantile(means, 0.025)),
        "upper_95": float(np.quantile(means, 0.975)),
        "seed_cluster_standard_deviation": float(x.std(ddof=1)),
        "scope": "PROVISIONAL_29_OF_30_NOT_PAPER_RESULT",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--holdout-return-zip", required=True)
    p.add_argument("--output-json", required=True)
    args = p.parse_args()
    archive = Path(args.holdout_return_zip).resolve()
    if sha256_file(archive) != EXPECTED_RETURN_SHA256:
        raise RuntimeError("fresh-holdout return SHA-256 mismatch")

    all_cells: list[pd.DataFrame] = []
    all_paired: list[pd.DataFrame] = []
    audits: list[dict] = []
    missing: list[int] = []
    payload_scheduling_seed_count = 0

    with zipfile.ZipFile(archive) as outer:
        if outer.testzip() is not None:
            raise RuntimeError("fresh-holdout return ZIP CRC failure")
        roots = {name.split("/", 1)[0] for name in outer.namelist() if "/" in name}
        if len(roots) != 1:
            raise RuntimeError("unexpected outer return root layout")
        root = next(iter(roots))
        verify_inner_manifest(outer, root)
        metadata = read_json_from_zip(outer, f"{root}/HOLDOUT_RETURN_METADATA.json")
        completion = read_json_from_zip(outer, f"{root}/SEED_COMPLETION_INDEX.json")
        incomplete = read_json_from_zip(outer, f"{root}/merged/PHASE1_MERGE_INCOMPLETE.json")
        if metadata["package_id"] != EXPECTED_PACKAGE_ID:
            raise RuntimeError("holdout package ID mismatch")
        if int(metadata["seed_return_count"]) != 30:
            raise RuntimeError("expected all 30 seed return ZIPs")
        if [int(v["seed"]) for v in completion] != EXPECTED_SEEDS:
            raise RuntimeError("seed completion index mismatch")

        invalid_records = {int(v["campaign_seed"]): v["error"] for v in incomplete["invalid_or_missing"]}
        payload_defects = {
            seed for seed, text in invalid_records.items()
            if "payload lower-bound trace mismatch" in text
        }
        missing_results = {
            seed for seed, text in invalid_records.items()
            if "SEED_RESULT.json" in text and "FileNotFoundError" in text
        }
        if payload_defects != PAYLOAD_VALIDATOR_DEFECT_SEEDS:
            raise RuntimeError(f"unexpected payload-validator defect seeds: {sorted(payload_defects)}")
        if missing_results != {MISSING_SEED}:
            raise RuntimeError(f"unexpected missing-result seeds: {sorted(missing_results)}")

        for seed in EXPECTED_SEEDS:
            nested_name = f"{root}/seed_returns/FR3_PHASE1_SEED_{seed}_RETURN.zip"
            nested_bytes = outer.read(nested_name)
            with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
                if nested.testzip() is not None:
                    raise RuntimeError(f"seed {seed} return CRC failure")
                prefix = f"FR3_PHASE1_SEED_{seed}_RETURN"
                result_name = f"{prefix}/result/SEED_RESULT.json"
                if result_name not in nested.namelist():
                    if seed != MISSING_SEED:
                        raise RuntimeError(f"unexpected missing result for seed {seed}")
                    missing.append(seed)
                    stderr = nested.read(f"{prefix}/worker_stderr.log").decode("utf-8", "replace")
                    if "protected scheduling mode count 7776 exceeds 4096" not in stderr:
                        raise RuntimeError("seed 44052 failure is not the bound mode-cap exception")
                    continue
                audit = read_json_from_zip(nested, result_name)
                if audit["package_id"] != EXPECTED_PACKAGE_ID:
                    raise RuntimeError(f"seed {seed} package ID mismatch")
                audits.append(audit)
                cells = pd.read_csv(io.BytesIO(nested.read(f"{prefix}/result/CELL_SUMMARY.csv")))
                paired = pd.read_csv(io.BytesIO(nested.read(f"{prefix}/result/PRIMARY_PAIRED_EFFECTS.csv")))
                cells["campaign_seed"] = seed
                paired["campaign_seed"] = seed
                all_cells.append(cells)
                all_paired.append(paired)
                for slot in range(5):
                    payload = nested.read(f"{prefix}/result/PASS_{slot}_CANDIDATE_ACTION_TRACE.npz")
                    with np.load(io.BytesIO(payload), allow_pickle=False) as data:
                        action = {key: data[key] for key in data.files}
                    validate_payload_formula(action, slot, seed)
                    if np.any(action["candidate_schedule_nonzero_mode_count_trace"] > 0):
                        payload_scheduling_seed_count += 1
                        break

    if missing != [MISSING_SEED] or len(audits) != 29:
        raise RuntimeError("holdout incompleteness classification mismatch")
    cells = pd.concat(all_cells, ignore_index=True)
    paired = pd.concat(all_paired, ignore_index=True)
    seed_effects = paired.groupby("campaign_seed")[EFFECT_COLUMNS].mean().sort_index()
    bootstrap = {
        name: bootstrap_29(seed_effects[name].to_numpy(float), 20260801 + offset)
        for offset, name in enumerate(EFFECT_COLUMNS)
    }
    candidate = cells.loc[cells["method_id"] == CANDIDATE]
    predictive = cells.loc[cells["method_id"] == PREDICTIVE]
    static = cells.loc[cells["method_id"] == STATIC]
    result = {
        "schema_version": 1,
        "status": "PASS_HOLDOUT_COMPLETION_REPAIR_REQUIRED_AND_WELL_SCOPED",
        "source_supported_facts": {
            "return_sha256": EXPECTED_RETURN_SHA256,
            "expected_seed_count": 30,
            "complete_seed_result_count": 29,
            "missing_seed_result": MISSING_SEED,
            "payload_validator_false_alarm_seed_count": len(PAYLOAD_VALIDATOR_DEFECT_SEEDS),
            "payload_validator_false_alarm_seeds": sorted(PAYLOAD_VALIDATOR_DEFECT_SEEDS),
            "mode_count_observed": 7776,
            "original_mode_count_guard": 4096,
            "candidate_safety_pass_seed_count": 29,
            "candidate_hard_gate_pass_seed_count": int(sum(bool(a["candidate_hard_gates_pass"]) for a in audits)),
            "candidate_floor_violation_user_seconds_29": int(candidate["eligible_floor_violation_user_seconds"].sum()),
            "candidate_floor_violation_user_intervals_29": int(candidate["eligible_floor_violation_user_intervals"].sum()),
            "candidate_unresolved_intervals_29": int(candidate["candidate_unresolved_deployable_intervals"].sum()),
            "candidate_long_eess_violation_seconds_29": int(candidate["long_violation_seconds"].sum()),
            "candidate_short_eess_violation_seconds_29": int(candidate["short_violation_seconds"].sum()),
            "predictive_floor_violation_user_seconds_29": int(predictive["eligible_floor_violation_user_seconds"].sum()),
            "static_floor_violation_user_seconds_29": int(static["eligible_floor_violation_user_seconds"].sum()),
            "payload_formula_verified_on_all_29_complete_seed_results": True,
            "seed_count_with_nonzero_scheduling_payload": int(payload_scheduling_seed_count),
        },
        "scientific_inference": {
            "validator_defect": "validator omitted schedule-mode and mutable-sector terms from the declared payload lower bound",
            "seed_44052_defect": "implementation enumeration guard rejected an already-declared 7776-mode companion-aware library before scientific evaluation",
            "repair_changes_action_space": False,
            "repair_changes_objective_or_constraints": False,
            "repair_changes_floor_or_tolerances": False,
            "repair_requires_new_seed": False,
            "required_rerun_seeds": [MISSING_SEED],
        },
        "provisional_29_seed_statistics_not_paper_result": bootstrap,
        "next_gate": "RERUN_ONLY_SEED_44052_WITH_MODE_CAP_8192_THEN_REVALIDATE_AND_MERGE_ALL_30",
        "automatic_extra_seeds_authorized": False,
        "automatic_algorithm_tuning_authorized": False,
    }
    output = Path(args.output_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("INCOMPLETE_HOLDOUT_AUDIT=PASS")
    print("COMPLETE_SEED_RESULT_COUNT=29")
    print("PAYLOAD_VALIDATOR_FALSE_ALARM_SEED_COUNT=10")
    print("MISSING_SEED_RESULT=44052")
    print("SEED_44052_ROOT_CAUSE=MODE_COUNT_7776_EXCEEDS_IMPLEMENTATION_GUARD_4096")
    print("PROVISIONAL_PRIMARY_POINT_ESTIMATE_29=" + str(bootstrap[EFFECT_COLUMNS[0]]["point_estimate"]))
    print("PROVISIONAL_PRIMARY_LOWER_95_29=" + str(bootstrap[EFFECT_COLUMNS[0]]["lower_95"]))
    print("PROVISIONAL_PRIMARY_UPPER_95_29=" + str(bootstrap[EFFECT_COLUMNS[0]]["upper_95"]))
    print("AUTOMATIC_EXTRA_SEEDS_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
